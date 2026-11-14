from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

MIN_TIMED_MOVEMENT_MS = 100
MAX_TIMED_MOVEMENT_MS = 5000
TimedMovementDuration = Annotated[
    int, Field(ge=MIN_TIMED_MOVEMENT_MS, le=MAX_TIMED_MOVEMENT_MS, strict=True)
]


class ControlLease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_id: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]+$")


class ControlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pulso_ms: int | None = Field(default=None, strict=True)
    codigo: int = Field(ge=0, le=13, strict=True)
    intencion: int | None = Field(default=None, gt=0, le=9007199254740991, strict=True)


class TimedControlInput(ControlInput):
    duracion_ms: TimedMovementDuration | None = None


class DeviceCommand(ControlLease, ControlInput):
    pass
