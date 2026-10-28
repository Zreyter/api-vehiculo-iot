import asyncio
import secrets
import time
from dataclasses import dataclass, field

from app.core.errors import ServiceError
from app.models.schemas import DemoStep, Event, state_event

BROWSER_LEASE_SECONDS = .9
DEMO_TICK_SECONDS = .15
PHYSICAL_CODES = frozenset((0, 1, 2, 3, 4, 10, 11, 12, 13))


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
    physical: bool = False
    execution: str = field(default_factory=lambda: secrets.token_hex(16))
    deadline: float = field(default_factory=lambda: time.monotonic() + BROWSER_LEASE_SECONDS)
    key: str | None = None
    failure: str | None = None
    confirmed: bool = False


class DemoService:
    def __init__(self, repository, manager, coordinator, devices=None):
        self.repository = repository
        self.manager = manager
        self.coordinator = coordinator
        self.closing = False
        self.devices = devices

    @staticmethod
    def _event(kind: str, run: DemoRun, message: str | None = None) -> Event:
        step = run.last_step
        return state_event(
            kind, run.vehicle_id, run.last_state, id_demo=run.demo_id,
            orden=step.orden if step else None,
            duracion_ms=step.duracion_ms if step else None,
            pausa_ms=step.pausa_ms if step else None,
            mensaje=message,
            modo_demo="fisico" if run.physical else "registro",
            id_ejecucion=run.execution if run.physical else None,
            salidas_aplicadas_confirmadas=run.confirmed,
        )

    async def start(self, vehicle_id: int, demo_id: int, *, physical=False) -> Event:
        async with self.coordinator.lock(vehicle_id):
            if self.closing:
                raise ServiceError(503, "El servidor está cerrando.")
            if self.coordinator.remote_busy(vehicle_id):
                raise ServiceError(409, "Desactiva la conducción WiFi y espera sus registros antes de iniciar una DEMO.")
            if vehicle_id in self.coordinator.active:
                raise ServiceError(409, "Ya hay una DEMO activa para este vehículo.")
            steps, state = await asyncio.to_thread(self.repository.demo_plan, vehicle_id, demo_id)
            if physical:
                if not self.devices or not self.devices.status(vehicle_id)["listo"]:
                    raise ServiceError(409, "Conecta el ESP8266 en modo WIFI antes de ejecutar la secuencia física.")
                if not self.devices.status(vehicle_id)["demo_temporizada"]:
                    raise ServiceError(409, "Actualiza el firmware del ESP8266 para admitir demos temporizadas. No se activaron salidas.")
                commands = await asyncio.to_thread(self.repository.device_catalog, vehicle_id)
                for step in steps:
                    try:
                        code = int(step.codigo)
                    except (TypeError, ValueError):
                        code = -1
                    if (str(step.codigo).strip() != str(code) or code not in PHYSICAL_CODES
                        or commands.get(code) != step.id_comando or not 0 <= step.pausa_ms <= 60000
                        or not (0 <= step.duracion_ms <= 60000 if code == 0 else 1 <= step.duracion_ms <= 60000)):
                        raise ServiceError(422, f"Paso {step.orden}: usa movimiento 1–4 o 10–13 con duración de 1 a 60000 ms, o parada (0). Pausa máxima: 60000 ms. No admite botones 5–9.")
            run = DemoRun(vehicle_id, demo_id, steps, state, physical=physical)
            self.coordinator.active[vehicle_id] = run
            initial = self._event("demo_iniciada", run)
            self.manager.publish(initial)
            run.task = asyncio.create_task(self._run_physical(run) if physical else self._run(run), name=f"demo-vehiculo-{vehicle_id}")
            return initial

    def renew(self, vehicle_id: int, execution: str) -> dict:
        run = self.coordinator.active.get(vehicle_id)
        if (not run or not run.physical or not secrets.compare_digest(run.execution, execution)
            or run.stop.is_set() or time.monotonic() >= run.deadline):
            raise ServiceError(409, "La ejecución DEMO terminó o venció. Iníciala de nuevo; no se reanuda automáticamente.")
        run.deadline = time.monotonic() + BROWSER_LEASE_SECONDS
        return {"vence_en_ms": int(BROWSER_LEASE_SECONDS * 1000)}

    async def cancel(self, vehicle_id: int) -> Event:
        run = self.coordinator.active.get(vehicle_id)
        if run is None:
            raise ServiceError(409, "No hay una DEMO activa para este vehículo.")
        # Prioridad: no esperar el lock ni intentar cancelar un hilo de MySQL.
        run.stop.set()
        if run.physical and run.key:
            await self.devices.stop(vehicle_id, run.key, reason="demo_cancelada")
        await asyncio.shield(run.task)
        if run.terminal.tipo == "error":
            raise ServiceError(503, run.terminal.mensaje)
        return run.terminal

    async def _heartbeat(self, run):
        try:
            while not run.stop.is_set():
                if time.monotonic() >= run.deadline:
                    raise ServiceError(503, "Se perdió la conexión con la página; se detuvo la DEMO.")
                if run.key:
                    await self.devices.renew(run.vehicle_id, run.key)
                await self._wait(run, int(DEMO_TICK_SECONDS * 1000))
        except Exception as exc:
            run.failure = exc.detail if isinstance(exc, ServiceError) else "Se perdió la comunicación del dispositivo."
            run.stop.set()
            if run.key:
                await self.devices.stop(run.vehicle_id, run.key, reason="demo_conexion_perdida")

    async def _run_physical(self, run):
        heartbeat = asyncio.create_task(self._heartbeat(run))
        try:
            result = await self.devices.acquire(run.vehicle_id, demo=run)
            run.key = result["lease_id"]
            for step in run.steps:
                if run.stop.is_set():
                    break
                # SQL runs with outputs released, never extends a held movement.
                run.last_state = await asyncio.to_thread(self.repository.apply, run.vehicle_id, step.id_comando, None)
                if run.stop.is_set():
                    break
                code = int(step.codigo)
                result = await self.devices.command(run.vehicle_id, run.key, code, record=False,
                    demo_ms=step.duracion_ms if code != 0 else None)
                if run.stop.is_set():
                    break
                if result.get("cancelado") or not result.get("salidas_confirmadas"):
                    raise ServiceError(503, "La placa no confirmó el paso; se detuvo la DEMO.")
                run.last_step, run.confirmed = step, True
                self.manager.publish(self._event("demo_movimiento", run))
                await self._wait(run, step.duracion_ms)
                if run.stop.is_set():
                    break
                await self.devices.command(run.vehicle_id, run.key, 0, record=False)
                await self._wait(run, step.pausa_ms)
        except ServiceError as exc:
            if not run.stop.is_set():
                run.failure = exc.detail
        except Exception:
            run.failure = "Error al ejecutar la DEMO física; se solicitaron salidas liberadas."
        finally:
            if run.failure:
                run.stop.set()
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            if run.key:
                result = await self.devices.stop(run.vehicle_id, run.key, reason="fin_demo")
                run.confirmed = result.get("salidas_confirmadas", False)
                if not run.confirmed:
                    run.failure = run.failure or "No se confirmó la parada. Actúa el watchdog local; no se reanuda la secuencia."
            else:
                run.confirmed = False
            kind = "error" if run.failure else "demo_cancelada" if run.stop.is_set() else "demo_finalizada"
            run.terminal = self._event(kind, run, run.failure)
            self.manager.publish(run.terminal)
            async with self.coordinator.lock(run.vehicle_id):
                if self.coordinator.active.get(run.vehicle_id) is run:
                    self.coordinator.active.pop(run.vehicle_id)

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
        if self.devices:
            await asyncio.gather(*(self.devices.stop(run.vehicle_id, run.key, reason="servidor_cerrando")
                                   for run in runs if run.physical and run.key), return_exceptions=True)
        await asyncio.gather(*(run.task for run in runs), return_exceptions=True)
