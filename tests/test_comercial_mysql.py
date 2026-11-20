"""Integración optativa con un mysqld de prueba de localhost. Crea un esquema exclusivo."""
import base64
import os
import secrets
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock

import mysql.connector
from fastapi.testclient import TestClient

from starlette.websockets import WebSocketDisconnect
from tests.fakes import MemoryRepository
from app.core.claves_comerciales import proteger
from app.core.config import Settings
from app.core.errors import ServiceError
from app.main import create_app


@unittest.skipUnless(os.getenv("MYSQL43_TEST_PORT"), "requiere MySQL aislado en localhost")
class ComercialMySQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = "qa43_" + uuid4().hex
        cls.password = secrets.token_urlsafe(24)
        cls.db = mysql.connector.connect(host="127.0.0.1", port=int(os.environ["MYSQL43_TEST_PORT"]),
                                         user="root", password=os.environ["MYSQL43_TEST_PASSWORD"],
                                         autocommit=True)
        cls.addClassCleanup(cls.db.close)
        cls.cur = cls.db.cursor()
        cls.addClassCleanup(cls.cur.close)
        cls.cur.execute("CREATE DATABASE " + schema + " CHARACTER SET utf8mb4")
        cls.addClassCleanup(cls.cur.execute, "DROP DATABASE " + schema)
        cls.cur.execute("USE " + schema)
        cls.cur.execute("CREATE TABLE vehiculos(id_vehiculo INT PRIMARY KEY AUTO_INCREMENT, nombre VARCHAR(80), modelo VARCHAR(80),activo BOOL)")
        cls.cur.execute("CREATE TABLE demos(id_demo INT PRIMARY KEY AUTO_INCREMENT,id_vehiculo INT,nombre VARCHAR(80),descripcion VARCHAR(255),activo BOOL DEFAULT TRUE)")
        cls.cur.execute("CREATE TABLE comandos(id_comando INT PRIMARY KEY,id_vehiculo INT,nombre VARCHAR(60),codigo INT,activo BOOL)")
        cls.cur.execute("CREATE TABLE demo_movimientos(id_demo_movimiento INT PRIMARY KEY AUTO_INCREMENT,id_demo INT,id_comando INT,orden INT,duracion_ms INT,pausa_ms INT)")
        cls.cur.execute("INSERT INTO vehiculos VALUES(47,'Unidad 47','Excavadora',1)")
        migrations = Path(__file__).resolve().parents[1] / "migrations/4.3"
        for name in ("001_catalogo.sql", "002_unidades_existentes.sql", "002_unidades_existentes.sql", "004_propiedad.sql", "004_propiedad.sql", "005_demos_exhibicion.sql"):
            statements = "\n".join(line for line in (migrations/name).read_text(encoding="utf-8").splitlines()
                                   if not line.lstrip().startswith("--"))
            for statement in statements.split(";"):
                if statement.strip():
                    cls.cur.execute(statement)
        cls.cur.executemany("INSERT INTO comercial_usuarios(correo,nombre,rol,clave_hash) VALUES(%s,%s,%s,%s)",
                            [(role+"@ejemplo.test",role,role,proteger(cls.password)) for role in ("admin","usuario")])
        cls.settings = Settings(_env_file=None, comercial_habilitado=True, mysql_host="127.0.0.1",
                                mysql_port=int(os.environ["MYSQL43_TEST_PORT"]), mysql_user="root",
                                mysql_password=os.environ["MYSQL43_TEST_PASSWORD"], mysql_database=schema,
                                control_token="Legacy43")
        cls.client = TestClient(create_app(cls.settings))
        cls.addClassCleanup(cls.client.close)

    def login(self, role="admin"):
        res = self.client.post("/comercial/acceso", json={"correo": role+"@ejemplo.test", "clave": self.password})
        self.assertEqual(res.status_code, 200, res.text)
        return {"Authorization": "Bearer " + res.json()["token"]}

    def test_roles_expiracion_y_salida(self):
        self.assertEqual(self.client.get("/comercial/resumen").status_code, 401)
        self.assertEqual(self.client.get("/comercial/resumen", headers={"Authorization": "Bearer Legacy43"}).status_code, 401)
        headers = self.login("usuario")
        self.assertEqual(self.client.get("/comercial/unidades", headers=headers).status_code, 403)
        admin = self.login()
        self.assertEqual(self.client.delete("/comercial/sesion",headers=admin).status_code,204)
        self.assertEqual(self.client.get("/comercial/resumen",headers=admin).status_code,401)
        admin = self.login()
        self.cur.execute("UPDATE comercial_sesiones SET vence=UTC_TIMESTAMP() - INTERVAL 1 SECOND")
        self.assertEqual(self.client.get("/comercial/resumen",headers=admin).status_code,401)

    def test_catalogo_persistencia_y_baja_logica(self):
        headers = self.login()
        models = "/comercial/modelos"
        self.assertEqual(self.client.get("/comercial/resumen", headers=headers).json()["total_unidades"],1)
        units = self.client.get("/comercial/unidades",headers=headers).json()
        self.assertEqual((units[0]["id_vehiculo"],units[0]["estado"]),(47,"sin_clasificar"))
        form = {"nombre":"Laboratorio","descripcion":"Prueba"}
        created = self.client.post(models,json=form,headers=headers)
        self.assertEqual(created.status_code,201,created.text)
        self.assertEqual(self.client.post(models,json=form,headers=headers).status_code,409)
        mid = created.json()["id_modelo"]
        self.assertEqual(self.client.put(f"{models}/{mid}",json={**form,"activo":False},headers=headers).status_code,200)
        result = self.client.get(models,params={"buscar":"Laboratorio","limite":1},headers=headers)
        self.assertEqual(result.json()[0]["activo"],False)
        self.cur.execute("SELECT accion FROM comercial_auditoria WHERE id_recurso=%s ORDER BY id_evento",(mid,))
        self.assertEqual(self.cur.fetchall(),[("crear_modelo",),("actualizar_modelo",)])
        self.assertEqual(self.client.get("/comercial/modelos?limite=101",headers=headers).status_code,422)

    def test_clientes_baja_revoca_y_no_edita_administradores(self):
        headers = self.login()
        body = {"nombre":"Cliente de prueba", "correo":"persona@example.test", "clave":self.password}
        response = self.client.post("/comercial/clientes", headers=headers, json=body)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertNotIn(self.password, response.text)
        uid = response.json()["id_usuario"]
        self.assertEqual(self.client.post("/comercial/clientes", headers=headers, json=body).status_code,409)
        invalid = self.client.post("/comercial/clientes",headers=headers,json={**body,"rol":"admin"})
        self.assertEqual(invalid.status_code,422)
        self.assertNotIn(self.password,invalid.text)
        session = self.client.post("/comercial/acceso",json={"correo":body["correo"],"clave":self.password}).json()
        buyer = {"Authorization":"Bearer "+session["token"]}
        self.assertEqual(self.client.get("/comercial/clientes",headers=buyer).status_code,403)
        changes = {"nombre":body["nombre"],"correo":body["correo"],"activo":False}
        self.assertEqual(self.client.put(f"/comercial/clientes/{uid}",headers=headers,json=changes).status_code,200)
        self.assertEqual(self.client.get("/comercial/clientes",headers=buyer).status_code,401)
        self.cur.execute("SELECT id_usuario FROM comercial_usuarios WHERE rol='admin'")
        admin_id = self.cur.fetchone()[0]
        self.assertEqual(self.client.put(f"/comercial/clientes/{admin_id}",headers=headers,json=changes).status_code,404)
        self.assertEqual(self.client.get("/comercial/clientes?buscar=persona",headers=headers).json()[0]["activo"],False)

    def test_propiedad_canales_y_transferencia(self):
        repo = MemoryRepository()
        repo.states[47] = {**repo.states[1], "id_vehiculo": 47}
        app = create_app(self.settings, repo)
        admin, a = self.login(), self.login("usuario")
        self.cur.execute("SELECT id_usuario FROM comercial_usuarios WHERE correo='usuario@ejemplo.test'")
        uid_a = self.cur.fetchone()[0]
        body = {"nombre": "Segundo", "correo": "segundo@ejemplo.test", "clave": self.password}
        uid_b = self.client.post("/comercial/clientes", headers=admin, json=body).json()["id_usuario"]
        b = self.login("segundo")
        path = "/comercial/unidades/47/propietario"

        def socket(client, headers, role):
            token = headers["Authorization"].split()[1].encode()
            encoded = base64.urlsafe_b64encode(token).decode().rstrip("=")
            return client.websocket_connect("/ws/vehiculos/47", subprotocols=[role,"token."+encoded],
                                            headers={"origin":"http://testserver"})

        with TestClient(app) as client:
            def asignar(headers, nuevo, anterior):
                return client.put(path,headers=headers,json={"id_usuario":nuevo,"anterior":anterior}).status_code

            self.assertEqual(asignar(a,uid_a,None),403)
            self.assertEqual(asignar(admin,uid_a,None),204)
            self.assertEqual(client.get("/comercial/mis-vehiculos",headers=a).json()[0]["id_vehiculo"],47)
            self.assertEqual(client.get("/comercial/mis-vehiculos",headers=b).json(),[])
            self.assertEqual(client.get("/vehiculos/47/historial").status_code,401)
            for headers in (b, admin, {"Authorization":"Bearer Legacy43"}):
                for method, url, data in [
                    ("GET","/vehiculos/47/historial",None), ("GET","/vehiculos/47/dispositivo",None),
                    ("GET","/admin/vehiculos/47/estado",None), ("GET","/admin/vehiculos/47/demos",None),
                    ("POST","/vehiculos/47/movimientos",{"id_comando":102}),
                    ("DELETE","/vehiculos/47/control",None),
                ]:
                    self.assertIn(client.request(method,url,headers=headers,json=data).status_code,(401,403))
                for role in ("iot-control","iot-monitor"):
                    with self.assertRaises(WebSocketDisconnect), socket(client,headers,role):
                        pass
            with socket(client,a,"iot-control") as mando, socket(client,a,"iot-monitor") as monitor:
                self.assertEqual(mando.receive_json()["tipo"],"estado")
                self.assertEqual(monitor.receive_json()["tipo"],"estado")
                self.assertEqual(monitor.receive_json()["tipo"],"historial")
                mando.send_json({"id":1,"accion":"estado"})
                self.assertTrue(mando.receive_json()["ok"])
                self.assertEqual(asignar(admin,uid_b,None),409)
                self.assertEqual(asignar(admin,uid_b,uid_a),204)
                for channel in (mando,monitor):
                    with self.assertRaises(WebSocketDisconnect):
                        channel.receive_json()
            self.assertEqual(client.get("/vehiculos/47/historial",headers=a).status_code,403)
            self.assertEqual(client.get("/comercial/mis-vehiculos",headers=a).json(),[])
            with socket(client,b,"iot-monitor") as monitor:
                monitor.receive_json()
                monitor.receive_json()
                res = client.post("/vehiculos/47/movimientos",json={"id_comando":102},headers=b)
                self.assertEqual(res.status_code,200,res.text)
                self.assertEqual(monitor.receive_json()["id_vehiculo"],47)
                self.assertEqual(client.delete("/comercial/sesion",headers=b).status_code,204)
                with self.assertRaises(WebSocketDisconnect):
                    monitor.receive_json()
            self.assertEqual(asignar(admin,None,uid_b),204)
            self.cur.execute("SELECT anterior,nuevo FROM comercial_cambios_propietario ORDER BY id_evento")
            self.assertEqual(self.cur.fetchall(),[(None,uid_a),(uid_a,uid_b),(uid_b,None)])

    def test_unidades_demos_privadas_y_exhibicion(self):
        admin, comprador = self.login(), self.login("usuario")
        self.cur.execute("SELECT id_usuario FROM comercial_usuarios WHERE correo='usuario@ejemplo.test'")
        usuario = self.cur.fetchone()[0]
        self.cur.execute("SELECT id_modelo FROM comercial_modelos WHERE nombre='Excavadora'")
        modelo = self.cur.fetchone()[0]
        cuerpo = {"nombre":"Unidad de taller","id_modelo":modelo,"estado":"disponible"}
        nueva = self.client.post("/comercial/unidades",headers=admin,json=cuerpo)
        self.assertEqual(nueva.status_code,201,nueva.text)
        unidad = nueva.json()["id_vehiculo"]
        ruta = f"/comercial/unidades/{unidad}"
        self.cur.execute("INSERT INTO comandos VALUES(410,%s,'Pala',1,1)",(unidad,))
        confirmado = self.client.put(ruta+"/propietario",headers=admin,json={"id_usuario":usuario,"anterior":None})
        self.assertEqual(confirmado.status_code,204,confirmado.text)
        demo = {"nombre":"Privada","pasos":[{"id_comando":410,"duracion_ms":400,"pausa_ms":200}]}
        creada = self.client.post(ruta+"/secuencias",headers=comprador,json=demo)
        self.assertEqual(creada.status_code,201,creada.text)
        endpoint = ruta+"/secuencias/"+str(creada.json()["id_demo"])
        self.assertEqual(self.client.get(endpoint,headers=comprador).json(),demo["pasos"])
        self.assertEqual(self.client.put(endpoint,headers=admin,json=demo).status_code,403)
        self.assertEqual(self.client.put(endpoint,headers=comprador,json={**demo,"pasos":[{**demo["pasos"][0],"id_comando":401}]}).status_code,422)
        self.assertEqual(self.client.put(ruta,headers=admin,json={**cuerpo,"estado":"inactivo"}).status_code,409)
        self.assertEqual(self.client.put(ruta+"/propietario",headers=admin,json={"id_usuario":None,"anterior":usuario}).status_code,204)
        self.assertEqual(self.client.get(endpoint,headers=comprador).status_code,403)
        self.assertEqual(self.client.put(ruta,headers=admin,json={**cuerpo,"estado":"exhibicion"}).status_code,200)
        repo = self.client.app.state.comercial
        reserva, movimientos = repo.reservar(unidad,45,(1,4))
        self.assertEqual(movimientos,{1:"Pala"})
        with self.assertRaises(ServiceError) as exc:
            repo.reservar(unidad,45,(1,4))
        self.assertEqual(exc.exception.status_code,409)
        repo.finalizar_exhibicion(reserva,"desconexion")
        otra,_ = repo.reservar(unidad,45,(1,4))
        self.assertNotEqual(reserva,otra)
        repo.finalizar_exhibicion(otra,"detener")
        self.assertEqual(self.client.get("/exhibicion/catalogo").json()["habilitada"],False)
        app = create_app(self.settings.model_copy(update={"exhibicion_habilitada":True}))
        dispositivo = app.state.device_service
        dispositivo.status = lambda _: {"listo":True,"demo_temporizada":True,"control_ocupado":False}
        dispositivo.acquire = AsyncMock(return_value={"lease_id":"placa-de-prueba"})
        dispositivo.command = AsyncMock(return_value={"orden_enviada":True})
        dispositivo.stop = AsyncMock(return_value={})
        ws = f"/exhibicion/ws/{unidad}"
        origin = {"origin":"http://testserver"}
        with TestClient(app) as cliente:
            with cliente.websocket_connect(ws,headers=origin) as invitado:
                self.assertEqual(invitado.receive_json()["tipo"],"inicio")
                with cliente.websocket_connect(ws,headers=origin) as ocupado:
                    self.assertEqual(ocupado.receive_json()["tipo"],"error")
                invitado.send_json({"codigo":1})
                self.assertEqual(invitado.receive_json(),{"tipo":"orden","enviada":True})
                invitado.send_json({"accion":"detener"})
                self.assertEqual(invitado.receive()["type"],"websocket.close")
            dispositivo.command.assert_awaited_once_with(unidad,"placa-de-prueba",1,demo_ms=200,record=False)
            dispositivo.stop.assert_awaited_once_with(unidad,"placa-de-prueba",reason="fin_exhibicion")
        self.assertEqual(self.client.get("/salud").json(),{"api":"disponible","rds":"disponible"})
        self.assertEqual(self.client.get("/comercial/auditoria",headers=comprador).status_code,403)
        self.assertIn("alta_demo",{row["accion"] for row in self.client.get("/comercial/auditoria",headers=admin).json()})
        self.assertEqual(self.client.put(ruta,headers=admin,json={**cuerpo,"estado":"inactivo"}).status_code,200)

    def test_vencimiento_y_baja_con_unidades_multiples(self):
        app = create_app(self.settings, MemoryRepository())
        admin = self.login()
        correo = "multiu@ejemplo.test"
        uid = self.client.post("/comercial/clientes", headers=admin,
                               json={"correo":correo,"nombre":"Varias","clave":self.password}).json()["id_usuario"]
        self.cur.execute("INSERT INTO vehiculos VALUES (1,'Uno','Excavadora',1),(2,'Dos','Excavadora',1)")
        self.cur.execute("""INSERT INTO comercial_unidades SELECT id_vehiculo,id_modelo,'disponible'
                            FROM vehiculos CROSS JOIN comercial_modelos
                            WHERE vehiculos.id_vehiculo IN (1,2) AND comercial_modelos.nombre='Excavadora'""")
        with TestClient(app) as client:
            for v in (1,2):
                result = client.put(f"/comercial/unidades/{v}/propietario", headers=admin,
                                    json={"id_usuario":uid,"anterior":None})
                self.assertEqual(result.status_code,204,result.text)
            buyer = self.login("multiu")
            self.assertEqual({r["id_vehiculo"] for r in client.get("/comercial/mis-vehiculos",headers=buyer).json()},{1,2})
            self.cur.execute("UPDATE comercial_sesiones SET vence=UTC_TIMESTAMP()+INTERVAL 2 SECOND WHERE id_usuario=%s",(uid,))
            with client.websocket_connect("/ws/vehiculos/1",headers=buyer) as socket:
                self.assertEqual(socket.receive_json()["id_vehiculo"],1)
                with self.assertRaises(WebSocketDisconnect):
                    socket.receive_json()
            buyer = self.login("multiu")
            with client.websocket_connect("/ws/vehiculos/2",headers=buyer) as socket:
                self.assertEqual(socket.receive_json()["id_vehiculo"],2)
                response = client.put(f"/comercial/clientes/{uid}",headers=admin,
                                      json={"correo":correo,"nombre":"Varias","activo":False})
                self.assertEqual(response.status_code,200)
                with self.assertRaises(WebSocketDisconnect):
                    socket.receive_json()
            self.assertEqual(client.get("/vehiculos/2/historial",headers=buyer).status_code,401)

    def test_modulo_opcional(self):
        with TestClient(create_app(self.settings.model_copy(update={"comercial_habilitado":False}))) as old:
            self.assertEqual(old.get("/comercial/resumen").status_code,404)
            self.assertIn("/vehiculos/{id_vehiculo}/historial",old.get("/openapi.json").json()["paths"])
