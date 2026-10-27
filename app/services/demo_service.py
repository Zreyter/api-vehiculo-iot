import asyncio
from dataclasses import dataclass, field

from app.core.errors import ServiceError
from app.models.schemas import DemoStep, Event, state_event


@dataclass
class DemoRun:
    vehicle_id: int
    demo_id: int
    steps: list[DemoStep]
    last_state: dict | None
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    last_step: DemoStep | None = None
    terminal: Event | None = None


class DemoService:
    def __init__(self, repository, manager, coordinator):
        self.repository = repository
        self.manager = manager
        self.coordinator = coordinator
        self.closing = False

    @staticmethod
    def _event(kind: str, run: DemoRun, message: str | None = None) -> Event:
        step = run.last_step
        return state_event(
            kind, run.vehicle_id, run.last_state, id_demo=run.demo_id,
            orden=step.orden if step else None,
            duracion_ms=step.duracion_ms if step else None,
            pausa_ms=step.pausa_ms if step else None,
            mensaje=message,
        )

    async def start(self, vehicle_id: int, demo_id: int) -> Event:
        async with self.coordinator.lock(vehicle_id):
            if self.closing:
                raise ServiceError(503, "El servidor está cerrando.")
            if self.coordinator.remote_busy(vehicle_id):
                raise ServiceError(409, "Desactiva la conducción WiFi y espera sus registros antes de iniciar una DEMO.")
            if vehicle_id in self.coordinator.active:
                raise ServiceError(409, "Ya hay una DEMO activa para este vehículo.")
            steps, state = await asyncio.to_thread(self.repository.demo_plan, vehicle_id, demo_id)
            run = DemoRun(vehicle_id, demo_id, steps, state)
            self.coordinator.active[vehicle_id] = run
            initial = self._event("demo_iniciada", run)
            self.manager.publish(initial)
            run.task = asyncio.create_task(self._run(run), name=f"demo-vehiculo-{vehicle_id}")
            return initial

    async def cancel(self, vehicle_id: int) -> Event:
        run = self.coordinator.active.get(vehicle_id)
        if run is None:
            raise ServiceError(409, "No hay una DEMO activa para este vehículo.")
        # Prioridad: no esperar el lock ni intentar cancelar un hilo de MySQL.
        run.stop.set()
        await asyncio.shield(run.task)
        if run.terminal.tipo == "error":
            raise ServiceError(503, run.terminal.mensaje)
        return run.terminal

    @staticmethod
    async def _wait(run: DemoRun, milliseconds: int) -> None:
        if run.stop.is_set():
            return
        try:
            await asyncio.wait_for(run.stop.wait(), timeout=milliseconds / 1000)
        except TimeoutError:
            pass

    async def _run(self, run: DemoRun) -> None:
        failure = None
        try:
            for step in run.steps:
                async with self.coordinator.lock(run.vehicle_id):
                    if run.stop.is_set():
                        break
                    run.last_state = await asyncio.to_thread(
                        self.repository.apply, run.vehicle_id, step.id_comando, None
                    )
                    run.last_step = step
                    # Si se canceló durante SQL, no publicar un nuevo movimiento.
                    if run.stop.is_set():
                        break
                    self.manager.publish(self._event("demo_movimiento", run))
                await self._wait(run, step.duracion_ms)
                await self._wait(run, step.pausa_ms)
                if run.stop.is_set():
                    break
        except ServiceError as exc:
            failure = exc.detail
        except Exception:
            failure = "Error interno al procesar la DEMO. No se confirmó ejecución física."
        finally:
            async with self.coordinator.lock(run.vehicle_id):
                kind = "error" if failure else ("demo_cancelada" if run.stop.is_set() else "demo_finalizada")
                run.terminal = self._event(kind, run, failure)
                self.manager.publish(run.terminal)
                if self.coordinator.active.get(run.vehicle_id) is run:
                    self.coordinator.active.pop(run.vehicle_id)

    async def close(self) -> None:
        self.closing = True
        runs = tuple(self.coordinator.active.values())
        for run in runs:
            run.stop.set()
        await asyncio.gather(*(run.task for run in runs), return_exceptions=True)
