import asyncio


class VehicleCoordinator:
    """Coordinación de laboratorio: usar exactamente un proceso de Uvicorn."""

    def __init__(self):
        self.locks: dict[int, asyncio.Lock] = {}
        self.active: dict = {}
        self.remote: dict = {}
        self.device_pending: dict[int, int] = {}

    def remote_busy(self, vehicle_id: int) -> bool:
        return vehicle_id in self.remote or self.device_pending.get(vehicle_id, 0) > 0

    def lock(self, vehicle_id: int) -> asyncio.Lock:
        return self.locks.setdefault(vehicle_id, asyncio.Lock())
