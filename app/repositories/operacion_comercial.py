from contextlib import contextmanager

from app.core.errors import ServiceError
from app.repositories.comercial import ComercialRepository
from app.services.demo_service import PHYSICAL_CODES


def auditar(cur, actor, accion, recurso, identificador):
    cur.execute("""INSERT INTO comercial_auditoria(actor,accion,recurso,id_recurso,resultado)
                   VALUES(%s,%s,%s,%s,'correcto')""", (actor,accion,recurso,identificador))


class OperacionComercial(ComercialRepository):
    def salud(self):
        with self.database.transaction() as cn, cn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1

    def auditoria(self, token, buscar, inicio, limite):
        with self.administrador(token) as (cur, _):
            cur.execute("""SELECT id_evento,fecha,actor,accion,recurso,id_recurso,resultado
                           FROM comercial_auditoria WHERE LOCATE(%s,accion)>0 OR LOCATE(%s,recurso)>0
                           ORDER BY id_evento DESC LIMIT %s OFFSET %s""",(buscar,buscar,limite,inicio))
            return cur.fetchall()

    def guardar_unidad(self, token, ficha, unidad=None):
        with self.administrador(token, escritura=True) as (cur, actor):
            cur.execute("SELECT nombre FROM comercial_modelos WHERE id_modelo=%s AND activo=1", (ficha.id_modelo,))
            modelo = cur.fetchone()
            if not modelo:
                raise ServiceError(422, "Selecciona un modelo activo.")
            if unidad is not None:
                cur.execute("""SELECT v.id_vehiculo,p.id_usuario,u.id_modelo FROM vehiculos v
                               LEFT JOIN comercial_unidades u USING(id_vehiculo)
                               LEFT JOIN comercial_propiedad p USING(id_vehiculo)
                               WHERE v.id_vehiculo=%s FOR UPDATE""",(unidad,))
                actual = cur.fetchone()
                if not actual:
                    raise ServiceError(404, "Unidad inexistente.")
                if actual["id_usuario"] and (ficha.estado != "asignado" or ficha.id_modelo != actual["id_modelo"]):
                    raise ServiceError(409, "Retira la asignación antes de cambiar el modelo o el estado.")
            if ficha.estado == "asignado" and (unidad is None or not actual["id_usuario"]):
                raise ServiceError(422, "Selecciona un comprador desde Asignar.")
            activo = ficha.estado != "inactivo"
            if unidad is None:
                cur.execute("INSERT INTO vehiculos(nombre,modelo,activo) VALUES(%s,%s,%s)",
                            (ficha.nombre,modelo["nombre"],activo))
                unidad = cur.lastrowid
                accion = "alta_unidad"
            else:
                cur.execute("UPDATE vehiculos SET nombre=%s,modelo=%s,activo=%s WHERE id_vehiculo=%s",
                            (ficha.nombre,modelo["nombre"],activo,unidad))
                accion = "baja_unidad" if not activo else "editar_unidad"
            cur.execute("""INSERT INTO comercial_unidades(id_vehiculo,id_modelo,estado) VALUES(%s,%s,%s)
                           ON DUPLICATE KEY UPDATE id_modelo=%s, estado=%s""",
                        (unidad,ficha.id_modelo,ficha.estado,ficha.id_modelo,ficha.estado))
            auditar(cur,actor,accion,"unidad",unidad)
            return {"id_vehiculo": unidad}

    @contextmanager
    def editor(self, token, unidad, escritura=False):
        with self.cuenta(token, rol=None, escritura=escritura) as (cur,actor):
            cur.execute("""SELECT v.activo,p.id_usuario FROM vehiculos v
                           LEFT JOIN comercial_propiedad p USING(id_vehiculo) WHERE v.id_vehiculo=%s""",(unidad,))
            fila = cur.fetchone()
            if not fila or not fila["activo"]:
                raise ServiceError(404,"Unidad inexistente o inactiva.")
            admin = actor["rol"] == "admin"
            if not admin and fila["id_usuario"] != actor["id_usuario"]:
                raise ServiceError(403,"Esta unidad no está asignada a tu cuenta.")
            yield cur,actor["id_usuario"],admin

    def demos_editor(self, token, unidad):
        with self.editor(token,unidad) as (cur,actor,admin):
            cur.execute("""SELECT d.id_demo,d.nombre,d.descripcion, p.id_usuario IS NULL AS fabrica
                           FROM demos d LEFT JOIN comercial_demos_privadas p USING(id_demo)
                           WHERE d.id_vehiculo=%s AND d.activo=1 AND
                           (p.id_usuario IS NULL OR p.id_usuario=%s) ORDER BY d.nombre,d.id_demo""",
                        (unidad,None if admin else actor))
            demos=cur.fetchall()
            cur.execute("""SELECT id_comando,nombre,codigo FROM comandos WHERE id_vehiculo=%s AND activo=1
                           ORDER BY codigo""",(unidad,))
            return {"demos":demos,"comandos":[c for c in cur.fetchall() if c["codigo"] in PHYSICAL_CODES]}

    def demo_privada(self, unidad, demo=None, *, mantenimiento=False):
        with self.database.transaction() as cn, cn.cursor() as cur:
            cur.execute("""SELECT d.id_demo FROM demos d JOIN comercial_demos_privadas p USING(id_demo)
                           LEFT JOIN comercial_propiedad u ON u.id_vehiculo=d.id_vehiculo
                           WHERE d.id_vehiculo=%s AND (%s OR NOT (u.id_usuario <=> p.id_usuario))""",
                        (unidad,mantenimiento))
            ocultas={row[0] for row in cur.fetchall()}
            if demo in ocultas:
                raise ServiceError(403,"La demo es privada.")
            return ocultas

    def guardar_demo(self, token, unidad, ficha, demo=None):
        with self.editor(token,unidad,escritura=True) as (cur,actor,admin):
            if demo is not None:
                cur.execute("""SELECT p.id_usuario FROM demos d LEFT JOIN comercial_demos_privadas p USING(id_demo)
                               WHERE d.id_demo=%s AND d.id_vehiculo=%s AND d.activo=1 FOR UPDATE""",(demo,unidad))
                row=cur.fetchone()
                if not row or row["id_usuario"] != (None if admin else actor):
                    raise ServiceError(403,"Esta cuenta no puede modificar la demo.")
            if ficha is None:
                cur.execute("UPDATE demos SET activo=0 WHERE id_demo=%s",(demo,))
                accion="baja_demo"
            else:
                cur.execute("SELECT id_comando,codigo FROM comandos WHERE id_vehiculo=%s AND activo=1",(unidad,))
                permitidos={r["id_comando"] for r in cur.fetchall() if r["codigo"] in PHYSICAL_CODES}
                if any(p.id_comando not in permitidos for p in ficha.pasos):
                    raise ServiceError(422,"Cada paso debe usar un movimiento permitido de esta unidad.")
                if demo is None:
                    cur.execute("INSERT INTO demos(id_vehiculo,nombre,descripcion) VALUES(%s,%s,%s)",
                                (unidad,ficha.nombre,ficha.descripcion))
                    demo=cur.lastrowid
                    if not admin:
                        cur.execute("INSERT INTO comercial_demos_privadas VALUES(%s,%s)",(demo,actor))
                    accion="alta_demo"
                else:
                    cur.execute("UPDATE demos SET nombre=%s,descripcion=%s WHERE id_demo=%s",
                                (ficha.nombre,ficha.descripcion,demo))
                    cur.execute("DELETE FROM demo_movimientos WHERE id_demo=%s",(demo,))
                    accion="editar_demo"
                cur.executemany("""INSERT INTO demo_movimientos(id_demo,id_comando,orden,duracion_ms,pausa_ms)
                                   VALUES(%s,%s,%s,%s,%s)""",
                                [(demo,p.id_comando,i,p.duracion_ms,p.pausa_ms) for i,p in enumerate(ficha.pasos,1)])
            auditar(cur,actor,accion,"demo",demo)
            return {"id_demo":demo}

    def pasos_editor(self, token, unidad, demo):
        with self.editor(token,unidad) as (cur,actor,admin):
            cur.execute("""SELECT m.id_comando,m.duracion_ms,m.pausa_ms FROM demo_movimientos m
                           JOIN demos d USING(id_demo) LEFT JOIN comercial_demos_privadas p USING(id_demo)
                           WHERE d.id_demo=%s AND d.id_vehiculo=%s AND d.activo=1
                           AND (p.id_usuario IS NULL OR p.id_usuario=%s) ORDER BY m.orden""",
                        (demo,unidad,None if admin else actor))
            pasos = cur.fetchall()
            if not pasos:
                raise ServiceError(404, "No hay pasos disponibles para esta demo.")
            return pasos

    def exhibicion(self, compartidas=()):
        compartidas = tuple(compartidas)
        seleccion = ",".join(["%s"] * len(compartidas)) or "NULL"
        with self.database.transaction() as cn, cn.cursor(dictionary=True) as cur:
            cur.execute("SELECT id_modelo,nombre,descripcion FROM comercial_modelos WHERE activo=1 ORDER BY nombre")
            modelos=cur.fetchall()
            cur.execute(f"""SELECT u.id_modelo,u.id_vehiculo,v.nombre,EXISTS(
                           SELECT 1 FROM comercial_exhibiciones e WHERE e.unidad_reservada=u.id_vehiculo
                           AND e.vence>UTC_TIMESTAMP(6)) reservada FROM comercial_unidades u
                           JOIN vehiculos v USING(id_vehiculo) JOIN comercial_modelos m USING(id_modelo)
                           LEFT JOIN comercial_propiedad p USING(id_vehiculo)
                           WHERE v.activo=1 AND m.activo=1 AND
                           ((u.estado='exhibicion' AND p.id_usuario IS NULL) OR
                            (u.estado='asignado' AND p.id_usuario IS NOT NULL AND
                             u.id_vehiculo IN ({seleccion})))""", compartidas)
            return modelos,cur.fetchall()

    def reservar(self, unidad, segundos, permitidos, compartidas=()):
        compartidas = tuple(compartidas)
        seleccion = ",".join(["%s"] * len(compartidas)) or "NULL"
        with self.database.transaction(write=True) as cn,cn.cursor(dictionary=True) as cur:
            cur.execute(f"""SELECT 1 FROM comercial_unidades u JOIN vehiculos v USING(id_vehiculo)
                           JOIN comercial_modelos m USING(id_modelo) LEFT JOIN comercial_propiedad p USING(id_vehiculo)
                           WHERE u.id_vehiculo=%s AND v.activo=1 AND m.activo=1 AND
                           ((u.estado='exhibicion' AND p.id_usuario IS NULL) OR
                            (u.estado='asignado' AND p.id_usuario IS NOT NULL AND
                             u.id_vehiculo IN ({seleccion}))) FOR UPDATE""",(unidad,*compartidas))
            if not cur.fetchone():
                raise ServiceError(403,"Unidad fuera de exhibición.")
            cur.execute("SELECT codigo,nombre FROM comandos WHERE id_vehiculo=%s AND activo=1",(unidad,))
            comandos={r["codigo"]:r["nombre"] for r in cur.fetchall() if r["codigo"] in permitidos}
            if not comandos:
                raise ServiceError(409,"La unidad carece de movimientos de exhibición.")
            cur.execute("""UPDATE comercial_exhibiciones SET cierre=vence,motivo='caducada'
                           WHERE unidad_reservada=%s AND vence<=UTC_TIMESTAMP(6)""",(unidad,))
            cur.execute("""INSERT INTO comercial_exhibiciones(id_vehiculo,vence)
                           VALUES(%s,UTC_TIMESTAMP(6)+INTERVAL %s SECOND)""",(unidad,segundos))
            return cur.lastrowid,comandos

    def finalizar_exhibicion(self, reserva, motivo):
        with self.database.transaction(write=True) as cn,cn.cursor() as cur:
            cur.execute("""UPDATE comercial_exhibiciones SET cierre=UTC_TIMESTAMP(6),motivo=%s
                           WHERE id_sesion=%s AND cierre IS NULL""",(motivo,reserva))
