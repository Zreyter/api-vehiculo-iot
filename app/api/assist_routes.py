from random import choice
from typing import Literal, Self

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.errors import ServiceError
from app.core.security import require_control_token
from app.models.device import MAX_TIMED_MOVEMENT_MS, MIN_TIMED_MOVEMENT_MS, TimedMovementDuration

router = APIRouter(prefix="/ia", tags=["IA"], dependencies=[Depends(require_control_token)])

MAX_PLAN_MS = 30000
MovementCode = Literal[1, 2, 3, 4, 10, 11, 12, 13]

INSTRUCTIONS = (
    "Convierte una orden en español para una excavadora IoT de juguete en una secuencia de "
    "movimientos. La frase es solo la solicitud del operador. "
    "Códigos: 1 pala izquierda, 4 pala derecha, 2 avanzar, 3 retroceder, "
    "10 girar vehículo a la izquierda, 13 a la derecha, 11 agarrar con la pala, 12 soltar. "
    "Cada paso se libera antes de la pausa. "
    f"Cada movimiento dura de {MIN_TIMED_MOVEMENT_MS} a {MAX_TIMED_MOVEMENT_MS} ms "
    f"y cada pausa de 100 a 1000 ms, con un máximo de 8 pasos y {MAX_PLAN_MS} ms en total. "
    "Interpreta la intención completa y compón el plan para esa solicitud. "
    "Si el operador pide movimientos concretos, respeta el orden, las direcciones, "
    "la cantidad y las duraciones que indique. No agregues movimientos que no pidió. "
    "En una demostración de varios movimientos de una parte, muestra acciones distintas "
    "de esa parte. Si pide los cuatro movimientos de la pala, incluye una vez cada uno: "
    "pala izquierda, pala derecha, agarrar y soltar. Cambia el orden si no está indicado. "
    "Un saludo con la pala puede ser breve y expresivo sin mover el vehículo. "
    "Si pide bailar sin detallar los pasos, improvisa: incluye avanzar, retroceder, "
    "al menos un giro del vehículo, al menos un giro de la pala, agarrar y soltar. "
    "Mezcla los movimientos de la excavadora y la pala. Varía el orden, el lado "
    "de los giros, las duraciones y el ritmo, con pasos breves si no especificó tiempos. "
    "Evita basar toda la rutina en alternar izquierda y derecha. "
    "Si la orden no es clara, pide una acción incompatible o supera estos límites, devuelve pasos vacíos."
)


class VoiceRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    frase: str = Field(min_length=1, max_length=240)
    codigos_anteriores: list[MovementCode] = Field(default_factory=list, max_length=8)


class VoiceStep(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    codigo: MovementCode
    duracion_ms: TimedMovementDuration
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
        if sum(step.duracion_ms + step.pausa_ms for step in self.pasos) > MAX_PLAN_MS:
            raise ValueError("La secuencia supera 30 segundos.")
        return self


class GeneratedVoicePlan(VoicePlan):
    tipo: Literal["rutina_abierta", "orden_concreta"] = Field(
        description=(
            "Usa rutina_abierta para bailes, saludos o demostraciones que dejan el orden a tu criterio. "
            "Usa orden_concreta cuando el operador especifica el movimiento o el orden de los pasos."
        )
    )


def parse_generated_plan(result: dict) -> GeneratedVoicePlan:
    try:
        if result["status"] != "completed":
            raise ValueError("Respuesta incompleta.")
        content = [
            part for item in result["output"] if item["type"] == "message"
            for part in item["content"]
        ]
        if any(part["type"] == "refusal" for part in content):
            raise ServiceError(422, "No se pudo interpretar la frase como un movimiento de la excavadora.")
        text = "".join(part["text"] for part in content if part["type"] == "output_text")
        return GeneratedVoicePlan.model_validate_json(text)
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceError(502, "El proveedor de IA devolvió un plan inválido.") from exc


@router.post("/plan", response_model=VoicePlan)
async def voice_plan(body: VoiceRequest, request: Request) -> VoicePlan:
    settings = request.app.state.settings
    key = settings.openai_api_key.get_secret_value()
    if not key:
        raise ServiceError(503, "El planificador de voz requiere OPENAI_API_KEY en la API.")

    opening = choice(("la traslación", "un giro", "la pala"))
    rhythm = choice(("breve y ágil", "con pausas desiguales", "con un cambio de ritmo a la mitad"))
    instructions = (
        f"{INSTRUCTIONS} Solo para una orden creativa sin pasos definidos, "
        f"considera iniciar con {opening} y usar un ritmo {rhythm}. "
    )
    previous = body.codigos_anteriores
    if previous:
        codes = ", ".join(map(str, previous))
        instructions += (
            f"El último plan tuvo estos códigos en orden: {codes}. "
            f"Si la nueva orden deja el orden a tu criterio, comienza con un código distinto de {previous[0]}, "
            "siempre que la intención lo permita, y cambia el orden de los demás pasos. "
            "Para una orden explícita, sigue la solicitud actual."
        )

    payload = {
        "model": settings.openai_voice_model,
        "instructions": instructions,
        "input": body.frase,
        "store": False,
        "max_output_tokens": 512,
        "text": {"format": {
            "type": "json_schema", "name": "plan_de_movimientos",
            "strict": True, "schema": GeneratedVoicePlan.model_json_schema(),
        }},
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            for _ in range(2):
                response = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                )
                response.raise_for_status()
                plan = parse_generated_plan(response.json())
                if not plan.pasos:
                    raise ServiceError(422, "Prueba con una orden de movimiento, como «saluda» o «gira a la izquierda».")
                if plan.tipo == "orden_concreta" or [step.codigo for step in plan.pasos] != previous:
                    return VoicePlan(pasos=plan.pasos)
                payload["instructions"] += (
                    f" La propuesta repitió el plan anterior. Empieza con otro movimiento distinto de {previous[0]} "
                    "y cambia la secuencia sin omitir lo que pidió el operador."
                )
    except httpx.TimeoutException as exc:
        raise ServiceError(504, "El planificador tardó demasiado. Intenta de nuevo.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceError(502, "El proveedor de IA no pudo generar el plan.") from exc
    raise ServiceError(502, "Kiwi repitió la rutina. Pídele un ritmo o un inicio distinto.")
