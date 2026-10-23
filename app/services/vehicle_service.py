import asyncio

from app.core.errors import ServiceError
from app.models.schemas import MovementRequest, state_event


class VehicleService:
    def __init__(self, repository, manager, coordinator):
        self.repository = repository
        self.manager = manager
        self.coordinator = coordinator

    async def move(self, vehicle_id: int, request: MovementRequest):
        async with self.coordinator.lock(vehicle_id):
            if self.coordinator.remote_busy(vehicle_id):
                raise ServiceError(409, "Desactiva la conducción WiFi y espera sus registros antes de usar movimientos individuales.")
            if vehicle_id in self.coordinator.active:
                raise ServiceError(409, "Hay una DEMO activa. Cancélala antes de enviar un movimiento individual.")
            try:
                state = await asyncio.to_thread(
                    self.repository.apply, vehicle_id, request.id_comando, request.origen
                )
            except ServiceError as exc:
                self.manager.publish(state_event("error", vehicle_id, None, mensaje=exc.detail))
                raise
            event = state_event("movimiento_individual", vehicle_id, state)
            self.manager.publish(event)
            return event

    async def history(self, vehicle_id: int, limit: int):
        return await asyncio.to_thread(self.repository.history, vehicle_id, limit)

    async def connect(self, vehicle_id: int, socket, *, subprotocol: str | None = None):
        # Snapshot + suscripción son atómicos respecto a los movimientos de esta API.
        async with self.coordinator.lock(vehicle_id):
            state = await asyncio.to_thread(self.repository.snapshot, vehicle_id)
            return await self.manager.connect(
                vehicle_id, socket, state_event("estado", vehicle_id, state),
                subprotocol=subprotocol,
            )
