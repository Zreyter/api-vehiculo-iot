from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

MAX_INT = 2_147_483_647
Identifier = Annotated[int, Field(strict=True, gt=0, le=MAX_INT)]
Active = Annotated[int, Field(strict=True, ge=0, le=1)]
Name80 = Annotated[str, Field(min_length=1, max_length=80)]
Description = Annotated[str, Field(max_length=255)]


class CatalogInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VehicleCreate(CatalogInput):
    nombre: Name80
    modelo: Annotated[str, Field(min_length=1, max_length=80)]
    descripcion: Description = ""
    microcontrolador: Annotated[str, Field(min_length=1, max_length=50)]


class VehicleUpdate(VehicleCreate):
    activo: Active


class CommandCreate(CatalogInput):
    nombre: Annotated[str, Field(min_length=1, max_length=60)]
    codigo: Annotated[int, Field(strict=True, ge=-2_147_483_648, le=MAX_INT)]
    descripcion: Description = ""


class CommandUpdate(CommandCreate):
    activo: Active


class DemoCreate(CatalogInput):
    nombre: Name80
    descripcion: Description = ""


class DemoUpdate(DemoCreate):
    activo: Active


class DemoMovementInput(CatalogInput):
    id_comando: Identifier
    orden: Identifier
    duracion_ms: Annotated[int, Field(strict=True, ge=0, le=MAX_INT)]
    pausa_ms: Annotated[int, Field(strict=True, ge=0, le=MAX_INT)]


class VehicleRecord(BaseModel):
    id_vehiculo: int
    nombre: str
    modelo: str | None
    descripcion: str | None
    microcontrolador: str | None
    fecha_registro: datetime
    activo: int


class CommandRecord(BaseModel):
    id_comando: int
    id_vehiculo: int
    nombre: str
    codigo: int
    descripcion: str | None
    activo: int


class DemoRecord(BaseModel):
    id_demo: int
    id_vehiculo: int
    nombre: str
    descripcion: str | None
    activo: int


class DemoMovementRecord(BaseModel):
    id_demo_movimiento: int
    id_demo: int
    orden: int
    id_comando: int
    comando: str
    codigo: int
    duracion_ms: int
    pausa_ms: int


class StateRecord(BaseModel):
    id_vehiculo: int
    vehiculo: str
    id_comando: int | None
    comando: str | None
    codigo: int | None
    conectado: int | None
    fecha_actualizacion: datetime
