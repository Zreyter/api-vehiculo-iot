from fastapi import APIRouter, Depends, Request

from app.api.routes import VehicleId
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
    return await request.app.state.device_service.command(id_vehiculo, body.lease_id, body.codigo, intent=body.intencion, pulso_ms=body.pulso_ms)


@router.delete("/vehiculos/{id_vehiculo}/control", dependencies=control, tags=["Dispositivo ESP8266"])
async def release(id_vehiculo: VehicleId, request: Request, body: ControlLease | None = None):
    # Parada autenticada global: también se puede usar si el navegador perdió su lease.
    return await request.app.state.device_service.stop(id_vehiculo, body.lease_id if body else None)
