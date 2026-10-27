from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, WebSocket, WebSocketDisconnect

from app.core.errors import ServiceError
from app.core.security import check_token, require_control_token
from app.models.schemas import DemoRequest, Event, HistoryItem, MovementRequest, state_event

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
    description="Lee y valida la secuencia en MySQL. Solo permite una DEMO por vehículo. Actualiza estado sin registrar historial; duración y pausa usan esperas asíncronas.",
)
async def start_demo(id_vehiculo: VehicleId, body: DemoRequest, request: Request):
    try:
        return await request.app.state.demo_service.start(id_vehiculo, body.id_demo)
    except ServiceError as exc:
        request.app.state.manager.publish(state_event("error", id_vehiculo, None, id_demo=body.id_demo, mensaje=exc.detail))
        raise


@router.delete(
    "/vehiculos/{id_vehiculo}/demos/activa", response_model=Event,
    dependencies=control, tags=["DEMO"], responses=errors,
    summary="Cancelar la DEMO activa",
    description="Interrumpe duración/pausa inmediatamente. Si SQL está en curso espera su conclusión y suprime el evento de ese movimiento. Al responder no habrá más pasos de esa DEMO. No envía un comando físico de parada.",
)
async def cancel_demo(id_vehiculo: VehicleId, request: Request):
    return await request.app.state.demo_service.cancel(id_vehiculo)


@router.websocket("/ws/vehiculos/{id_vehiculo}")
async def vehicle_socket(socket: WebSocket, id_vehiculo: int):
    client = None
    try:
        authorization = socket.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        check_token(socket.app.state.settings, token if scheme.lower() == "bearer" else "")
        if id_vehiculo <= 0:
            raise HTTPException(422, "Identificador inválido.")
        client = await socket.app.state.vehicle_service.connect(id_vehiculo, socket)
        while True:
            # El canal es de observación; los controles se autentican por HTTP.
            message = await socket.receive()
            if message["type"] == "websocket.disconnect":
                break
    except (HTTPException, ServiceError):
        await socket.close(code=1008)
    except WebSocketDisconnect:
        pass
    finally:
        if client is not None:
            await socket.app.state.manager.disconnect(id_vehiculo, client)
