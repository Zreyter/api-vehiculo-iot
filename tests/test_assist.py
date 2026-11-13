import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fakes import MemoryRepository


class VoicePlanTests(unittest.TestCase):
    headers = {"Authorization": "Bearer TestAb12"}

    def client(self, key=""):
        settings = Settings(_env_file=None, control_token="TestAb12", openai_api_key=key,
                            browser_origins=["https://control.example"])
        return TestClient(create_app(settings, MemoryRepository()))

    def provider(self, parts, status="completed"):
        def reply(request):
            self.assertEqual(str(request.url), "https://api.openai.com/v1/responses")
            self.assertEqual(request.headers["Authorization"], "Bearer fake-key")
            body = json.loads(request.content)
            self.assertEqual(body["input"], "saluda")
            self.assertFalse(body["store"])
            self.assertTrue(body["text"]["format"]["strict"])
            return httpx.Response(200, json={"status": status, "output": [
                {"type": "message", "content": parts},
            ]})

        return patch("app.api.assist_routes.httpx.AsyncClient", return_value=httpx.AsyncClient(
            transport=httpx.MockTransport(reply),
        ))

    def test_plan_requires_control_token_and_server_key(self):
        with self.client() as client:
            self.assertEqual(client.post("/ia/plan", json={"frase": "saluda"}).status_code, 401)
            self.assertEqual(client.post("/ia/plan", headers=self.headers,
                                         json={"frase": "saluda"}).status_code, 503)
            self.assertEqual(client.post("/ia/plan", headers=self.headers,
                                         json={"frase": " "}).status_code, 422)

    def test_preflight_and_valid_model_response(self):
        plan = {"pasos": [{"codigo": 4, "duracion_ms": 200, "pausa_ms": 300}]}
        with self.client("fake-key") as client, self.provider([{"type": "output_text", "text": json.dumps(plan)}]):
            preflight = client.options("/ia/plan", headers={
                "origin": "https://control.example", "access-control-request-method": "POST",
                "access-control-request-headers": "Authorization,Content-Type,ngrok-skip-browser-warning",
            })
            self.assertEqual(preflight.status_code, 200)
            response = client.post("/ia/plan", headers=self.headers, json={"frase": " saluda "})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), plan)

    def test_model_refusal_or_invalid_movements_are_rejected(self):
        plans = [
            ({"pasos": []}, 422),
            ({"pasos": [{"codigo": True, "duracion_ms": 200, "pausa_ms": 300}]}, 502),
            ({"pasos": [{"codigo": 9, "duracion_ms": 200, "pausa_ms": 300}]}, 502),
            ({"pasos": [{"codigo": 4, "duracion_ms": 350, "pausa_ms": 300}]}, 502),
            ({"pasos": [{"codigo": 2, "duracion_ms": 1000, "pausa_ms": 1000}] * 5}, 502),
        ]
        with self.client("fake-key") as client:
            for plan, status in plans:
                with self.subTest(plan=plan), self.provider([{"type": "output_text", "text": json.dumps(plan)}]):
                    response = client.post("/ia/plan", headers=self.headers, json={"frase": "saluda"})
                    self.assertEqual(response.status_code, status)
            with self.provider([{"type": "refusal", "refusal": "No disponible."}]):
                response = client.post("/ia/plan", headers=self.headers, json={"frase": "saluda"})
                self.assertEqual(response.status_code, 422)
