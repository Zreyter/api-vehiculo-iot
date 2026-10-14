import asyncio


class VehicleCoordinator:
    """Coordinación de laboratorio: usar exactamente un proceso de Uvicorn."""

    def __init__(self):
        self.locks: dict[int, asyncio.Lock] = {}
        self.active: dict = {}

    def lock(self, vehicle_id: int) -> asyncio.Lock:
        return self.locks.setdefault(vehicle_id, asyncio.Lock())
