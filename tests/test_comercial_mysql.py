"""Integración optativa con un mysqld de prueba de localhost. Crea un esquema exclusivo."""
import os
import secrets
import unittest
from pathlib import Path
from uuid import uuid4

import mysql.connector
from fastapi.testclient import TestClient

from app.core.claves_comerciales import proteger
from app.core.config import Settings
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
        cls.cur.execute("CREATE TABLE vehiculos(id_vehiculo INT PRIMARY KEY, nombre VARCHAR(80), modelo VARCHAR(80),activo BOOL)")
        cls.cur.execute("CREATE TABLE demos(id_demo INT PRIMARY KEY,activo BOOL)")
        cls.cur.execute("INSERT INTO vehiculos VALUES(47,'Unidad 47','Excavadora',1)")
        migrations = Path(__file__).resolve().parents[1] / "migrations/4.3"
        for name in ("001_catalogo.sql", "002_unidades_existentes.sql", "002_unidades_existentes.sql"):
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

    def test_modulo_opcional(self):
        with TestClient(create_app(self.settings.model_copy(update={"comercial_habilitado":False}))) as old:
            self.assertEqual(old.get("/comercial/resumen").status_code,404)
            self.assertIn("/vehiculos/{id_vehiculo}/historial",old.get("/openapi.json").json()["paths"])
