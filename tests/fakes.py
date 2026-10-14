import threading
from copy import deepcopy
from datetime import datetime, timezone

from app.core.errors import ServiceError
from app.models.schemas import DemoStep


class MemoryRepository:
    """Doble explícito: no se conecta a MySQL ni forma parte de la aplicación."""

    def __init__(self, duration=5):
        self.states = {
            v: {"id_vehiculo": v, "id_comando": 102, "comando": "ADELANTE", "codigo": 2, "conectado": 0}
            for v in (1, 2)
        }
        self.records = []
        self.calls = []
        self.duration = duration
        self.fail = False
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False
        self.lock = threading.Lock()

    def snapshot(self, vehicle_id):
        if vehicle_id not in self.states:
            raise ServiceError(404, "Vehículo inexistente.")
        return deepcopy(self.states[vehicle_id])

    def history(self, vehicle_id, limit):
        self.snapshot(vehicle_id)
        return deepcopy([r for r in reversed(self.records) if r["id_vehiculo"] == vehicle_id][:limit])

    def apply(self, vehicle_id, command_id, origin):
        if self.block:
            self.entered.set()
            if not self.release.wait(timeout=3):
                raise ServiceError(503, "Prueba de SQL excedió su espera.")
        if self.fail:
            raise ServiceError(503, "Fallo SQL simulado.")
        if command_id not in (102, 110):
            raise ServiceError(422, "Comando inválido.")
        with self.lock:
            self.calls.append((vehicle_id, command_id, origin))
            name, code = ("ADELANTE", 2) if command_id == 102 else ("GIRO_CARRO_IZQUIERDA", 10)
            state = self.states[vehicle_id]
            state.update(id_comando=command_id, comando=name, codigo=code)
            if origin is not None:
                self.records.append({
                    "id_historial": len(self.records) + 1, "id_vehiculo": vehicle_id,
                    "comando": name, "codigo": code, "fecha_hora": datetime.now(timezone.utc), "origen": origin,
                })
            return deepcopy(state)

    def demo_plan(self, vehicle_id, demo_id):
        state = self.snapshot(vehicle_id)
        if demo_id != 1:
            raise ServiceError(404, "DEMO inexistente.")
        steps = [DemoStep(
            id_demo_movimiento=i, orden=i, id_comando=cmd,
            comando=name, codigo=code, duracion_ms=self.duration, pausa_ms=2,
        ) for i, cmd, name, code in [(1, 102, "ADELANTE", 2), (2, 110, "GIRO_CARRO_IZQUIERDA", 10)]]
        return steps, state


class RecordingManager:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)
