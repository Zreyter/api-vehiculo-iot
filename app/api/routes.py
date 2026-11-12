from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.core.errors import ServiceError
from app.core.security import require_control_token
from app.models.schemas import DemoRequest, DemoHeartbeatRequest, Event, HistoryItem, MovementRequest, state_event

router = APIRouter()
VehicleId = Annotated[int, Path(gt=0, description="Identificador real del vehículo en MySQL")]
control = [Depends(require_control_token)]
errors = {
    401: {"description": "Token inválido o ausente"},
    404: {"description": "Vehículo o DEMO inexistente"},
    409: {"description": "Recurso inactivo o conflicto con DEMO activa"},
    422: {"description": "Validación de datos o comando"},
    503: {"description": "Configuración o MySQL no disponible"},
}


@router.post(
    "/vehiculos/{id_vehiculo}/movimientos", response_model=Event,
    dependencies=control, tags=["Movimiento individual"], responses=errors,
    summary="Registrar un movimiento individual",
    description="Valida vehículo y comando activos y relacionados. Confirma estado + historial en una transacción y luego emite movimiento_individual. Conserva conectado. No confirma ejecución física. Durante una DEMO responde 409.",
)
async def movement(id_vehiculo: VehicleId, body: MovementRequest, request: Request):
    return await request.app.state.vehicle_service.move(id_vehiculo, body)


@router.get(
    "/vehiculos/{id_vehiculo}/historial", response_model=list[HistoryItem],
    tags=["Historial"], responses=errors, summary="Consultar hasta diez movimientos",
    description="Orden descendente de fecha_hora e id_historial. Lectura local sin token; nunca devuelve más de diez elementos.",
)
async def history(id_vehiculo: VehicleId, request: Request, limite: int = Query(default=10, ge=1, le=10)):
    return await request.app.state.vehicle_service.history(id_vehiculo, limite)


@router.post(
    "/vehiculos/{id_vehiculo}/demos", response_model=Event, status_code=202,
    dependencies=control, tags=["DEMO"], responses=errors,
    summary="Iniciar DEMO por WebSocket",
    description="Lee y valida la secuencia en MySQL. modo=registro conserva los eventos de software; modo=fisico controla el ESP8266, libera entre pasos y exige renovar /demos/activa/latido antes de 900 ms. No agrega historial DEMO ni confirma movimiento mecánico.",
)
async def start_demo(id_vehiculo: VehicleId, body: DemoRequest, request: Request):
    try:
        return await request.app.state.demo_service.start(id_vehiculo, body.id_demo, physical=body.modo == "fisico")
    except ServiceError as exc:
        request.app.state.manager.publish(state_event("error", id_vehiculo, None, id_demo=body.id_demo, mensaje=exc.detail))
        raise


@router.delete(
    "/vehiculos/{id_vehiculo}/demos/activa", response_model=Event,
    dependencies=control, tags=["DEMO"], responses=errors,
    summary="Cancelar la DEMO activa",
    description="Interrumpe duración/pausa y solicita parada física prioritaria en modo fisico. SQL pendiente no bloquea la liberación de salidas. No confirma cancelación física si la placa no confirma cero.",
)
async def cancel_demo(id_vehiculo: VehicleId, request: Request):
    return await request.app.state.demo_service.cancel(id_vehiculo)


@router.post("/vehiculos/{id_vehiculo}/demos/activa/latido", dependencies=control,
             tags=["DEMO"], responses=errors, summary="Renovar ejecución física DEMO")
async def renew_demo(id_vehiculo: VehicleId, body: DemoHeartbeatRequest, request: Request):
    return request.app.state.demo_service.renew(id_vehiculo, body.id_ejecucion)
