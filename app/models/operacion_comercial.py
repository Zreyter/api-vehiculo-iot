from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Id = Annotated[int, Field(strict=True, gt=0, le=2147483647)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FichaUnidad(Entrada):
    nombre: str = Field(min_length=1, max_length=80)
    id_modelo: Id
    estado: Literal["disponible", "exhibicion", "inactivo", "sin_clasificar", "asignado"]


class Paso(Entrada):
    id_comando: Id
    duracion_ms: int = Field(strict=True, ge=1, le=60000)
    pausa_ms: int = Field(strict=True, ge=0, le=60000)


class Secuencia(Entrada):
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str = Field(default="", max_length=255)
    pasos: list[Paso] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def duracion_total(self):
        if sum(p.duracion_ms + p.pausa_ms for p in self.pasos) > 120000:
            raise ValueError("Duración máxima de dos minutos.")
        return self
