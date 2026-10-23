from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MovementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id_comando: int = Field(gt=0, strict=True)
    origen: str = Field(default="API", min_length=1, max_length=30)


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_demo: int = Field(gt=0, strict=True)


class DemoStep(BaseModel):
    id_demo_movimiento: int = Field(gt=0)
    orden: int = Field(gt=0)
    id_comando: int = Field(gt=0)
    comando: str
    codigo: int | str
    duracion_ms: int = Field(ge=0)
    pausa_ms: int = Field(ge=0)


class HistoryItem(BaseModel):
    id_historial: int
    id_vehiculo: int
    comando: str | None
    codigo: int | str | None
    fecha_hora: datetime
    origen: str


class Event(BaseModel):
    tipo: Literal[
        "estado", "movimiento_individual", "demo_iniciada", "demo_movimiento",
        "demo_finalizada", "demo_cancelada", "error",
    ]
    id_vehiculo: int
    id_comando: int | None = None
    comando: str | None = None
    codigo: int | str | None = None
    marca_temporal: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    estado: dict[str, Any] | None = None
    id_demo: int | None = None
    orden: int | None = None
    duracion_ms: int | None = None
    pausa_ms: int | None = None
    mensaje: str | None = None
    ejecucion_fisica_confirmada: bool = False
    salidas_aplicadas_confirmadas: bool = False


def state_event(kind: str, vehicle_id: int, state: dict | None, **kwargs) -> Event:
    state = state or {}
    return Event(
        tipo=kind, id_vehiculo=vehicle_id, estado=state or None,
        id_comando=state.get("id_comando"), comando=state.get("comando"),
        codigo=state.get("codigo"), **kwargs,
    )
