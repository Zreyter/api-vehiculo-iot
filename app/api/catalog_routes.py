from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from app.core.security import require_control_token
from app.models.catalog import (
    MAX_INT, CommandCreate, CommandRecord, CommandUpdate, DemoCreate,
    DemoMovementInput, DemoMovementRecord, DemoRecord, DemoUpdate,
    StateRecord, VehicleCreate, VehicleRecord, VehicleUpdate,
)

ObjectId = Annotated[int, Path(gt=0, le=MAX_INT)]
router = APIRouter(
    prefix="/admin", dependencies=[Depends(require_control_token)],
    responses={
        401: {"description": "Token inválido o ausente"},
        404: {"description": "Recurso inexistente o ajeno al padre de la ruta"},
        409: {"description": "DEMO activa, código/orden duplicado o restricción de integridad"},
        422: {"description": "Datos inválidos"},
        503: {"description": "MySQL o configuración no disponible"},
    },
)
DELETE_NOTE = "Elimina físicamente mediante el SP existente; no cambia activo a 0. Las relaciones y posibles cascadas son las de tu esquema MySQL. No se ejecuta durante las pruebas automatizadas contra datos reales."
UPDATE_NOTE = "PUT exige los campos del recurso y activo (0 o 1). Permite reactivar registros. Rechaza cambios durante una DEMO activa para ese vehículo."


@router.get("/vehiculos", response_model=list[VehicleRecord], tags=["Administración: vehículos"], summary="Listar vehículos", description="sp_obtener_vehiculos(), sin parámetros; incluye activos e inactivos.")
async def vehicles(request: Request):
    return await request.app.state.catalog_service.read("vehicles")


@router.get("/vehiculos/{id_vehiculo}", response_model=VehicleRecord, tags=["Administración: vehículos"], summary="Consultar un vehículo")
async def vehicle(id_vehiculo: ObjectId, request: Request):
    return await request.app.state.catalog_service.read("vehicle", id_vehiculo)


@router.post("/vehiculos", response_model=VehicleRecord, status_code=201, tags=["Administración: vehículos"], summary="Crear vehículo", description="sp_crear_vehiculo(nombre, modelo, descripcion, microcontrolador). Devuelve el recurso confirmado en BD. activo y fecha_registro los determina el esquema existente.")
async def create_vehicle(body: VehicleCreate, request: Request):
    return await request.app.state.catalog_service.write("create_vehicle", None, body)


@router.put("/vehiculos/{id_vehiculo}", response_model=VehicleRecord, tags=["Administración: vehículos"], summary="Actualizar vehículo", description=UPDATE_NOTE)
async def update_vehicle(id_vehiculo: ObjectId, body: VehicleUpdate, request: Request):
    return await request.app.state.catalog_service.write("update_vehicle", id_vehiculo, body)


@router.delete("/vehiculos/{id_vehiculo}", status_code=204, tags=["Administración: vehículos"], summary="Eliminar vehículo", description=DELETE_NOTE)
async def delete_vehicle(id_vehiculo: ObjectId, request: Request):
    await request.app.state.catalog_service.write("delete_vehicle", id_vehiculo)
    return Response(status_code=204)


@router.get("/vehiculos/{id_vehiculo}/estado", response_model=StateRecord | None, tags=["Administración: vehículos"], summary="Consultar estado", description="Lee sp_obtener_estado; no modifica conectado. Devuelve null si aún no existe un estado.")
async def state(id_vehiculo: ObjectId, request: Request):
    return await request.app.state.catalog_service.read("state", id_vehiculo)


@router.get("/vehiculos/{id_vehiculo}/comandos", response_model=list[CommandRecord], tags=["Administración: comandos"], summary="Listar comandos del vehículo")
async def commands(id_vehiculo: ObjectId, request: Request):
    return await request.app.state.catalog_service.read("commands", id_vehiculo)


@router.post("/vehiculos/{id_vehiculo}/comandos", response_model=CommandRecord, status_code=201, tags=["Administración: comandos"], summary="Crear comando", description="Crea un comando relacionado con el vehículo. codigo es un INT independiente del ID y debe ser único dentro de este vehículo. activo lo determina el esquema existente.")
async def create_command(id_vehiculo: ObjectId, body: CommandCreate, request: Request):
    return await request.app.state.catalog_service.write("create_command", id_vehiculo, body)


@router.put("/vehiculos/{id_vehiculo}/comandos/{id_comando}", response_model=CommandRecord, tags=["Administración: comandos"], summary="Actualizar comando", description=UPDATE_NOTE)
async def update_command(id_vehiculo: ObjectId, id_comando: ObjectId, body: CommandUpdate, request: Request):
    return await request.app.state.catalog_service.write("update_command", id_vehiculo, id_comando, body)


@router.delete("/vehiculos/{id_vehiculo}/comandos/{id_comando}", status_code=204, tags=["Administración: comandos"], summary="Eliminar comando", description=DELETE_NOTE)
async def delete_command(id_vehiculo: ObjectId, id_comando: ObjectId, request: Request):
    await request.app.state.catalog_service.write("delete_command", id_vehiculo, id_comando)
    return Response(status_code=204)


@router.get("/vehiculos/{id_vehiculo}/demos", response_model=list[DemoRecord], tags=["Administración: DEMO"], summary="Listar DEMO del vehículo")
async def demos(id_vehiculo: ObjectId, request: Request):
    return await request.app.state.catalog_service.read("demos", id_vehiculo)


@router.post("/vehiculos/{id_vehiculo}/demos", response_model=DemoRecord, status_code=201, tags=["Administración: DEMO"], summary="Crear DEMO en el catálogo", description="Crea la definición sin iniciar su ejecución. Agrega sus pasos con el endpoint de movimientos. activo lo determina el esquema existente. La ejecución permanece en POST /vehiculos/{id}/demos.")
async def create_demo(id_vehiculo: ObjectId, body: DemoCreate, request: Request):
    return await request.app.state.catalog_service.write("create_demo", id_vehiculo, body)


@router.put("/vehiculos/{id_vehiculo}/demos/{id_demo}", response_model=DemoRecord, tags=["Administración: DEMO"], summary="Actualizar DEMO", description=UPDATE_NOTE)
async def update_demo(id_vehiculo: ObjectId, id_demo: ObjectId, body: DemoUpdate, request: Request):
    return await request.app.state.catalog_service.write("update_demo", id_vehiculo, id_demo, body)


@router.delete("/vehiculos/{id_vehiculo}/demos/{id_demo}", status_code=204, tags=["Administración: DEMO"], summary="Eliminar DEMO del catálogo", description=DELETE_NOTE + " No equivale a cancelar una ejecución.")
async def delete_demo(id_vehiculo: ObjectId, id_demo: ObjectId, request: Request):
    await request.app.state.catalog_service.write("delete_demo", id_vehiculo, id_demo)
    return Response(status_code=204)


@router.get("/vehiculos/{id_vehiculo}/demos/{id_demo}/movimientos", response_model=list[DemoMovementRecord], tags=["Administración: movimientos DEMO"], summary="Listar movimientos de una DEMO")
async def movements(id_vehiculo: ObjectId, id_demo: ObjectId, request: Request):
    return await request.app.state.catalog_service.read("movements", id_vehiculo, id_demo)


@router.post("/vehiculos/{id_vehiculo}/demos/{id_demo}/movimientos", response_model=DemoMovementRecord, status_code=201, tags=["Administración: movimientos DEMO"], summary="Agregar movimiento a DEMO", description="Valida que DEMO y comando pertenezcan al vehículo, orden positivo sin duplicados y duración/pausa no negativas. Recupera el ID con LAST_INSERT_ID() en la misma conexión porque el SP no lo devuelve. No ejecuta el movimiento ni registra historial.")
async def create_movement(id_vehiculo: ObjectId, id_demo: ObjectId, body: DemoMovementInput, request: Request):
    return await request.app.state.catalog_service.write("create_movement", id_vehiculo, id_demo, body)


@router.put("/vehiculos/{id_vehiculo}/demos/{id_demo}/movimientos/{id_demo_movimiento}", response_model=DemoMovementRecord, tags=["Administración: movimientos DEMO"], summary="Actualizar movimiento de DEMO", description="Valida pertenencia al vehículo y DEMO, orden sin duplicados y tiempos no negativos. No ejecuta el movimiento.")
async def update_movement(id_vehiculo: ObjectId, id_demo: ObjectId, id_demo_movimiento: ObjectId, body: DemoMovementInput, request: Request):
    return await request.app.state.catalog_service.write("update_movement", id_vehiculo, id_demo, id_demo_movimiento, body)


@router.delete("/vehiculos/{id_vehiculo}/demos/{id_demo}/movimientos/{id_demo_movimiento}", status_code=204, tags=["Administración: movimientos DEMO"], summary="Eliminar movimiento de DEMO", description=DELETE_NOTE)
async def delete_movement(id_vehiculo: ObjectId, id_demo: ObjectId, id_demo_movimiento: ObjectId, request: Request):
    await request.app.state.catalog_service.write("delete_movement", id_vehiculo, id_demo, id_demo_movimiento)
    return Response(status_code=204)
