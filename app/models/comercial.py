from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints


class Acceso(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]
    clave: SecretStr = Field(min_length=1, max_length=256)


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str = Field(default="", max_length=255)
    activo: bool = Field(default=True, strict=True)


class ModeloGuardado(Modelo):
    activo: bool
    id_modelo: int


class Sesion(BaseModel):
    token: str
    nombre: str
    rol: str


class Unidad(BaseModel):
    id_vehiculo: int
    nombre: str
    modelo: str
    estado: str


class UnidadAdministrada(Unidad):
    id_modelo: int | None
    conectado: bool = False
    id_usuario: int | None
    propietario: str | None


class Asignacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_usuario: Annotated[int, Field(gt=0, strict=True)] | None
    anterior: Annotated[int, Field(gt=0, strict=True)] | None


class Inventario(BaseModel):
    total_modelos: int
    total_unidades: int
    asignadas: int
    exhibicion: int
    sin_clasificar: int
    clientes: int
    demos: int


class ClienteBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nombre: str = Field(min_length=1, max_length=120)
    correo: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ClienteNuevo(ClienteBase):
    clave: SecretStr = Field(min_length=12, max_length=256)


class ClienteEdicion(ClienteBase):
    activo: bool = Field(strict=True)


class ClienteGuardado(ClienteBase):
    id_usuario: int
    activo: bool
