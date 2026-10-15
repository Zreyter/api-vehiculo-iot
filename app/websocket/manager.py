import asyncio
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.models.schemas import Event


@dataclass(eq=False)
class Client:
    socket: WebSocket
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=64))
    writer: asyncio.Task | None = None


class WebSocketManager:
    """Salas por vehículo y una cola FIFO por cliente, para no bloquear controles."""

    def __init__(self):
        self.rooms: dict[int, set[Client]] = {}

    async def connect(self, vehicle_id: int, socket: WebSocket, initial: Event) -> Client:
        await socket.accept()
        client = Client(socket)
        client.queue.put_nowait(initial.model_dump(mode="json"))
        self.rooms.setdefault(vehicle_id, set()).add(client)
        client.writer = asyncio.create_task(self._write(vehicle_id, client))
        return client

    def publish(self, event: Event) -> None:
        payload = event.model_dump(mode="json")
        for client in tuple(self.rooms.get(event.id_vehiculo, ())):
            try:
                client.queue.put_nowait(payload)
            except asyncio.QueueFull:
                # No descartar silenciosamente movimientos para un cliente lento.
                self._remove(event.id_vehiculo, client)
                client.writer.cancel()

    def _remove(self, vehicle_id: int, client: Client) -> None:
        room = self.rooms.get(vehicle_id)
        if room is not None:
            room.discard(client)
            if not room:
                self.rooms.pop(vehicle_id, None)

    async def _write(self, vehicle_id: int, client: Client) -> None:
        try:
            while True:
                payload = await client.queue.get()
                await asyncio.wait_for(client.socket.send_json(payload), timeout=2)
        except (Exception, asyncio.CancelledError):
            pass
        finally:
            self._remove(vehicle_id, client)
            try:
                await client.socket.close(code=1001)
            except (RuntimeError, OSError):
                pass

    async def disconnect(self, vehicle_id: int, client: Client) -> None:
        self._remove(vehicle_id, client)
        if client.writer is not None:
            client.writer.cancel()
            await asyncio.gather(client.writer, return_exceptions=True)

    async def close(self) -> None:
        clients = [(vehicle_id, client) for vehicle_id, room in self.rooms.items() for client in room]
        await asyncio.gather(*(self.disconnect(v, c) for v, c in clients))

    async def close_vehicle(self, vehicle_id: int) -> None:
        clients = tuple(self.rooms.get(vehicle_id, ()))
        await asyncio.gather(*(self.disconnect(vehicle_id, client) for client in clients))
