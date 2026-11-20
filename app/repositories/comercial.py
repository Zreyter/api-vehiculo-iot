import secrets
from contextlib import contextmanager

from app.core.claves_comerciales import coincide, huella, proteger
from app.core.errors import ServiceError


class ComercialRepository:
    def __init__(self, database):
        self.database = database

    def acceso(self, correo, clave):
        with self.database.transaction(write=True) as conn, conn.cursor(dictionary=True) as cur:
            cur.execute("""SELECT id_usuario,nombre,rol,activo,clave_hash,fallos,
                                  bloqueo_hasta > UTC_TIMESTAMP() AS bloqueado
                           FROM comercial_usuarios WHERE correo=%s FOR UPDATE""", (correo.lower(),))
            user = cur.fetchone()
            if user and user["bloqueado"]:
                raise ServiceError(429, "Espera unos minutos antes de volver a intentar.")
            if user and user["activo"] and coincide(clave, user["clave_hash"]):
                token = secrets.token_urlsafe(32)
                cur.execute("UPDATE comercial_usuarios SET fallos=0,bloqueo_hasta=NULL WHERE id_usuario=%s",
                            (user["id_usuario"],))
                cur.execute("DELETE FROM comercial_sesiones WHERE vence <= UTC_TIMESTAMP()")
                cur.execute("""INSERT INTO comercial_sesiones (token_hash,id_usuario,vence)
                               VALUES (%s,%s,UTC_TIMESTAMP() + INTERVAL 1 HOUR)""",
                            (huella(token), user["id_usuario"]))
                return {"token": token, "nombre": user["nombre"], "rol": user["rol"]}
            if user and user["activo"]:
                fallos = user["fallos"] + 1
                cur.execute("""UPDATE comercial_usuarios SET bloqueo_hasta=
                               IF(%s >= 5,UTC_TIMESTAMP() + INTERVAL 10 MINUTE,NULL),
                               fallos=IF(%s >= 5,0,%s) WHERE id_usuario=%s""",
                            (fallos, fallos, fallos, user["id_usuario"]))
        # El intento fallido debe confirmarse antes de devolver 401.
        raise ServiceError(401, "Correo o contraseña incorrectos.")

    def salir(self, token):
        with self.database.transaction(write=True) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM comercial_sesiones WHERE token_hash=%s", (huella(token),))

    @contextmanager
    def cuenta(self, token, *, rol, escritura=False):
        with self.database.transaction(write=escritura) as conn, conn.cursor(dictionary=True) as cur:
            cur.execute("""SELECT u.id_usuario,u.rol,
                                  TIMESTAMPDIFF(MICROSECOND, UTC_TIMESTAMP(6), s.vence) / 1000000 AS segundos
                           FROM comercial_usuarios u
                           JOIN comercial_sesiones s ON s.id_usuario=u.id_usuario
                           WHERE s.token_hash=%s AND s.vence > UTC_TIMESTAMP() AND u.activo=1""",
                        (huella(token),))
            actor = cur.fetchone()
            if not actor:
                raise ServiceError(401, "La sesión comercial terminó. Vuelve a ingresar.")
            if rol is not None and actor["rol"] != rol:
                raise ServiceError(403, "Esta cuenta no tiene permiso para la operación.")
            yield cur, actor

    @contextmanager
    def administrador(self, token, *, escritura=False):
        with self.cuenta(token, rol="admin", escritura=escritura) as (cur, actor):
            yield cur, actor["id_usuario"]

    def verificar_admin(self, token):
        with self.administrador(token):
            pass

    def permiso_unidad(self, token, unidad):
        with self.cuenta(token, rol="usuario") as (cur, actor):
            if unidad is not None:
                cur.execute("""SELECT 1 FROM comercial_propiedad p JOIN vehiculos v USING(id_vehiculo)
                               JOIN comercial_unidades u USING(id_vehiculo)
                               WHERE p.id_usuario=%s AND p.id_vehiculo=%s AND v.activo=1
                               AND u.estado='asignado'""", (actor["id_usuario"], unidad))
                if not cur.fetchone():
                    raise ServiceError(403, "Esta unidad no está asignada a tu cuenta.")
            return actor["id_usuario"], float(actor["segundos"])

    def exigir_sin_propietario(self, unidad):
        with self.database.transaction() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM comercial_propiedad WHERE id_vehiculo=%s", (unidad,))
            if cur.fetchone():
                raise ServiceError(409, "Retira la asignación antes de desactivar la unidad.")

    def mis_vehiculos(self, token):
        with self.cuenta(token, rol="usuario") as (cur, actor):
            cur.execute("""SELECT v.id_vehiculo,v.nombre,m.nombre modelo,u.estado
                           FROM comercial_propiedad p JOIN vehiculos v USING(id_vehiculo)
                           JOIN comercial_unidades u USING(id_vehiculo) JOIN comercial_modelos m USING(id_modelo)
                           WHERE p.id_usuario=%s AND v.activo=1 AND u.estado='asignado'
                           ORDER BY v.nombre,v.id_vehiculo""", (actor["id_usuario"],))
            return cur.fetchall()

    def asignar(self, token, unidad, nuevo, anterior, *, validar=False):
        with self.administrador(token, escritura=True) as (cur, actor):
            cur.execute("""SELECT v.activo,u.estado,p.id_usuario FROM comercial_unidades u
                           JOIN vehiculos v USING(id_vehiculo) LEFT JOIN comercial_propiedad p USING(id_vehiculo)
                           WHERE u.id_vehiculo=%s FOR UPDATE""", (unidad,))
            fila = cur.fetchone()
            if not fila:
                raise ServiceError(404, "Unidad comercial inexistente.")
            if fila["id_usuario"] != anterior:
                raise ServiceError(409, "La asignación cambió. Actualiza el inventario.")
            if nuevo == anterior:
                return False
            if nuevo is not None:
                if not fila["activo"] or fila["estado"] == "inactivo":
                    raise ServiceError(409, "La unidad está inactiva.")
                cur.execute("""SELECT id_usuario FROM comercial_usuarios WHERE id_usuario=%s
                               AND rol='usuario' AND activo=1 FOR UPDATE""", (nuevo,))
                if not cur.fetchone():
                    raise ServiceError(422, "Selecciona un comprador activo.")
                if validar:
                    return True
                cur.execute("""INSERT INTO comercial_propiedad(id_vehiculo,id_usuario) VALUES(%s,%s)
                               ON DUPLICATE KEY UPDATE id_usuario=%s""", (unidad,nuevo,nuevo))
                estado = "asignado"
            else:
                if validar:
                    return True
                cur.execute("DELETE FROM comercial_propiedad WHERE id_vehiculo=%s", (unidad,))
                estado = "disponible" if fila["activo"] and fila["estado"] != "inactivo" else "inactivo"
            cur.execute("UPDATE comercial_unidades SET estado=%s WHERE id_vehiculo=%s", (estado,unidad))
            cur.execute("""INSERT INTO comercial_auditoria(actor,accion,recurso,id_recurso,resultado)
                           VALUES(%s,'cambiar_propietario','unidad',%s,'correcto')""", (actor,unidad))
            cur.execute("INSERT INTO comercial_cambios_propietario VALUES(%s,%s,%s)", (cur.lastrowid,anterior,nuevo))

    def resumen(self, token):
        with self.administrador(token) as (cur, _):
            cur.execute("""SELECT COUNT(*) total_unidades,
                           COUNT(CASE WHEN v.activo=1 AND estado='asignado' THEN 1 END) asignadas,
                           COUNT(CASE WHEN v.activo=1 AND estado='exhibicion' THEN 1 END) exhibicion,
                           COUNT(CASE WHEN v.activo=1 AND (estado='sin_clasificar' OR estado IS NULL) THEN 1 END) sin_clasificar,
                           (SELECT COUNT(*) FROM comercial_modelos) total_modelos,
                           (SELECT COUNT(*) FROM comercial_usuarios WHERE rol='usuario' AND activo=1) clientes,
                           (SELECT COUNT(*) FROM demos WHERE activo=1) demos
                           FROM vehiculos v LEFT JOIN comercial_unidades u USING(id_vehiculo)""")
            return cur.fetchone()

    def unidades(self, token, buscar, inicio, limite):
        with self.administrador(token) as (cur, _):
            cur.execute("""SELECT v.id_vehiculo,v.nombre,COALESCE(m.nombre,v.modelo,'') modelo,
                                  IF(v.activo=0,'inactivo',COALESCE(u.estado,'sin_clasificar')) estado,
                                  p.id_usuario, c.nombre propietario,u.id_modelo
                           FROM vehiculos v LEFT JOIN comercial_unidades u USING(id_vehiculo)
                           LEFT JOIN comercial_modelos m USING(id_modelo)
                           LEFT JOIN comercial_propiedad p USING(id_vehiculo)
                           LEFT JOIN comercial_usuarios c ON c.id_usuario=p.id_usuario
                           WHERE LOCATE(%s,v.nombre)>0 OR LOCATE(%s,COALESCE(m.nombre,v.modelo,''))>0
                           ORDER BY v.id_vehiculo LIMIT %s OFFSET %s""", (buscar,buscar,limite,inicio))
            return cur.fetchall()

    def modelos(self, token, buscar, inicio, limite):
        with self.administrador(token) as (cur, _):
            cur.execute("""SELECT id_modelo,nombre,descripcion,activo FROM comercial_modelos
                           WHERE LOCATE(%s,nombre)>0 ORDER BY id_modelo LIMIT %s OFFSET %s""",
                        (buscar, limite, inicio))
            return cur.fetchall()

    def guardar_modelo(self, token, modelo, identificador=None):
        with self.administrador(token, escritura=True) as (cur, actor):
            campos = (modelo.nombre, modelo.descripcion, modelo.activo)
            if identificador is None:
                cur.execute("INSERT INTO comercial_modelos(nombre,descripcion,activo) VALUES(%s,%s,%s)", campos)
                identificador = cur.lastrowid
                accion = "crear_modelo"
            else:
                cur.execute("SELECT id_modelo FROM comercial_modelos WHERE id_modelo=%s FOR UPDATE",
                            (identificador,))
                if not cur.fetchone():
                    raise ServiceError(404, "Modelo inexistente.")
                cur.execute("UPDATE comercial_modelos SET nombre=%s,descripcion=%s,activo=%s WHERE id_modelo=%s",
                            (*campos, identificador))
                accion = "actualizar_modelo"
            cur.execute("""INSERT INTO comercial_auditoria(actor,accion,recurso,id_recurso,resultado)
                           VALUES(%s,%s,'modelo',%s,'correcto')""", (actor, accion, identificador))
            return {"id_modelo": identificador, **modelo.model_dump()}

    def clientes(self, token, buscar, inicio, limite):
        with self.administrador(token) as (cur, _):
            cur.execute("""SELECT id_usuario,nombre,correo,activo FROM comercial_usuarios
                           WHERE rol='usuario' AND (LOCATE(%s,nombre)>0 OR LOCATE(%s,correo)>0)
                           ORDER BY id_usuario LIMIT %s OFFSET %s""", (buscar,buscar,limite,inicio))
            return cur.fetchall()

    def guardar_cliente(self, token, cliente, identificador=None):
        correo = cliente.correo.lower()
        with self.administrador(token, escritura=True) as (cur, actor):
            if identificador is None:
                cur.execute("""INSERT INTO comercial_usuarios (nombre,correo,clave_hash,rol)
                               VALUES (%s,%s,%s,'usuario')""",
                            (cliente.nombre,correo,proteger(cliente.clave.get_secret_value())))
                identificador, activo, accion = cur.lastrowid, True, "alta_cliente"
            else:
                cur.execute("""SELECT id_usuario FROM comercial_usuarios
                               WHERE id_usuario=%s AND rol='usuario' FOR UPDATE""", (identificador,))
                if not cur.fetchone():
                    raise ServiceError(404, "Cliente inexistente.")
                activo, accion = cliente.activo, "actualizar_cliente"
                cur.execute("""UPDATE comercial_usuarios SET nombre=%s, correo=%s, activo=%s
                               WHERE id_usuario=%s""", (cliente.nombre,correo,activo,identificador))
                if not activo:
                    cur.execute("DELETE FROM comercial_sesiones WHERE id_usuario=%s", (identificador,))
            cur.execute("""INSERT INTO comercial_auditoria(actor,accion,recurso,id_recurso,resultado)
                           VALUES(%s,%s,'cliente',%s,'correcto')""", (actor,accion,identificador))
            return {"id_usuario": identificador, "nombre": cliente.nombre, "correo": correo, "activo": activo}
