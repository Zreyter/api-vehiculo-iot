import asyncio
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, Path, Request

from app.api.comercial import Busqueda, Inicio, Limite, Token
from app.core.errors import ServiceError
from app.models.operacion_comercial import FichaUnidad, Secuencia

router = APIRouter(tags=["Operación comercial"])
Identificador = Annotated[int, Path(gt=0)]


@router.get("/salud")
async def salud(request: Request):
    """Comprueba la API y ejecuta SELECT 1 en su conexión RDS. Comparte la lectura durante cinco segundos."""
    app=request.app.state
    async with app.salud_lock:
        if monotonic() >= app.salud_vence:
            try:
                app.salud_rds = await asyncio.to_thread(app.comercial.salud)
            except ServiceError:
                app.salud_rds = False
            app.salud_vence = monotonic()+5
    return {"api":"disponible","rds":"disponible" if app.salud_rds else "no_disponible"}


@router.get("/comercial/auditoria")
def auditoria(request: Request, token: Token, buscar: Busqueda="", inicio: Inicio=0, limite: Limite=50):
    return request.app.state.comercial.auditoria(token,buscar,inicio,limite)


@router.post("/comercial/unidades",status_code=201)
def alta(body: FichaUnidad, request: Request, token: Token):
    return request.app.state.comercial.guardar_unidad(token,body)


def exigir_reposo(app, unidad):
    coord = app.device_service.coordinator
    if coord.remote_busy(unidad) or unidad in coord.active:
        raise ServiceError(409,"Termina la operación en curso antes de editar la unidad.")


@router.put("/comercial/unidades/{unidad}")
async def editar(unidad: Identificador, body: FichaUnidad, request: Request, token: Token):
    app=request.app.state
    await asyncio.to_thread(app.comercial.verificar_admin,token)
    async with app.permisos.cambio(unidad), app.device_service.coordinator.lock(unidad):
        exigir_reposo(app,unidad)
        return await asyncio.to_thread(app.comercial.guardar_unidad,token,body,unidad)


@router.get("/comercial/unidades/{unidad}/secuencias")
def catalogo(unidad: Identificador, request: Request, token: Token):
    return request.app.state.comercial.demos_editor(token,unidad)


@router.get("/comercial/unidades/{unidad}/secuencias/{demo}")
def pasos(unidad: Identificador, demo: Identificador, request: Request, token: Token):
    return request.app.state.comercial.pasos_editor(token,unidad,demo)


async def guardar(request, token, unidad, body, demo=None):
    app=request.app.state
    async with app.permisos.operacion(unidad), app.device_service.coordinator.lock(unidad):
        exigir_reposo(app,unidad)
        return await asyncio.to_thread(app.comercial.guardar_demo,token,unidad,body,demo)


@router.post("/comercial/unidades/{unidad}/secuencias",status_code=201)
async def crear_secuencia(unidad: Identificador, body: Secuencia, request: Request, token: Token):
    return await guardar(request,token,unidad,body)


@router.put("/comercial/unidades/{unidad}/secuencias/{demo}")
async def editar_secuencia(unidad: Identificador, demo: Identificador, body: Secuencia, request: Request, token: Token):
    return await guardar(request,token,unidad,body,demo)


@router.delete("/comercial/unidades/{unidad}/secuencias/{demo}")
async def archivar(unidad: Identificador, demo: Identificador, request: Request, token: Token):
    return await guardar(request,token,unidad,None,demo)
