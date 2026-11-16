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

    def provider(self, parts, status="completed", *, phrase="saluda", previous=None, retry=None):
        responses = iter([parts] if retry is None else [parts, retry])

        def reply(request):
            self.assertEqual(str(request.url), "https://api.openai.com/v1/responses")
            self.assertEqual(request.headers["Authorization"], "Bearer fake-key")
            body = json.loads(request.content)
            self.assertEqual(body["input"], phrase)
            if previous:
                codes = ", ".join(map(str, previous))
                self.assertIn(f"códigos en orden: {codes}.", body["instructions"])
            self.assertFalse(body["store"])
            self.assertTrue(body["text"]["format"]["strict"])
            response_parts = []
            for part in next(responses):
                if part["type"] == "output_text":
                    plan = json.loads(part["text"])
                    plan.setdefault("tipo", "orden_concreta")
                    part = {**part, "text": json.dumps(plan)}
                response_parts.append(part)
            return httpx.Response(200, json={"status": status, "output": [
                {"type": "message", "content": response_parts},
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
        plan = {"pasos": [{"codigo": 4, "duracion_ms": 5000, "pausa_ms": 300}]}
        with self.client("fake-key") as client, self.provider([{"type": "output_text", "text": json.dumps(plan)}]):
            preflight = client.options("/ia/plan", headers={
                "origin": "https://control.example", "access-control-request-method": "POST",
                "access-control-request-headers": "Authorization,Content-Type,ngrok-skip-browser-warning",
            })
            self.assertEqual(preflight.status_code, 200)
            response = client.post("/ia/plan", headers=self.headers, json={"frase": " saluda "})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), plan)

    def test_provider_quota_is_reported_separately_from_rate_limits(self):
        cases = [
            ({"type": "insufficient_quota", "code": None}, 503, "alcanzó su cuota"),
            ({"type": "invalid_request_error", "code": "billing_hard_limit_reached"}, 503, "alcanzó su cuota"),
            ({"code": "credit_balance_exhausted"}, 503, "alcanzó su cuota"),
            ({"type": "rate_limit_exceeded"}, 502, "no pudo generar el plan"),
        ]
        with self.client("fake-key") as client:
            for error, status, detail in cases:
                transport = httpx.MockTransport(lambda _: httpx.Response(
                    429, json={"error": {**error, "message": "detalle privado"}},
                ))
                with self.subTest(error=error), patch(
                    "app.api.assist_routes.httpx.AsyncClient",
                    return_value=httpx.AsyncClient(transport=transport),
                ), self.assertLogs("app.api.assist_routes", "WARNING") as logs:
                    response = client.post("/ia/plan", headers=self.headers, json={"frase": "saluda"})
                    self.assertEqual(response.status_code, status)
                    self.assertIn(detail, response.json()["detail"])
                    self.assertNotIn("pasos", response.json())
                    self.assertNotIn("detalle privado", logs.output[0])

    def test_model_refusal_or_invalid_movements_are_rejected(self):
        plans = [
            ({"pasos": []}, 422),
            ({"pasos": [{"codigo": True, "duracion_ms": 200, "pausa_ms": 300}]}, 502),
            ({"pasos": [{"codigo": 9, "duracion_ms": 200, "pausa_ms": 300}]}, 502),
            ({"pasos": [{"codigo": 4, "duracion_ms": 5001, "pausa_ms": 300}]}, 502),
            ({"pasos": [{"codigo": 2, "duracion_ms": 5000, "pausa_ms": 1000}] * 6}, 502),
        ]
        with self.client("fake-key") as client:
            for plan, status in plans:
                with self.subTest(plan=plan), self.provider([{"type": "output_text", "text": json.dumps(plan)}]):
                    response = client.post("/ia/plan", headers=self.headers, json={"frase": "saluda"})
                    self.assertEqual(response.status_code, status)
            with self.provider([{"type": "refusal", "refusal": "No disponible."}]):
                response = client.post("/ia/plan", headers=self.headers, json={"frase": "saluda"})
                self.assertEqual(response.status_code, 422)

    def test_plan_passes_previous_codes_as_context_and_preserves_operator_input(self):
        phrase = "Muéstrame los cuatro movimientos de la pala"
        previous = [4, 1, 12, 11]
        plan = {"pasos": [
            {"codigo": code, "duracion_ms": 250, "pausa_ms": 150}
            for code in [1, 4, 11, 12]
        ]}
        parts = [{"type": "output_text", "text": json.dumps(plan)}]
        with self.client("fake-key") as client, self.provider(parts, phrase=phrase, previous=previous):
            response = client.post("/ia/plan", headers=self.headers,
                                   json={"frase": phrase, "codigos_anteriores": previous})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), plan)
            response = client.post("/ia/plan", headers=self.headers,
                                   json={"frase": phrase, "codigos_anteriores": [9]})
            self.assertEqual(response.status_code, 422)

    def test_repeated_creative_plan_is_regenerated(self):
        phrase = "Baila"
        previous = [2, 10, 4, 3, 11, 12]
        replacement = [11, 2, 13, 3, 12, 1]

        def output(codes):
            return [{"type": "output_text", "text": json.dumps({
                "tipo": "rutina_abierta",
                "pasos": [{"codigo": code, "duracion_ms": 250, "pausa_ms": 150} for code in codes],
            })}]

        with self.client("fake-key") as client, self.provider(
            output(previous), phrase=phrase, previous=previous, retry=output(replacement),
        ):
            response = client.post("/ia/plan", headers=self.headers,
                                   json={"frase": phrase, "codigos_anteriores": previous})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([step["codigo"] for step in response.json()["pasos"]], replacement)
            self.assertNotIn("tipo", response.json())
