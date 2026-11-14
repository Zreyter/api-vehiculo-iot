"""Un punto de entrada para la placa, el control y la observación."""

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from secrets import compare_digest

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.errors import DatabaseUnavailable, ServiceError
from app.core.security import check_token
from app.models.device import TimedControlInput, DeviceCommand
from app.models.schemas import DemoRequest

router = APIRouter()
logger = logging.getLogger(__name__)
CONTROL = "iot-control"
MONITOR = "iot-monitor"
DEVICE = "iot-device"
DIRECT_DEVICE = "iot-device-direct"
TRACE_FIELDS = ("tipo", "seq", "codigo", "ok", "modo", "motivo", "duracion_ms",
                "pulso_ms", "demo_ms", "ttl_ms", "demo_temporizada",
                "pulsos_encendido_explicitos", "encendido_estimado")


class DeviceTransport:
    """Publica las tramas que pasan por la conexión real, sin nonces ni sesión."""

    def __init__(self, socket, vehicle_id, protocol):
        self.socket, self.vehicle_id, self.protocol = socket, vehicle_id, protocol
        self.manager = socket.app.state.manager

    async def accept(self):
        await self.socket.accept(subprotocol=self.protocol)

    async def close(self, code=1000):
        await self.socket.close(code=code)

    async def send_json(self, frame):
        await self.socket.send_json(frame)
        self.trace("api → esp8266", frame)

    def trace(self, direction, frame):
        self.manager.broadcast(self.vehicle_id, {
            "tipo": "trama_dispositivo",
            "direccion": direction,
            "marca_temporal": datetime.now(timezone.utc).isoformat(),
            "trama": {key: frame[key] for key in TRACE_FIELDS
                      if key in frame and type(frame[key]) in (str, int, bool, type(None))},
        }, role=MONITOR)


class ControlConnection:
    """La conexión es dueña de su lease y de la demo que inició."""

    def __init__(self, app, vehicle_id, client):
        self.app, self.vehicle_id, self.client = app, vehicle_id, client
        self.device = app.device_service
        self.demos = app.demo_service
        self.lease = self.execution = None
        self.input_intent = self.input_generation = 0
        self.tasks = set()
        self.lifecycle = asyncio.Lock()
        self.closed = False

    def trace_input(self, kind, code, **fields):
        self.app.manager.broadcast(self.vehicle_id, {
            "tipo": kind,
            "direccion": "Panel → API",
            "marca_temporal": datetime.now(timezone.utc).isoformat(),
            "codigo": code,
            **fields,
        }, role=MONITOR)

    async def received_without_forwarding(self, code, intent, duration, message, current):
        if code and not await self.device.record_without_device(self.vehicle_id, code, current):
            return {"cancelado": True}
        if not current():
            return {"cancelado": True}
        self.trace_input("orden_sin_envio", code, intencion=intent, mensaje=message, duracion_ms=duration,
                         registro="pendiente" if code else None)
        return {"recibida": True, "codigo": code, "orden_enviada": False, "sesion_activa": bool(self.lease),
                "salidas_confirmadas": False, "duracion_ms": duration, "mensaje": message}

    async def release_input_lease(self, key):
        if self.lease == key:
            self.lease = None
        try:
            return await self.device.stop(self.vehicle_id, key)
        except ServiceError as exc:
            if exc.status_code != 409:
                raise
            return {}

    async def receive_input(self, order):
        intent, code = order.intencion, order.codigo
        if intent is None:
            raise ServiceError(422, "Falta la intención de la orden.")
        if (code == 9 and order.pulso_ms not in (200, 2000)) or (code != 9 and order.pulso_ms is not None):
            raise ServiceError(422, "El código 9 requiere un pulso de 200 o 2000 ms.")
        duration = order.duracion_ms
        if duration is not None and code not in (1, 2, 3, 4, 10, 11, 12, 13):
            raise ServiceError(422, "Duración incompatible con el movimiento.")
        if self.closed or intent <= self.input_intent:
            return {"cancelado": True}
        self.input_intent = intent
        generation = self.input_generation
        self.trace_input("orden_recibida", code, intencion=intent)
        vehicle = self.vehicle_id

        def current():
            return not self.closed and generation == self.input_generation and intent == self.input_intent

        # El toque manual de la pala derecha conserva su duración predeterminada.
        movement_ms = 200 if code == 4 and duration is None else duration

        async def without_device(message):
            pulse = order.pulso_ms or movement_ms or (200 if 5 <= code <= 8 else 0)
            return await self.received_without_forwarding(code, intent, pulse, message, current)

        if code and not self.lease:
            async with self.lifecycle:
                if not current():
                    return {"cancelado": True}
                if not self.lease:
                    try:
                        result = await self.device.acquire(vehicle, direct_only=True)
                    except ServiceError as exc:
                        if not current():
                            return {"cancelado": True}
                        if isinstance(exc, DatabaseUnavailable) or exc.status_code not in (409, 503):
                            raise
                        return await without_device(exc.detail)
                    except (TimeoutError, OSError, RuntimeError):
                        return await without_device("No se pudo abrir el canal de la placa.")
                    key = result["lease_id"]
                    if not current():
                        await self.release_input_lease(key)
                        return {"cancelado": True}
                    self.lease = key

        key = self.lease
        if not key:
            return await without_device("Sin una sesión física activa.")
        try:
            result = await self.device.command(vehicle, key, code, intent=intent,
                                               pulso_ms=order.pulso_ms, demo_ms=movement_ms)
        except (ServiceError, TimeoutError, OSError, RuntimeError) as exc:
            if not current():
                return {"cancelado": True}
            await self.release_input_lease(key)
            if isinstance(exc, DatabaseUnavailable):
                raise
            message = exc.detail if isinstance(exc, ServiceError) else "Se interrumpió el canal de la placa."
            return await without_device(message)
        if result.get("cancelado") and not result.get("registro_ocupado") and current():
            await self.release_input_lease(key)
            return await without_device("Se interrumpió el canal de la placa.")
        ended = result.pop("sesion_finalizada", False)
        if ended and self.lease == key:
            self.lease = None
        return {"recibida": True, "sesion_activa": self.lease == key, **result}

    async def dispatch(self, action, body):
        vehicle = self.vehicle_id
        if action == "entrada":
            return await self.receive_input(TimedControlInput(**body))
        if action == "estado":
            return self.device.status(vehicle)
        if action == "orden":
            if not self.lease:
                raise ServiceError(409, "Activa el control primero.")
            order = DeviceCommand(lease_id=self.lease, **body)
            # En control web, el giro derecho de la pala es un toque temporizado.
            return await self.device.command(vehicle, order.lease_id, order.codigo,
                                             intent=order.intencion, pulso_ms=order.pulso_ms,
                                             demo_ms=200 if order.codigo == 4 else None)
        if action == "latido":
            key = self.lease
            if key:
                try:
                    return await self.device.renew(vehicle, key)
                except ServiceError as exc:
                    if not self.input_intent or exc.status_code not in (409, 503):
                        raise
                    await self.release_input_lease(key)
                    return {"sesion_activa": False}
            if self.input_intent:
                return {"sesion_activa": False}
            raise ServiceError(409, "El control está desactivado.")
        if action == "demo_latido":
            return self.demos.renew(vehicle, self.execution or "")
        if action == "liberar":
            self.input_generation += 1
        # Mientras MySQL prepara una adquisición, la lectura del socket sigue activa.
        async with self.lifecycle:
            if self.closed and action not in ("liberar", "demo_cancelar"):
                raise ServiceError(409, "La conexión terminó.")
            if action == "activar":
                result = await self.device.acquire(vehicle)
                self.lease = result["lease_id"]
                return result["dispositivo"]
            if action == "liberar":
                lease, self.lease = self.lease, None
                return await self.device.stop(vehicle, lease) if lease else {}
            if action == "demo_iniciar":
                demo = DemoRequest(**body)
                event = await self.demos.start(vehicle, demo.id_demo, physical=True, continue_without_device=True)
                self.execution = event.id_ejecucion
                return event.model_dump(mode="json")
            if action == "demo_cancelar":
                run = self.demos.coordinator.active.get(vehicle)
                if run and run.execution == self.execution:
                    return (await self.demos.cancel(vehicle)).model_dump(mode="json")
                return {}
        raise ServiceError(422, "Acción WebSocket desconocida.")

    async def reply(self, message):
        payload = {"tipo": "respuesta", "id": message["id"]}
        try:
            result = await self.dispatch(message["accion"], message.get("datos", {}))
            payload.update(ok=True, datos=result)
        except ServiceError as exc:
            payload.update(ok=False, error=exc.detail, estado_http=exc.status_code)
        except (TypeError, ValidationError):
            payload.update(ok=False, error="Datos de la acción inválidos.", estado_http=422)
        except Exception:
            logger.exception("Error al procesar el control WebSocket")
            payload.update(ok=False, error="Error interno al procesar la acción.", estado_http=500)
        if not self.closed:
            self.app.manager.enqueue(self.vehicle_id, self.client, payload)

    def schedule(self, raw):
        message = json.loads(raw)
        if (not isinstance(message, dict) or type(message.get("id")) is not int
                or not isinstance(message.get("accion"), str)
                or not isinstance(message.get("datos", {}), dict)):
            raise ValueError("Solicitud WebSocket inválida.")
        if len(self.tasks) >= 24:
            raise ValueError("Demasiadas acciones pendientes.")
        task = asyncio.create_task(self.reply(message))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def close(self):
        self.closed = True
        # Frenar antes de esperar órdenes en vuelo. El watchdog cubre un corte de red.
        try:
            await self.dispatch("liberar", {})
        finally:
            try:
                await self.dispatch("demo_cancelar", {})
            except ServiceError:
                logger.info("La demo terminó durante el cierre del control", exc_info=True)
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)


class SocketGateway:
    def __init__(self, socket, vehicle_id, legacy=None):
        self.socket, self.vehicle_id, self.legacy = socket, vehicle_id, legacy
        self.app = socket.app.state

    def browser_token(self, protocols):
        origin = self.socket.headers.get("origin")
        scheme = "https" if self.socket.url.scheme == "wss" else "http"
        local = f"{scheme}://{self.socket.headers.get('host', '')}"
        if not origin or origin not in {local, *self.app.settings.browser_origins}:
            raise HTTPException(403, "Origen no permitido.")
        tokens = [p[6:] for p in protocols if p.startswith("token.")]
        if len(tokens) != 1 or not 0 < len(tokens[0]) <= 4096:
            raise HTTPException(401, "Token requerido.")
        token = tokens[0]
        return base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True).decode("ascii")

    def authorize(self):
        if self.vehicle_id <= 0:
            raise HTTPException(422)
        protocols = self.socket.scope.get("subprotocols", [])
        scheme, _, token = self.socket.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer":
            token = ""
        roles = [p for p in protocols if p in (CONTROL, MONITOR, DEVICE, DIRECT_DEVICE, "iot")]
        if len(roles) > 1:
            raise HTTPException(400)
        protocol = roles[0] if roles else None
        if protocol in (DEVICE, DIRECT_DEVICE) or self.legacy == DEVICE:
            settings = self.app.settings
            expected = settings.device_token.get_secret_value()
            if self.legacy == DEVICE and not expected:
                expected = settings.control_token.get_secret_value()
            if not expected or not compare_digest(expected.encode(), token.encode()):
                raise HTTPException(401)
            return DEVICE, protocol
        if self.legacy == "iot" and protocol != "iot":
            raise HTTPException(401)
        if protocol:
            token = self.browser_token(protocols)
        check_token(self.app.settings, token)
        return protocol or "observador", protocol

    async def run_device(self, protocol):
        transport = DeviceTransport(self.socket, self.vehicle_id, protocol)
        device = await self.app.device_service.connect(self.vehicle_id, transport, direct=protocol == DIRECT_DEVICE)
        try:
            while True:
                raw = await self.socket.receive_text()
                if len(raw) > 1024:
                    raise ValueError()
                frame = json.loads(raw)
                if not isinstance(frame, dict):
                    raise ValueError()
                await self.app.device_service.message(self.vehicle_id, device, frame)
                if (device.direct and frame.get("tipo") == "estado") or frame.get("sesion") == device.session:
                    transport.trace("esp8266 → api", frame)
        finally:
            await self.app.device_service.disconnect(self.vehicle_id, device)

    async def run_browser(self, role, protocol):
        client = await self.app.vehicle_service.connect(
            self.vehicle_id, self.socket, subprotocol=protocol, role=role,
        )
        control = ControlConnection(self.app, self.vehicle_id, client) if role == CONTROL else None
        try:
            while True:
                frame = await self.socket.receive()
                if frame["type"] == "websocket.disconnect":
                    return
                if control:
                    raw = frame.get("text") or ""
                    if len(raw) > 2048:
                        raise ValueError()
                    control.schedule(raw)
        finally:
            await self.app.manager.disconnect(self.vehicle_id, client)
            if control:
                await control.close()

    async def run(self):
        try:
            role, protocol = self.authorize()
            if role == DEVICE:
                await self.run_device(protocol)
            else:
                await self.run_browser(role, protocol)
        except (HTTPException, ServiceError, ValueError):
            try:
                await self.socket.close(code=1008)
            except (RuntimeError, OSError):
                pass
        except WebSocketDisconnect:
            pass


@router.websocket("/ws/vehiculos/{id_vehiculo}")
async def vehicle_socket(socket: WebSocket, id_vehiculo: int):
    await SocketGateway(socket, id_vehiculo).run()


@router.websocket("/dispositivo/ws/vehiculos/{id_vehiculo}")
async def legacy_device(socket: WebSocket, id_vehiculo: int):
    await SocketGateway(socket, id_vehiculo, DEVICE).run()


@router.websocket("/panel/ws/vehiculos/{id_vehiculo}")
async def legacy_panel(socket: WebSocket, id_vehiculo: int):
    await SocketGateway(socket, id_vehiculo, "iot").run()
