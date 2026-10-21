import base64
import unittest

from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.main import create_app
from tests.fakes import MemoryRepository


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            Settings(_env_file=None, control_token=SecretStr("panel-test-token")),
            MemoryRepository(),
        )
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        encoded = base64.urlsafe_b64encode(b"panel-test-token").decode().rstrip("=")
        self.protocols = ["iot", "token." + encoded]

    def test_panel_assets_and_existing_api_contract(self):
        self.assertEqual(self.client.get("/panel", follow_redirects=False).headers["location"], "/panel/")
        page = self.client.get("/panel/")
        self.assertEqual(page.status_code, 200)
        self.assertIn('src="./panel.js"', page.text)
        self.assertIn('href="./panel.css"', page.text)
        self.assertIn("script-src 'self'", page.headers["content-security-policy"])
        for path, content_type in [("panel.js", "javascript"), ("panel.css", "text/css")]:
            response = self.client.get("/panel/" + path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(content_type, response.headers["content-type"])
        self.assertEqual(self.client.get("/panel/.env").status_code, 404)
        self.assertEqual(self.client.get("/docs").status_code, 200)
        self.assertEqual(self.client.post("/vehiculos/1/movimientos", json={"id_comando": 102}).status_code, 401)

    def test_browser_and_postman_receive_same_movement(self):
        with self.client.websocket_connect(
            "/panel/ws/vehiculos/1", subprotocols=self.protocols,
            headers={"Origin": "http://testserver"},
        ) as browser:
            self.assertEqual(browser.accepted_subprotocol, "iot")
            self.assertEqual(browser.receive_json()["tipo"], "estado")
            auth = {"Authorization": "Bearer panel-test-token"}
            with self.client.websocket_connect("/ws/vehiculos/1", headers=auth) as postman:
                postman.receive_json()
                response = self.client.post(
                    "/vehiculos/1/movimientos", headers=auth,
                    json={"id_comando": 102, "origen": "Panel web"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(browser.receive_json(), postman.receive_json())
                history = self.client.get("/vehiculos/1/historial").json()
                self.assertEqual(history[0]["origen"], "Panel web")

    def test_browser_socket_rejects_invalid_auth_origin_and_vehicle(self):
        cases = [
            ([], "http://testserver", 1),
            (["iot", "token.aW52YWxpZA"], "http://testserver", 1),
            (["iot", "token.!!!"], "http://testserver", 1),
            (self.protocols, "https://otro.example", 1),
            (self.protocols, "", 1),
            (self.protocols, "http://testserver", 0),
            (self.protocols, "http://testserver", 999),
        ]
        for protocols, origin, vehicle in cases:
            with self.subTest(protocols=protocols, origin=origin, vehicle=vehicle):
                with self.assertRaises(WebSocketDisconnect):
                    with self.client.websocket_connect(
                        f"/panel/ws/vehiculos/{vehicle}", subprotocols=protocols,
                        headers={"Origin": origin},
                    ):
                        pass

    def test_browser_socket_finishes_demo_without_adding_history(self):
        before = self.client.get("/vehiculos/1/historial").json()
        with self.client.websocket_connect(
            "/panel/ws/vehiculos/1", subprotocols=self.protocols,
            headers={"Origin": "http://testserver"},
        ) as browser:
            browser.receive_json()
            response = self.client.post(
                "/vehiculos/1/demos", json={"id_demo": 1},
                headers={"Authorization": "Bearer panel-test-token"},
            )
            self.assertEqual(response.status_code, 202)
            events = [browser.receive_json()["tipo"] for _ in range(4)]
            self.assertEqual(events, ["demo_iniciada", "demo_movimiento", "demo_movimiento", "demo_finalizada"])
        self.assertEqual(before, self.client.get("/vehiculos/1/historial").json())
