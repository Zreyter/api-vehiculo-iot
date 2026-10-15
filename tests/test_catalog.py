import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.vehicle_repository import VehicleRepository
from tests.catalog_mysql import FakeMySQL

VEHICLE = {"nombre": "Vehículo CRUD", "modelo": "Laboratorio", "descripcion": "Registro aislado de prueba", "microcontrolador": "ESP8266"}
COMMAND = {"nombre": "COMANDO_PRUEBA", "codigo": 6000, "descripcion": "Código distinto del ID"}
DEMO = {"nombre": "DEMO CRUD", "descripcion": "Sin ejecución física"}


class CatalogApiTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeMySQL()
        patcher = patch("app.core.database.mysql.connector.connect", side_effect=self.server.connect)
        patcher.start()
        self.addCleanup(patcher.stop)
        settings = Settings(_env_file=None, control_token=SecretStr("test-only-token"), mysql_password=SecretStr("test-only-password"))
        database = Database(settings)
        self.app = create_app(settings, VehicleRepository(database), CatalogRepository(database))
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.auth = {"Authorization": "Bearer test-only-token"}

    def send(self, method, path, data=None, expected=200):
        response = self.client.request(method, path, json=data, headers=self.auth)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json() if response.content else None

    def test_full_crud_and_original_services_cover_all_21_procedures(self):
        original_history = deepcopy(self.server.data["historial"])
        vehicle = self.send("POST", "/admin/vehiculos", VEHICLE, 201)
        vehicle_id = vehicle["id_vehiculo"]
        base = f"/admin/vehiculos/{vehicle_id}"
        self.assertEqual(vehicle["nombre"], VEHICLE["nombre"])
        self.assertEqual(len(self.send("GET", "/admin/vehiculos")), 3)
        self.assertEqual(self.send("GET", base), vehicle)
        self.assertIsNone(self.send("GET", base + "/estado"))
        command = self.send("POST", base + "/comandos", COMMAND, 201)
        command_id = command["id_comando"]
        self.assertNotEqual(command_id, command["codigo"])
        self.assertEqual(self.send("GET", base + "/comandos"), [command])
        demo = self.send("POST", base + "/demos", DEMO, 201)
        demo_id = demo["id_demo"]
        demo_path = base + f"/demos/{demo_id}"
        self.assertEqual(self.send("GET", base + "/demos"), [demo])
        step = {"id_comando": command_id, "orden": 1, "duracion_ms": 25, "pausa_ms": 7}
        movement = self.send("POST", demo_path + "/movimientos", step, 201)
        movement_path = demo_path + f"/movimientos/{movement['id_demo_movimiento']}"
        self.assertEqual(movement["id_demo"], demo_id)
        self.assertEqual(movement["codigo"], 6000)
        self.assertEqual(self.send("GET", demo_path + "/movimientos"), [movement])
        self.assertEqual(len(self.server.id_queries), 1)
        self.assertTrue(self.server.id_queries[0].closed)
        for path, data in [
            (base, dict(VEHICLE, nombre="Vehículo actualizado", activo=0)),
            (base + f"/comandos/{command_id}", dict(COMMAND, codigo=6001, activo=0)),
            (demo_path, dict(DEMO, nombre="DEMO actualizada", activo=0)),
            (movement_path, dict(step, orden=2, duracion_ms=50, pausa_ms=0)),
        ]:
            result = self.send("PUT", path, data)
            for key, value in data.items():
                self.assertEqual(result[key], value)
        for path in (movement_path, demo_path, base + f"/comandos/{command_id}", base):
            self.send("DELETE", path, expected=204)
        self.send("GET", base, expected=404)
        self.assertEqual(self.server.data["historial"], original_history)
        self.assertEqual(self.server.commits, 12)

        # Regresión de las rutas originales con los mismos repositorios y DB simulada.
        self.send("POST", "/vehiculos/1/movimientos", {"id_comando": 102, "origen": "Postman"})
        before = self.send("GET", "/vehiculos/1/historial")
        self.server.data["movimientos"][501].update(duracion_ms=0, pausa_ms=0)
        with self.client.websocket_connect("/ws/vehiculos/1", headers=self.auth) as socket:
            socket.receive_json()
            self.send("POST", "/vehiculos/1/demos", {"id_demo": 42}, 202)
            events = [socket.receive_json() for _ in range(3)]
        self.assertEqual([e["tipo"] for e in events], ["demo_iniciada", "demo_movimiento", "demo_finalizada"])
        self.assertEqual(before, self.send("GET", "/vehiculos/1/historial"))
        import csv
        with (Path(__file__).resolve().parents[1] / "docs/sp_definiciones.csv").open(encoding="utf-8-sig", newline="") as f:
            expected = {r["procedimiento"] for r in csv.DictReader(f)}
        self.assertEqual({name for name, _ in self.server.calls}, expected)

    def test_all_admin_routes_require_token_including_reads(self):
        schema = self.client.get("/openapi.json").json()
        for path, methods in schema["paths"].items():
            if path.startswith("/admin/"):
                actual = path.replace("{id_vehiculo}", "1").replace("{id_comando}", "102").replace("{id_demo}", "42").replace("{id_demo_movimiento}", "501")
                for method, metadata in methods.items():
                    with self.subTest(method=method, path=path):
                        self.assertEqual(metadata["security"], [{"HTTPBearer": []}])
                        response = self.client.request(method, actual, json={})
                        self.assertEqual(response.status_code, 401)

    def test_parent_relationships_are_checked_before_mutation(self):
        before = deepcopy(self.server.data)
        cases = [
            ("PUT", "/admin/vehiculos/2/comandos/102", dict(COMMAND, activo=1)),
            ("DELETE", "/admin/vehiculos/2/comandos/102", None),
            ("PUT", "/admin/vehiculos/2/demos/42", dict(DEMO, activo=1)),
            ("DELETE", "/admin/vehiculos/2/demos/42", None),
            ("GET", "/admin/vehiculos/2/demos/42/movimientos", None),
            ("DELETE", "/admin/vehiculos/2/demos/43/movimientos/501", None),
            ("POST", "/admin/vehiculos/1/demos/42/movimientos", {"id_comando": 202, "orden": 2, "duracion_ms": 10, "pausa_ms": 0}),
        ]
        for method, path, body in cases:
            with self.subTest(path=path):
                self.send(method, path, body, 404)
        self.assertEqual(self.server.data, before)
        self.assertEqual(self.server.commits, 0)

    def test_missing_resource_update_and_delete_do_not_succeed(self):
        self.send("PUT", "/admin/vehiculos/999", dict(VEHICLE, activo=1), 404)
        self.send("DELETE", "/admin/vehiculos/999", expected=404)
        self.assertFalse(any(name in {"sp_actualizar_vehiculo", "sp_eliminar_vehiculo"} for name, _ in self.server.calls))

    def test_duplicate_codes_and_sequence_order_are_conflicts(self):
        self.send("POST", "/admin/vehiculos/1/comandos", dict(COMMAND, codigo=2), 409)
        self.send("PUT", "/admin/vehiculos/1/comandos/110", dict(COMMAND, codigo=2, activo=1), 409)
        self.send("POST", "/admin/vehiculos/1/demos/42/movimientos", {"id_comando": 102, "orden": 1, "duracion_ms": 0, "pausa_ms": 0}, 409)
        self.assertEqual(self.server.commits, 0)

    def test_reactivation_and_inactive_catalog_reads(self):
        self.send("PUT", "/admin/vehiculos/1", dict(VEHICLE, activo=0))
        self.assertEqual(self.send("GET", "/admin/vehiculos/1")["activo"], 0)
        self.send("POST", "/vehiculos/1/movimientos", {"id_comando": 102}, 409)
        self.send("PUT", "/admin/vehiculos/1", dict(VEHICLE, activo=1))
        self.send("PUT", "/admin/vehiculos/1/comandos/102", {"nombre": "ADELANTE", "codigo": 2, "descripcion": "", "activo": 0})
        self.assertEqual(self.send("GET", "/admin/vehiculos/1/comandos")[0]["activo"], 0)
        self.send("POST", "/vehiculos/1/movimientos", {"id_comando": 102}, 422)

    def test_admin_changes_do_not_modify_connected(self):
        before = deepcopy(self.server.data["estado"])
        self.send("PUT", "/admin/vehiculos/1", dict(VEHICLE, activo=1))
        self.send("PUT", "/admin/vehiculos/1/comandos/102", {"nombre": "ADELANTE", "codigo": 2, "descripcion": "", "activo": 1})
        self.assertEqual(self.server.data["estado"], before)
        self.assertEqual(self.send("GET", "/admin/vehiculos/1/estado")["conectado"], 0)

    def test_mysql_integrity_errors_are_sanitized_and_rolled_back(self):
        self.server.fail_procedure = "sp_crear_vehiculo"
        before = deepcopy(self.server.data)
        for errno, status in [(1062, 409), (1451, 409), (1452, 422), (1048, 422), (1406, 422), (1213, 409), (2006, 503)]:
            with self.subTest(errno=errno):
                self.server.fail_errno = errno
                response = self.send("POST", "/admin/vehiculos", VEHICLE, status)
                self.assertNotIn("privado", json.dumps(response))
                self.assertEqual(self.server.data, before)
        self.assertEqual(self.server.rollbacks, 7)

    def test_commit_failure_returns_error_and_persists_nothing(self):
        before = deepcopy(self.server.data)
        self.server.fail_commit = True
        self.send("POST", "/admin/vehiculos", VEHICLE, 503)
        self.assertEqual(self.server.data, before)
        self.assertEqual(self.server.rollbacks, 1)

    def test_delete_restrict_returns_conflict_and_keeps_related_records(self):
        before = deepcopy(self.server.data)
        for path in ["/admin/vehiculos/1", "/admin/vehiculos/1/comandos/102", "/admin/vehiculos/1/demos/42"]:
            self.send("DELETE", path, expected=409)
        self.assertEqual(self.server.data, before)

    def test_all_catalog_mutations_for_active_demo_vehicle_are_rejected(self):
        self.send("POST", "/vehiculos/1/demos", {"id_demo": 42}, 202)
        base = "/admin/vehiculos/1"
        step = {"id_comando": 102, "orden": 2, "duracion_ms": 0, "pausa_ms": 0}
        for method, path, body in [
            ("PUT", base, dict(VEHICLE, activo=0)), ("DELETE", base, None),
            ("POST", base + "/comandos", COMMAND),
            ("PUT", base + "/comandos/102", dict(COMMAND, activo=1)),
            ("DELETE", base + "/comandos/102", None),
            ("POST", base + "/demos", DEMO),
            ("PUT", base + "/demos/42", dict(DEMO, activo=1)),
            ("DELETE", base + "/demos/42", None),
            ("POST", base + "/demos/42/movimientos", step),
            ("PUT", base + "/demos/42/movimientos/501", step),
            ("DELETE", base + "/demos/42/movimientos/501", None),
        ]:
            with self.subTest(path=path):
                self.send(method, path, body, 409)
        self.send("GET", base)
        self.send("DELETE", "/vehiculos/1/demos/activa")
        self.send("PUT", base, dict(VEHICLE, activo=1))

    def test_successful_vehicle_delete_closes_its_websocket(self):
        vehicle = self.send("POST", "/admin/vehiculos", VEHICLE, 201)
        vehicle_id = vehicle["id_vehiculo"]
        with self.client.websocket_connect(f"/ws/vehiculos/{vehicle_id}", headers=self.auth) as socket:
            self.assertIsNone(socket.receive_json()["estado"])
            self.send("DELETE", f"/admin/vehiculos/{vehicle_id}", expected=204)
            with self.assertRaises(WebSocketDisconnect):
                socket.receive_json()

    def test_failed_vehicle_delete_does_not_close_websocket(self):
        with self.client.websocket_connect("/ws/vehiculos/1", headers=self.auth) as socket:
            socket.receive_json()
            self.send("DELETE", "/admin/vehiculos/1", expected=409)
            self.send("POST", "/vehiculos/1/movimientos", {"id_comando": 102})
            self.assertEqual(socket.receive_json()["tipo"], "movimiento_individual")

    def test_pydantic_bounds_and_extra_fields(self):
        for body in [dict(VEHICLE, nombre=" "), dict(VEHICLE, nombre="x" * 81), dict(VEHICLE, microcontrolador="x" * 51), dict(VEHICLE, conectado=1)]:
            self.send("POST", "/admin/vehiculos", body, 422)
        for body in [dict(COMMAND, nombre="x" * 61), dict(COMMAND, codigo=True), dict(COMMAND, codigo=2**31), dict(COMMAND, descripcion="x" * 256)]:
            self.send("POST", "/admin/vehiculos/1/comandos", body, 422)
        for body in [dict(VEHICLE, activo=2), dict(VEHICLE, activo=True), VEHICLE]:
            self.send("PUT", "/admin/vehiculos/1", body, 422)
        for step in [
            {"id_comando": 102, "orden": 0, "duracion_ms": 1, "pausa_ms": 0},
            {"id_comando": 102, "orden": 2, "duracion_ms": -1, "pausa_ms": 0},
            {"id_comando": 102, "orden": 2, "duracion_ms": 1, "pausa_ms": -1},
            {"id_comando": "102", "orden": 2, "duracion_ms": 1, "pausa_ms": 0},
        ]:
            self.send("POST", "/admin/vehiculos/1/demos/42/movimientos", step, 422)
        self.send("GET", "/admin/vehiculos/0", expected=422)
        self.send("GET", f"/admin/vehiculos/{2**31}", expected=422)
