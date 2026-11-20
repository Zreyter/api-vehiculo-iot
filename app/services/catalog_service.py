import asyncio

from app.core.errors import ServiceError


class CatalogService:
    def __init__(self, repository, coordinator, manager):
        self.repository = repository
        self.coordinator = coordinator
        self.manager = manager
        self.verificar_demo = None

    async def read(self, operation: str, *ids):
        # operation es una constante del endpoint, no un parámetro de HTTP.
        if self.verificar_demo and operation == "movements":
            await asyncio.to_thread(self.verificar_demo, *ids)
        rows = await asyncio.to_thread(getattr(self.repository, operation), *ids)
        if self.verificar_demo and operation == "demos":
            ocultas = await asyncio.to_thread(self.verificar_demo,*ids)
            return [r for r in rows if r["id_demo"] not in ocultas]
        return rows

    async def write(self, operation: str, vehicle_id: int | None, *args):
        method = getattr(self.repository, operation)
        if vehicle_id is None:  # Crear un vehículo todavía no tiene ID que bloquear.
            return await asyncio.to_thread(method, *args)
        async with self.coordinator.lock(vehicle_id):
            if self.coordinator.remote_busy(vehicle_id):
                raise ServiceError(409, "Desactiva la conducción WiFi y espera sus registros antes de modificar el catálogo.")
            if vehicle_id in self.coordinator.active:
                raise ServiceError(409, "Cancela o espera a que termine la DEMO antes de modificar este vehículo o su catálogo.")
            if self.verificar_demo and operation in ("update_demo","delete_demo","create_movement","update_movement","delete_movement"):
                await asyncio.to_thread(self.verificar_demo,vehicle_id,args[0],mantenimiento=True)
            result = await asyncio.to_thread(method, vehicle_id, *args)
            if operation == "delete_vehicle":
                # Solo cerrar sus suscriptores cuando el DELETE ya confirmó COMMIT.
                await self.manager.close_vehicle(vehicle_id)
            return result
