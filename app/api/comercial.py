from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.comercial import (
    Acceso, ClienteEdicion, ClienteGuardado, ClienteNuevo, Inventario, Modelo, ModeloGuardado, Sesion, Unidad,
)

router = APIRouter(prefix="/comercial", tags=["Administración comercial"])
bearer = HTTPBearer(auto_error=False, scheme_name="SesionComercial")


def sesion(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if not credentials:
        raise HTTPException(401, "Inicia una sesión comercial.", headers={"WWW-Authenticate": "Bearer"})
    return credentials.credentials


Token = Annotated[str, Depends(sesion)]
Busqueda = Annotated[str, Query(max_length=80)]
Inicio = Annotated[int, Query(ge=0)]
Limite = Annotated[int, Query(ge=1, le=100)]


@router.post("/acceso", response_model=Sesion, responses={401: {}, 429: {}})
def acceso(body: Acceso, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.comercial.acceso(body.correo, body.clave.get_secret_value())


@router.delete("/sesion", status_code=204)
def salir(request: Request, token: Token):
    request.app.state.comercial.salir(token)
    return Response(status_code=204)


@router.get("/resumen", response_model=Inventario, responses={401: {}, 403: {}})
def resumen(request: Request, token: Token):
    return request.app.state.comercial.resumen(token)


@router.get("/unidades", response_model=list[Unidad])
def unidades(request: Request, token: Token, buscar: Busqueda = "", inicio: Inicio = 0, limite: Limite = 50):
    return request.app.state.comercial.unidades(token, buscar, inicio, limite)


@router.get("/modelos", response_model=list[ModeloGuardado])
def modelos(request: Request, token: Token, buscar: Busqueda = "", inicio: Inicio = 0, limite: Limite = 50):
    return request.app.state.comercial.modelos(token, buscar, inicio, limite)


@router.post("/modelos", response_model=ModeloGuardado, status_code=201, responses={409: {}})
def crear_modelo(body: Modelo, request: Request, token: Token):
    return request.app.state.comercial.guardar_modelo(token, body)


@router.put("/modelos/{id_modelo}", response_model=ModeloGuardado, responses={404: {}, 409: {}})
def actualizar_modelo(id_modelo: Annotated[int, Path(gt=0)], body: Modelo, request: Request, token: Token):
    return request.app.state.comercial.guardar_modelo(token, body, id_modelo)


@router.get("/clientes", response_model=list[ClienteGuardado])
def clientes(request: Request, token: Token, buscar: Busqueda = "", inicio: Inicio = 0, limite: Limite = 50):
    return request.app.state.comercial.clientes(token, buscar, inicio, limite)


@router.post("/clientes", response_model=ClienteGuardado, status_code=201, responses={409: {}})
def crear_cliente(body: ClienteNuevo, request: Request, token: Token):
    return request.app.state.comercial.guardar_cliente(token, body)


@router.put("/clientes/{id_usuario}", response_model=ClienteGuardado, responses={404: {}, 409: {}})
def editar_cliente(id_usuario: Annotated[int, Path(gt=0)], body: ClienteEdicion, request: Request, token: Token):
    return request.app.state.comercial.guardar_cliente(token, body, id_usuario)
