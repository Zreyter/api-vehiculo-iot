import unittest

from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.main import create_app
from tests.fakes import MemoryRepository


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryRepository()
        self.app = create_app(
            Settings(_env_file=None, control_token=SecretStr("local-test-token")), self.repo
        )
        self.auth = {"Authorization": "Bearer local-test-token"}
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_individual_updates_state_history_and_both_clients(self):
        with self.client.websocket_connect("/ws/vehiculos/1", headers=self.auth) as a:
            with self.client.websocket_connect("/ws/vehiculos/1", headers=self.auth) as b:
                self.assertEqual(a.receive_json()["tipo"], "estado")
                self.assertEqual(b.receive_json()["estado"]["conectado"], 0)
                response = self.client.post("/vehiculos/1/movimientos", json={"id_comando": 110, "origen": "Postman"}, headers=self.auth)
                self.assertEqual(response.status_code, 200)
                first, second = a.receive_json(), b.receive_json()
                self.assertEqual(first, second)
                self.assertEqual(first["id_comando"], 110)
                self.assertEqual(first["codigo"], 10)
                self.assertFalse(first["ejecucion_fisica_confirmada"])
                history = self.client.get("/vehiculos/1/historial").json()
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]["origen"], "Postman")

    def test_demo_finishes_without_changing_history(self):
        before = self.client.get("/vehiculos/1/historial").json()
        with self.client.websocket_connect("/ws/vehiculos/1", headers=self.auth) as socket:
            socket.receive_json()
            response = self.client.post("/vehiculos/1/demos", json={"id_demo": 1}, headers=self.auth)
            self.assertEqual(response.status_code, 202)
            events = [socket.receive_json() for _ in range(4)]
            self.assertEqual([e["tipo"] for e in events], ["demo_iniciada", "demo_movimiento", "demo_movimiento", "demo_finalizada"])
            self.assertEqual([e["orden"] for e in events[1:3]], [1, 2])
            self.assertTrue(all(e["duracion_ms"] is not None for e in events[1:]))
        self.assertEqual(before, self.client.get("/vehiculos/1/historial").json())
        self.assertTrue(all(origin is None for _, _, origin in self.repo.calls))

    def test_events_are_isolated_by_vehicle(self):
        with self.client.websocket_connect("/ws/vehiculos/2", headers=self.auth) as socket:
            self.assertEqual(socket.receive_json()["id_vehiculo"], 2)
            self.client.post("/vehiculos/1/movimientos", json={"id_comando": 102}, headers=self.auth)
            self.client.post("/vehiculos/2/movimientos", json={"id_comando": 110}, headers=self.auth)
            # Si se filtrase el evento del vehículo 1, sería el primero en FIFO.
            self.assertEqual(socket.receive_json()["id_vehiculo"], 2)

    def test_auth_required_for_all_controls_and_websocket(self):
        for method, path, body in [
            ("post", "/vehiculos/1/movimientos", {"id_comando": 102}),
            ("post", "/vehiculos/1/demos", {"id_demo": 1}),
            ("delete", "/vehiculos/1/demos/activa", None),
        ]:
            response = self.client.request(method, path, json=body)
            self.assertEqual(response.status_code, 401)
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws/vehiculos/1"):
                pass

    def test_pydantic_limits_history_and_validates_body(self):
        for body in [{"id_comando": -1}, {"id_comando": True}, {"id_comando": 102, "conectado": 1}, {"id_comando": 102, "origen": "x" * 31}]:
            self.assertEqual(self.client.post("/vehiculos/1/movimientos", json=body, headers=self.auth).status_code, 422)
        self.assertEqual(self.client.get("/vehiculos/1/historial?limite=11").status_code, 422)
        for _ in range(12):
            self.client.post("/vehiculos/1/movimientos", json={"id_comando": 102}, headers=self.auth)
        self.assertEqual(len(self.client.get("/vehiculos/1/historial").json()), 10)

    def test_disconnect_removes_membership(self):
        with self.client.websocket_connect("/ws/vehiculos/1", headers=self.auth) as socket:
            socket.receive_json()
        async def room_size():
            import asyncio
            await asyncio.sleep(.01)
            return len(self.app.state.manager.rooms.get(1, ()))
        self.assertEqual(self.client.portal.call(room_size), 0)

    def test_swagger_describes_http_and_bearer(self):
        schema = self.client.get("/openapi.json").json()
        self.assertIn("HTTPBearer", schema["components"]["securitySchemes"])
        self.assertEqual(self.client.get("/docs").status_code, 200)

    def test_missing_mysql_password_returns_safe_error(self):
        with TestClient(create_app(Settings(_env_file=None, mysql_password=SecretStr("")))) as client:
            response = client.get("/vehiculos/1/historial")
            self.assertEqual(response.status_code, 503)
            self.assertIn("MYSQL_PASSWORD", response.json()["detail"])
