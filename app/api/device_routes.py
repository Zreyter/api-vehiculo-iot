import json
from secrets import compare_digest

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from app.api.routes import VehicleId
from app.core.errors import ServiceError
from app.core.security import require_control_token
from app.models.device import ControlLease, DeviceCommand

router = APIRouter()
control = [Depends(require_control_token)]


@router.get("/vehiculos/{id_vehiculo}/dispositivo", dependencies=control, tags=["Dispositivo ESP8266"])
async def status(id_vehiculo: VehicleId, request: Request):
    return request.app.state.device_service.status(id_vehiculo)


@router.post("/vehiculos/{id_vehiculo}/control", dependencies=control, tags=["Dispositivo ESP8266"])
async def acquire(id_vehiculo: VehicleId, request: Request):
    return await request.app.state.device_service.acquire(id_vehiculo)


@router.put("/vehiculos/{id_vehiculo}/control", dependencies=control, tags=["Dispositivo ESP8266"])
async def renew(id_vehiculo: VehicleId, body: ControlLease, request: Request):
    return await request.app.state.device_service.renew(id_vehiculo, body.lease_id)


@router.post("/vehiculos/{id_vehiculo}/control/orden", dependencies=control, tags=["Dispositivo ESP8266"])
async def command(id_vehiculo: VehicleId, body: DeviceCommand, request: Request):
    return await request.app.state.device_service.command(id_vehiculo, body.lease_id, body.codigo)


@router.delete("/vehiculos/{id_vehiculo}/control", dependencies=control, tags=["Dispositivo ESP8266"])
async def release(id_vehiculo: VehicleId, request: Request, body: ControlLease | None = None):
    # Parada autenticada global: también se puede usar si el navegador perdió su lease.
    return await request.app.state.device_service.stop(id_vehiculo, body.lease_id if body else None)


@router.websocket("/dispositivo/ws/vehiculos/{id_vehiculo}")
async def device_socket(socket: WebSocket, id_vehiculo: int):
    device = None
    service = socket.app.state.device_service
    try:
        settings = socket.app.state.settings
        expected = settings.device_token.get_secret_value() or settings.control_token.get_secret_value()
        scheme, _, supplied = socket.headers.get("authorization", "").partition(" ")
        if id_vehiculo <= 0 or not expected or scheme.lower() != "bearer" or not compare_digest(expected.encode(), supplied.encode()):
            raise HTTPException(401)
        device = await service.connect(id_vehiculo, socket)
        while True:
            raw = await socket.receive_text()
            if len(raw) > 1024:
                await socket.close(code=1009)
                break
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise ValueError()
            await service.message(id_vehiculo, device, message)
    except (HTTPException, ServiceError, ValueError):
        await socket.close(code=1008)
    except WebSocketDisconnect:
        pass
    finally:
        if device:
            await service.disconnect(id_vehiculo, device)
