import base64
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.main import create_app
from tests.catalog_mysql import FakeMySQL
from tests.fakes import MemoryRepository


class SocketGatewayTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryRepository()
        for _ in range(12):
            self.repo.apply(1, 102, "Prueba")
        self.origin = "https://control.example"
        settings = Settings(_env_file=None, control_token="TestAb12",
                            device_token="device-test", browser_origins=[self.origin])
        self.client = TestClient(create_app(settings, self.repo))
        self.protocol = "token." + base64.urlsafe_b64encode(b"TestAb12").decode().rstrip("=")
        self.path = "/ws/vehiculos/1"

    def open_browser(self, role, origin=None):
        return self.client.websocket_connect(self.path, subprotocols=[role, self.protocol],
                                             headers={"origin": origin or self.origin})

    def test_swagger_uses_shared_favicon(self):
        with self.client:
            self.assertIn('href="/favicon.png"', self.client.get("/docs").text)
            icon = self.client.get("/favicon.png")
            self.assertEqual(icon.headers["content-type"], "image/png")
            self.assertTrue(icon.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_monitor_receives_history_and_real_device_frames(self):
        with self.client, self.open_browser("iot-monitor") as monitor:
            self.assertEqual(monitor.receive_json()["tipo"], "estado")
            history = monitor.receive_json()["movimientos"]
            self.assertEqual([item["id_historial"] for item in history], list(range(12, 2, -1)))
            with self.client.websocket_connect(self.path, subprotocols=["iot-device"],
                    headers={"authorization": "Bearer device-test"}) as device:
                greeting = device.receive_json()
                device.send_json({"tipo": "listo", "modo": "wifi", "codigo": 0,
                                  "sesion": greeting["sesion"], "permiso": "privado"})
                trace = monitor.receive_json()
                self.assertEqual(trace["trama"], {"tipo": "saludo"})
                trace = monitor.receive_json()
                self.assertEqual(trace["direccion"], "esp8266 → api")
                self.assertEqual(trace["trama"], {"tipo": "listo", "codigo": 0, "modo": "wifi"})

    def test_only_authorized_browser_or_device_can_enter(self):
        with self.client:
            with self.assertRaises(WebSocketDisconnect):
                with self.open_browser("iot-control", "https://otro.example"):
                    pass
            with self.assertRaises(WebSocketDisconnect):
                with self.client.websocket_connect(self.path, subprotocols=["iot-device"],
                        headers={"authorization": "Bearer TestAb12"}):
                    pass
            with self.open_browser("iot-control") as control:
                self.assertEqual(control.receive_json()["tipo"], "estado")
                control.send_json({"id": 1, "accion": "orden", "datos": {"codigo": 2}})
                self.assertEqual(control.receive_json()["estado_http"], 409)
                control.send_json({"id": 2, "accion": "estado"})
                self.assertFalse(control.receive_json()["datos"]["conectado"])

    def test_control_order_reaches_device_and_monitor_and_release_clears_outputs(self):
        db = FakeMySQL()
        db.data["comandos"][104] = dict(id_comando=104, id_vehiculo=1, nombre="PALA_DERECHA",
                                       codigo=4, descripcion="", activo=1)
        settings = Settings(_env_file=None, control_token="TestAb12", device_token="device-test",
                            browser_origins=[self.origin], mysql_password="local-fake")
        self.client = TestClient(create_app(settings))

        def take(socket, matches):
            for _ in range(20):
                frame = socket.receive_json()
                if matches(frame):
                    return frame
            self.fail("El canal no entregó la trama esperada.")

        with (patch("app.core.database.mysql.connector.connect", db.connect), self.client,
              self.open_browser("iot-monitor") as monitor,
              self.client.websocket_connect(self.path, subprotocols=["iot-device"],
                  headers={"authorization": "Bearer device-test"}) as device,
              self.open_browser("iot-control") as control):
            session = device.receive_json()["sesion"]

            def device_reply(kind, **values):
                device.send_json(dict(tipo=kind, sesion=session, demo_temporizada=True, **values))

            def confirm_stop(frame):
                self.assertEqual(frame["tipo"], "parar")
                device_reply("ack", seq=frame["seq"], codigo=0, modo="wifi", ok=True)

            def prepare(frame):
                device_reply("preparado", seq=frame["seq"], permiso="nonce-de-prueba")

            device_reply("listo", modo="wifi", codigo=0)
            take(monitor, lambda f: f.get("trama", {}).get("tipo") == "listo")
            control.send_json({"id": 1, "accion": "activar"})
            confirm_stop(device.receive_json())
            prefetch = device.receive_json()
            self.assertEqual(prefetch["tipo"], "preparar")
            prepare(prefetch)
            self.assertTrue(take(control, lambda f: f.get("id") == 1)["ok"])

            control.send_json({"id": 2, "accion": "orden", "datos": {"codigo": 4, "intencion": 1}})
            order = device.receive_json()
            if order["tipo"] == "preparar":
                prepare(order)
                order = device.receive_json()
            self.assertEqual((order["tipo"], order["codigo"], order["demo_ms"]), ("orden", 4, 200))
            device_reply("ack", seq=order["seq"], codigo=4, modo="wifi", ok=True, duracion_ms=200)
            self.assertTrue(take(control, lambda f: f.get("id") == 2)["ok"])

            control.send_json({"id": 3, "accion": "liberar"})
            confirm_stop(take(device, lambda f: f["tipo"] == "parar"))
            self.assertTrue(take(control, lambda f: f.get("id") == 3)["datos"]["salidas_confirmadas"])

            traced_order = take(monitor, lambda f: f.get("trama", {}).get("tipo") == "orden")["trama"]
            self.assertEqual(traced_order, {"tipo": "orden", "seq": order["seq"], "codigo": 4,
                                            "demo_ms": 200, "ttl_ms": order["ttl_ms"]})
            ack = take(monitor, lambda f: f.get("trama", {}).get("seq") == order["seq"])["trama"]
            self.assertEqual((ack["tipo"], ack["codigo"], ack["ok"]), ("ack", 4, True))
            movement = take(monitor, lambda f: f["tipo"] == "movimiento_individual")
            self.assertEqual((movement["codigo"], movement["comando"]), (4, "PALA_DERECHA"))
