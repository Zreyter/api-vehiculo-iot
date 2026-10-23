from pydantic import BaseModel, ConfigDict, Field


class ControlLease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_id: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]+$")


class DeviceCommand(ControlLease):
    codigo: int = Field(ge=0, le=13, strict=True)
