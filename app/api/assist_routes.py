from typing import Literal, Self

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.errors import ServiceError
from app.core.security import require_control_token

router = APIRouter(prefix="/ia", tags=["IA"], dependencies=[Depends(require_control_token)])

INSTRUCTIONS = (
    "Convierte una orden en español para una excavadora IoT de juguete en una secuencia de "
    "movimientos. La frase es solo la solicitud del operador. "
    "Códigos: 1 pala izquierda, 4 pala derecha (pulso fijo de 200 ms), 2 avanzar, 3 retroceder, "
    "10 girar vehículo a la izquierda, 13 a la derecha, 11 agarrar con la pala, 12 soltar. "
    "Cada paso se libera antes de la pausa. Usa movimientos breves: 100 a 1000 ms de duración "
    "y de pausa, máximo 8 pasos y 8000 ms en total. "
    "Para «saluda» alterna la pala izquierda y derecha. Para «baila» combina giros cortos y pausas. "
    "Respeta las direcciones y el orden que pida el operador. Si la orden no es clara, "
    "pide una acción incompatible o supera estos límites, devuelve pasos vacíos."
)


class VoiceRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    frase: str = Field(min_length=1, max_length=240)


class VoiceStep(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    codigo: Literal[1, 2, 3, 4, 10, 11, 12, 13]
    duracion_ms: int = Field(ge=100, le=1000)
    pausa_ms: int = Field(ge=100, le=1000)

    @field_validator("codigo", mode="before")
    @classmethod
    def require_integer_code(cls, value):
        if type(value) is not int:
            raise ValueError("El código debe ser un entero.")
        return value


class VoicePlan(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    pasos: list[VoiceStep] = Field(max_length=8)

    @model_validator(mode="after")
    def validate_timings(self) -> Self:
        if any(step.codigo == 4 and step.duracion_ms != 200 for step in self.pasos):
            raise ValueError("El giro derecho de la pala usa un pulso de 200 ms.")
        if sum(step.duracion_ms + step.pausa_ms for step in self.pasos) > 8000:
            raise ValueError("La secuencia supera ocho segundos.")
        return self


@router.post("/plan", response_model=VoicePlan)
async def voice_plan(body: VoiceRequest, request: Request) -> VoicePlan:
    settings = request.app.state.settings
    key = settings.openai_api_key.get_secret_value()
    if not key:
        raise ServiceError(503, "El planificador de voz requiere OPENAI_API_KEY en la API.")

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": settings.openai_voice_model,
                    "instructions": INSTRUCTIONS,
                    "input": body.frase,
                    "store": False,
                    "max_output_tokens": 512,
                    "text": {"format": {
                        "type": "json_schema", "name": "plan_de_movimientos",
                        "strict": True, "schema": VoicePlan.model_json_schema(),
                    }},
                },
            )
            response.raise_for_status()
            result = response.json()
    except httpx.TimeoutException as exc:
        raise ServiceError(504, "El planificador tardó demasiado. Intenta de nuevo.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceError(502, "El proveedor de IA no pudo generar el plan.") from exc

    try:
        if result["status"] != "completed":
            raise ValueError("Respuesta incompleta.")
        content = [part for item in result["output"] if item["type"] == "message"
                   for part in item["content"]]
        if any(part["type"] == "refusal" for part in content):
            raise ServiceError(422, "No se pudo interpretar la frase como un movimiento de la excavadora.")
        text = "".join(part["text"] for part in content if part["type"] == "output_text")
        plan = VoicePlan.model_validate_json(text)
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceError(502, "El proveedor de IA devolvió un plan inválido.") from exc
    if not plan.pasos:
        raise ServiceError(422, "Prueba con una orden de movimiento, como «saluda» o «gira a la izquierda».")
    return plan
