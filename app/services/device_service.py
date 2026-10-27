"""Canal de salidas del ESP8266. La parada no espera a MySQL.

Una sesión de navegador caduca si no renueva. Cada activación requiere un
permiso efímero emitido por la placa: no se usan relojes sincronizados ni se
reproduce el último estado de RDS al reconectar.
"""
import asyncio
import secrets
import time
from dataclasses import dataclass, field

from app.core.errors import ServiceError
from app.models.schemas import state_event

LEASE_SECONDS = .9
DEVICE_TTL_MS = 800
ACK_SECONDS = .6
PREPARED_SECONDS = .15  # La placa conserva su vencimiento independiente de 500 ms.


@dataclass(eq=False)
class Device:
    socket: object
    session: str = field(default_factory=lambda: secrets.token_hex(8))
    mode: str = "desconocido"
    ready: bool = False
    code: int = 0
    power: bool | None = None
    seen: float = field(default_factory=time.monotonic)
    sequence: int = 0
    pending: dict = field(default_factory=dict)
    tx: asyncio.Lock = field(default_factory=asyncio.Lock)
    barrier: int = 0


@dataclass(eq=False)
class Lease:
    device: Device
    commands: dict
    key: str = field(default_factory=lambda: secrets.token_hex(16))
    deadline: float = field(default_factory=lambda: time.monotonic() + LEASE_SECONDS)
    command_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    prepared: tuple | None = None
    preparing: asyncio.Task | None = None
    generation: int = 0
    initialized: bool = False


class DeviceService:
    def __init__(self, repository, manager, coordinator, *, prepare_ahead=True):
        self.repository, self.manager, self.coordinator = repository, manager, coordinator
        self.devices = {}
        self.leases = coordinator.remote
        self.queues, self.workers, self.log_errors = {}, {}, {}
        self.watch = None
        self.closing = False
        self.prepare_ahead = prepare_ahead
        self.preparations = set()

    def _invalidate(self, lease):
        lease.generation += 1
        lease.prepared = None
        task, lease.preparing = lease.preparing, None
        if task and task is not asyncio.current_task():
            task.cancel()

    def _retire(self, vehicle_id):
        lease = self.leases.pop(vehicle_id, None)
        if lease:
            self._invalidate(lease)
        return lease

    def start(self):
        if self.watch is None:
            self.watch = asyncio.create_task(self._watch())

    def status(self, vehicle_id):
        device = self.devices.get(vehicle_id)
        lease = self.leases.get(vehicle_id)
        return {
            "conectado": device is not None,
            "listo": bool(device and device.ready and device.mode == "wifi"),
            "modo": device.mode if device else "sin_conexion",
            "codigo_activo": device.code if device else None,
            "encendido_estimado": device.power if device else None,
            "control_ocupado": lease is not None,
            "registro_error": self.log_errors.get(vehicle_id),
            "confirmacion": "salidas del microcontrolador; sin sensores de movimiento",
        }

    async def _send(self, device, payload):
        async with device.tx:
            try:
                await asyncio.wait_for(device.socket.send_json(payload), ACK_SECONDS)
            except Exception:
                device.ready = False
                raise

    async def connect(self, vehicle_id, socket):
        if self.closing or vehicle_id in self.devices:
            raise ServiceError(409, "Ya hay un dispositivo conectado o el servidor está cerrando.")
        await socket.accept()
        device = Device(socket)
        self.devices[vehicle_id] = device
        try:
            await self._send(device, {"tipo": "saludo", "sesion": device.session})
        except Exception:
            self.devices.pop(vehicle_id, None)
            raise
        return device

    async def message(self, vehicle_id, device, message):
        if self.devices.get(vehicle_id) is not device or message.get("sesion") != device.session:
            return
        device.seen = time.monotonic()
        kind = message.get("tipo")
        if kind in ("listo", "estado", "ack"):
            mode, code = message.get("modo"), message.get("codigo")
            if mode not in ("wifi", "serial") or type(code) is not int or not 0 <= code <= 13:
                return
            device.mode, device.code = mode, code
            if type(message.get("encendido_estimado")) is bool:
                device.power = message["encendido_estimado"]
            elif message.get("encendido_estimado") is None:
                device.power = None
            if message.get("motivo") in ("watchdog", "conexion_perdida"):
                self._retire(vehicle_id)
            if mode == "serial":
                device.ready = False
                self._retire(vehicle_id)
            elif kind == "listo" and code == 0:
                device.ready = True
            elif code == 0 and vehicle_id not in self.leases:
                device.ready = True
        seq = message.get("seq")
        pending = device.pending.get(seq) if type(seq) is int else None
        if pending and (pending[0] == kind or (kind == "ack" and message.get("ok") is False)) and not pending[1].done():
            pending[1].set_result(message)

    async def disconnect(self, vehicle_id, device):
        if self.devices.get(vehicle_id) is not device:
            return
        self.devices.pop(vehicle_id, None)
        self._retire(vehicle_id)
        for _, future in device.pending.values():
            if not future.done():
                future.set_exception(ServiceError(503, "Se desconectó el ESP8266."))

    async def _exchange(self, device, seq, kind, payload):
        future = asyncio.get_running_loop().create_future()
        device.pending[seq] = (kind, future)
        try:
            await self._send(device, {"sesion": device.session, "seq": seq, **payload})
            return await asyncio.wait_for(future, ACK_SECONDS)
        except (TimeoutError, OSError, RuntimeError):
            if seq >= device.barrier:
                device.ready = False
            raise ServiceError(503, "El ESP8266 no confirmó la orden a tiempo.") from None
        finally:
            device.pending.pop(seq, None)
            if not future.done():
                future.cancel()

    def _lease(self, vehicle_id, key):
        lease = self.leases.get(vehicle_id)
        if not lease or not secrets.compare_digest(lease.key, key) or time.monotonic() >= lease.deadline:
            raise ServiceError(409, "La sesión de conducción venció o pertenece a otro controlador.")
        if self.devices.get(vehicle_id) is not lease.device or not lease.device.ready or lease.device.mode != "wifi":
            raise ServiceError(409, "El dispositivo no está listo en modo WiFi.")
        return lease

    async def _prepare(self, vehicle_id, key, lease):
        device = lease.device
        generation = lease.generation
        device.sequence += 1
        seq = device.sequence
        prepared = await self._exchange(device, seq, "preparado", {"tipo": "preparar", "control": key})
        self._lease(vehicle_id, key)
        if generation != lease.generation:
            return
        nonce = prepared.get("permiso")
        if not isinstance(nonce, str) or not 1 <= len(nonce) <= 32:
            raise ServiceError(503, "La placa no concedió permiso para activar salidas.")
        lease.prepared = (seq, nonce, time.monotonic())

    async def _warm(self, vehicle_id, key, lease):
        try:
            async with lease.command_lock:
                self._lease(vehicle_id, key)
                await self._prepare(vehicle_id, key, lease)
        except ServiceError:
            if self.leases.get(vehicle_id) is lease:
                await self.stop(vehicle_id, key)
        finally:
            if lease.preparing is asyncio.current_task():
                lease.preparing = None

    async def acquire(self, vehicle_id):
        async with self.coordinator.lock(vehicle_id):
            if self.closing or vehicle_id in self.coordinator.active or vehicle_id in self.leases or self.coordinator.device_pending.get(vehicle_id, 0):
                raise ServiceError(409, "El vehículo está ocupado por una DEMO, otro controlador o un registro pendiente.")
            device = self.devices.get(vehicle_id)
            if not device or not device.ready or device.mode != "wifi":
                raise ServiceError(409, "Conecta el ESP8266 y selecciona WIFI en el puerto serial.")
            commands = await asyncio.to_thread(self.repository.device_catalog, vehicle_id)
            if self.devices.get(vehicle_id) is not device or not device.ready or device.mode != "wifi":
                raise ServiceError(409, "El dispositivo cambió durante la validación del catálogo.")
            lease = Lease(device, commands)
            self.leases[vehicle_id] = lease
        try:
            await self._stop_outputs(device)
            self._lease(vehicle_id, lease.key)
            if self.prepare_ahead:
                async with lease.command_lock:
                    await self._prepare(vehicle_id, lease.key, lease)
            lease.initialized = True
        except (Exception, asyncio.CancelledError):
            if self.leases.get(vehicle_id) is lease:
                self._retire(vehicle_id)
            raise
        return {"lease_id": lease.key, "vence_en_ms": int(LEASE_SECONDS * 1000), "dispositivo": self.status(vehicle_id)}

    async def renew(self, vehicle_id, key):
        lease = self._lease(vehicle_id, key)
        lease.deadline = time.monotonic() + LEASE_SECONDS
        try:
            await self._send(lease.device, {"tipo": "latido", "sesion": lease.device.session,
                                         "control": key, "ttl_ms": DEVICE_TTL_MS})
        except Exception:
            await self.stop(vehicle_id, key)
            raise ServiceError(503, "No se pudo renovar la comunicación con la placa.") from None
        return {"vence_en_ms": int(LEASE_SECONDS * 1000)}

    async def command(self, vehicle_id, key, code):
        lease = self._lease(vehicle_id, key)
        generation = lease.generation
        if code == 0:
            # Libera salidas, pero conserva la sesión para el siguiente movimiento.
            self._invalidate(lease)
            ack = await self._stop_outputs(lease.device)
            return {"codigo": 0, "duracion_ms": 0, "salidas_confirmadas": True}
        if code not in lease.commands:
            raise ServiceError(422, "El código no existe o está inactivo en el catálogo del vehículo.")
        async with lease.command_lock:
            self._lease(vehicle_id, key)
            if generation != lease.generation:
                return {"cancelado": True}
            device = lease.device
            try:
                cached = bool(lease.prepared and time.monotonic() - lease.prepared[2] < PREPARED_SECONDS)
                if not cached:
                    await self._prepare(vehicle_id, key, lease)
                if generation != lease.generation:
                    return {"cancelado": True}
                self._lease(vehicle_id, key)
                seq, nonce, _ = lease.prepared
                lease.prepared = None  # Un permiso solo se usa una vez.
                ack = await self._exchange(device, seq, "ack", {"tipo": "orden", "control": key,
                    "permiso": nonce, "codigo": code, "ttl_ms": DEVICE_TTL_MS})
                if generation != lease.generation:
                    # Liberar no borra una orden que la placa sí alcanzó a confirmar.
                    if ack.get("ok") is True and ack.get("codigo") == code:
                        self._record(vehicle_id, lease.commands[code], key)
                    return {"cancelado": True}
                self._lease(vehicle_id, key)
                if ack.get("ok") is not True or ack.get("codigo") != code:
                    raise ServiceError(409, "La placa rechazó la orden: " + str(ack.get("motivo", "sin confirmación"))[:80])
                duration = ack.get("duracion_ms", 0)
                expected = (0,) if code in (1, 2, 3, 4, 10, 11, 12, 13) else (200, 2000) if code == 9 else (200,)
                if type(duration) is not int or duration not in expected:
                    raise ServiceError(503, "Duración de pulsación no válida en la confirmación de la placa.")
                self._record(vehicle_id, lease.commands[code], key)
            except Exception:
                if generation != lease.generation:
                    return {"cancelado": True}
                await self.stop(vehicle_id, key)
                raise
        return {"codigo": code, "duracion_ms": duration, "salidas_confirmadas": True, "registro": "pendiente",
                "permiso_anticipado": cached}

    async def _stop_outputs(self, device):
        device.sequence += 1
        device.barrier = device.sequence
        ack = await self._exchange(device, device.sequence, "ack", {"tipo": "parar"})
        if ack.get("ok") is not True or ack.get("codigo") != 0:
            device.ready = False
            raise ServiceError(503, "La placa no confirmó las salidas liberadas.")
        device.code = 0
        return ack

    async def stop(self, vehicle_id, key=None):
        lease = self.leases.get(vehicle_id)
        if key and not lease:
            return {"salidas_confirmadas": False, "mensaje": "La sesión ya terminó; no se interrumpió otro modo de control."}
        if key and lease and not secrets.compare_digest(key, lease.key):
            raise ServiceError(409, "La sesión pertenece a otro controlador.")
        self._retire(vehicle_id)
        device = self.devices.get(vehicle_id)
        if not device:
            return {"salidas_confirmadas": False, "mensaje": "Sin dispositivo; actúa su watchdog local."}
        try:
            await self._stop_outputs(device)
            return {"salidas_confirmadas": True}
        except Exception:
            device.ready = False
            return {"salidas_confirmadas": False, "mensaje": "Sin confirmación; actúa el watchdog local."}

    def _record(self, vehicle_id, command_id, key):
        queue = self.queues.setdefault(vehicle_id, asyncio.Queue(maxsize=32))
        if queue.full():
            raise ServiceError(503, "La cola de registros está llena. Se detuvo la conducción.")
        self.coordinator.device_pending[vehicle_id] = self.coordinator.device_pending.get(vehicle_id, 0) + 1
        queue.put_nowait((command_id, key))
        if vehicle_id not in self.workers or self.workers[vehicle_id].done():
            self.workers[vehicle_id] = asyncio.create_task(self._log(vehicle_id, queue))

    async def _log(self, vehicle_id, queue):
        while True:
            command, key = await queue.get()
            try:
                state = await asyncio.to_thread(self.repository.apply_device, vehicle_id, command)
                self.log_errors.pop(vehicle_id, None)
                self.manager.publish(state_event("movimiento_individual", vehicle_id, state,
                    salidas_aplicadas_confirmadas=True))
            except Exception:
                self.log_errors[vehicle_id] = "No se pudo registrar en RDS una orden ya aplicada. Revisa el historial antes de repetir."
                await self.stop(vehicle_id, key)
            finally:
                self.coordinator.device_pending[vehicle_id] -= 1
                queue.task_done()

    async def _watch(self):
        try:
            while True:
                await asyncio.sleep(.05)
                now = time.monotonic()
                expired = [(v, lease.key) for v, lease in self.leases.items() if now >= lease.deadline]
                for vehicle_id, key in expired:
                    try:
                        await self.stop(vehicle_id, key)
                    except ServiceError:
                        pass  # Una nueva sesión pudo sustituir la ya expirada.
                if self.prepare_ahead:
                    for vehicle_id, lease in tuple(self.leases.items()):
                        fresh = lease.prepared and now - lease.prepared[2] < PREPARED_SECONDS
                        if lease.initialized and not fresh and not lease.preparing and not lease.command_lock.locked():
                            task = asyncio.create_task(self._warm(vehicle_id, lease.key, lease))
                            lease.preparing = task
                            self.preparations.add(task)
                            task.add_done_callback(self.preparations.discard)
                stale = [(v, d) for v, d in self.devices.items() if now - d.seen > 3]
                for vehicle_id, device in stale:
                    if device.mode == "wifi":
                        await self.stop(vehicle_id)
                    await self.disconnect(vehicle_id, device)
                    try:
                        await device.socket.close(code=1001)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass

    async def close(self):
        self.closing = True
        if self.watch:
            self.watch.cancel()
            await asyncio.gather(self.watch, return_exceptions=True)
        for task in tuple(self.preparations):
            task.cancel()
        await asyncio.gather(*self.preparations, return_exceptions=True)
        await asyncio.gather(*(self.stop(v) for v, d in tuple(self.devices.items()) if d.mode == "wifi"), return_exceptions=True)
        await asyncio.gather(*(d.socket.close(code=1001) for d in tuple(self.devices.values())), return_exceptions=True)
        try:
            await asyncio.wait_for(asyncio.gather(*(q.join() for q in self.queues.values())), 3)
        except TimeoutError:
            pass
        for worker in self.workers.values():
            worker.cancel()
        await asyncio.gather(*self.workers.values(), return_exceptions=True)
