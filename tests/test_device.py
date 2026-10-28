import asyncio
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.core.errors import ServiceError
from app.main import create_app
from app.services.coordinator import VehicleCoordinator
from app.services.device_service import DeviceService
from tests.fakes import RecordingManager, MemoryRepository


class Repository:
    def __init__(self):
        self.records = []
        self.block = False
        self.entered = threading.Event()
        self.unblock = threading.Event()
        self.fail = False

    def device_catalog(self, vehicle):
        if vehicle not in (1, 2):
            raise ServiceError(404, 'Vehículo inexistente.')
        return {2: 102, 8: 108, 9: 109, 10: 110}

    def apply_device(self, vehicle, command):
        if self.block:
            self.entered.set()
            self.unblock.wait(2)
        if self.fail:
            raise ServiceError(503, 'Fallo de registro simulado')
        self.records.append((vehicle, command))
        return {'id_vehiculo': vehicle, 'id_comando': command, 'codigo': command-100, 'conectado': 0}


class Socket:
    """Dispositivo simulado: el servicio real exige permiso y confirmación."""
    def __init__(self, service, vehicle):
        self.service, self.vehicle = service, vehicle
        self.device = None
        self.frames = []
        self.mode, self.code, self.power = 'wifi', 0, False
        self.accepted, self.closed = False, False
        self.no_ack = False
        self.reject = False
        self.empty_permission = False

    async def accept(self): self.accepted = True
    async def close(self, **kwargs): self.closed = True

    async def send_json(self, frame):
        self.frames.append(frame)
        if frame['tipo'] == 'saludo' or self.no_ack:
            return
        response = {'sesion': self.device.session, 'seq': frame.get('seq')}
        if frame['tipo'] == 'preparar':
            response.update(tipo='preparado', permiso='' if self.empty_permission else 'nonce-de-prueba')
        elif frame['tipo'] in ('orden', 'parar'):
            self.code = frame.get('codigo', 0)
            duration = frame.get('pulso_ms',200) if self.code == 9 else 200 if 5 <= self.code <= 8 else 0
            response.update(tipo='ack', modo=self.mode, codigo=self.code, encendido_estimado=self.power,
                            ok=not self.reject, duracion_ms=duration, pulsos_encendido_explicitos=True)
        else:
            return
        await self.service.message(self.vehicle, self.device, response)


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repo = Repository()
        self.coordinator = VehicleCoordinator()
        self.manager = RecordingManager()
        self.service = DeviceService(self.repo, self.manager, self.coordinator)
        self.service.start()
        self.socket = Socket(self.service, 1)
        self.device = await self.service.connect(1, self.socket)
        self.socket.device = self.device
        await self.service.message(1, self.device, {'tipo':'listo','sesion':self.device.session,
            'modo':'wifi','codigo':0,'encendido_estimado':False})

    async def asyncTearDown(self):
        self.repo.unblock.set()
        self.socket.no_ack = False
        await self.service.close()

    async def acquire(self):
        return (await self.service.acquire(1))['lease_id']

    async def test_connect_only_sends_handshake_never_replays_database(self):
        self.assertEqual([f['tipo'] for f in self.socket.frames], ['saludo'])
        self.assertTrue(self.service.status(1)['listo'])
        self.assertEqual(self.repo.records, [])

    async def test_unknown_or_unreleased_device_cannot_acquire(self):
        self.device.ready = False
        with self.assertRaises(ServiceError): await self.acquire()
        with self.assertRaises(ServiceError): await self.service.acquire(2)

    async def test_duplicate_device_does_not_replace_original(self):
        with self.assertRaises(ServiceError): await self.service.connect(1, Socket(self.service, 1))
        self.assertIs(self.service.devices[1], self.device)

    async def test_only_one_browser_can_control_vehicle(self):
        await self.acquire()
        with self.assertRaises(ServiceError): await self.acquire()

    async def test_code_is_resolved_to_catalogue_id_and_registered_after_ack(self):
        key = await self.acquire()
        result = await self.service.command(1, key, 2)
        await self.service.queues[1].join()
        self.assertTrue(result['salidas_confirmadas'])
        self.assertEqual(self.repo.records, [(1, 102)])
        self.assertTrue(self.manager.events[0].salidas_aplicadas_confirmadas)
        self.assertFalse(self.manager.events[0].ejecucion_fisica_confirmada)
        orders=[(i,f) for i,f in enumerate(self.socket.frames) if f['tipo']=='orden']
        self.assertEqual(len(orders),1)
        index,order=orders[0]
        # Optional prefetch may run after the ACK while the log queue drains.
        self.assertEqual(self.socket.frames[index-1]['tipo'],'preparar')
        self.assertEqual(self.socket.frames[index-1]['seq'],order['seq'])

    async def test_missing_catalogue_code_does_not_reach_outputs(self):
        key = await self.acquire()
        before = len(self.socket.frames)
        with self.assertRaises(ServiceError): await self.service.command(1, key, 3)
        self.assertEqual(len(self.socket.frames), before)

    async def test_stop_does_not_need_code_zero_in_database(self):
        key = await self.acquire()
        await self.service.command(1, key, 2)
        await self.service.command(1, key, 0)
        self.assertEqual(self.device.code, 0)
        self.assertIn(1, self.service.leases)
        await self.service.stop(1, key)
        self.assertNotIn(1, self.service.leases)

    async def test_slow_mysql_does_not_block_renewal_or_release(self):
        self.repo.block = True
        key = await self.acquire()
        await self.service.command(1, key, 2)
        while not self.repo.entered.is_set(): await asyncio.sleep(.001)
        await asyncio.wait_for(self.service.renew(1, key), .1)
        response = await asyncio.wait_for(self.service.stop(1, key), .1)
        self.assertTrue(response['salidas_confirmadas'])
        self.assertEqual(self.repo.records, [])
        self.repo.unblock.set()
        await self.service.queues[1].join()

    async def test_browser_lease_expires_and_sends_release(self):
        key = await self.acquire()
        self.service.leases[1].deadline = time.monotonic() - 1
        await asyncio.sleep(.08)
        self.assertNotIn(1, self.service.leases)
        self.assertEqual(self.socket.frames[-1]['tipo'], 'parar')
        with self.assertRaises(ServiceError): await self.service.renew(1, key)

    async def test_serial_takeover_does_not_get_stopped_by_old_browser_cleanup(self):
        key = await self.acquire()
        self.socket.mode, self.socket.code = 'serial', 10
        await self.service.message(1, self.device, {'tipo':'estado','sesion':self.device.session,'modo':'serial','codigo':10})
        before = len(self.socket.frames)
        await self.service.stop(1, key)
        with self.assertRaises(ServiceError): await self.service.command(1, key, 2)
        self.assertEqual(len(self.socket.frames), before)
        self.assertEqual(self.device.code, 10)

    async def test_watchdog_status_revokes_old_browser_session(self):
        key = await self.acquire()
        await self.service.message(1, self.device, {'tipo':'estado','sesion':self.device.session,'modo':'wifi','codigo':0,'motivo':'watchdog'})
        with self.assertRaises(ServiceError): await self.service.renew(1, key)

    async def test_ack_timeout_releases_session_without_recording_success(self):
        key = await self.acquire()
        self.socket.no_ack = True
        with patch('app.services.device_service.ACK_SECONDS', .01):
            with self.assertRaises(ServiceError): await self.service.command(1, key, 2)
        self.assertNotIn(1, self.service.leases)
        self.assertEqual(self.repo.records, [])

    async def test_rejected_or_empty_permission_does_not_record_success(self):
        key = await self.acquire()
        self.socket.empty_permission = True
        self.service.leases[1].prepared = None
        with self.assertRaises(ServiceError): await self.service.command(1, key, 2)
        self.assertEqual(self.repo.records, [])
        self.assertFalse(any(f['tipo']=='orden' for f in self.socket.frames))

    async def test_mysql_failure_stops_control_after_output_ack(self):
        key = await self.acquire()
        self.repo.fail = True
        await self.service.command(1, key, 2)
        await self.service.queues[1].join()
        self.assertNotIn(1, self.service.leases)
        self.assertIsNotNone(self.service.status(1)['registro_error'])
        self.assertEqual(self.device.code, 0)

    async def test_old_device_session_and_invalid_sequence_are_ignored(self):
        await self.service.message(1, self.device, {'tipo':'estado','sesion':'old-session','modo':'serial','codigo':13})
        self.assertEqual(self.device.mode, 'wifi')

    async def test_power_duration_is_taken_from_device_ack(self):
        key = await self.acquire()
        self.socket.power = True
        result = await self.service.command(1, key, 9, pulso_ms=2000)
        self.assertEqual(result['duracion_ms'], 2000)

    async def test_unknown_power_state_is_not_replaced_with_stale_estimate(self):
        await self.service.message(1, self.device, {'tipo':'estado','sesion':self.device.session,'modo':'wifi','codigo':0,'encendido_estimado':None})
        self.assertIsNone(self.service.status(1)['encendido_estimado'])

    async def test_disconnect_and_reconnect_cannot_reuse_old_lease(self):
        key = await self.acquire()
        await self.service.disconnect(1, self.device)
        other = Socket(self.service, 1)
        replacement = await self.service.connect(1, other)
        other.device = replacement
        self.assertNotEqual(replacement.session, self.device.session)
        self.assertFalse(self.service.status(1)['listo'])
        with self.assertRaises(ServiceError): await self.service.renew(1, key)


class DeviceRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings(_env_file=None, control_token=SecretStr('control-test'), device_token=SecretStr('device-test')), MemoryRepository())
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_http_controls_require_token_and_validate_bodies(self):
        for method, path in [('GET','/dispositivo'),('POST','/control'),('PUT','/control'),('POST','/control/orden'),('DELETE','/control')]:
            response=self.client.request(method,'/vehiculos/1'+path)
            self.assertEqual(response.status_code,401)
        for body in ({'codigo':2,'lease_id':'x'}, {'codigo':True,'lease_id':'0'*32}, {'codigo':14,'lease_id':'0'*32}):
            self.assertEqual(self.client.post('/vehiculos/1/control/orden',json=body,headers={'Authorization':'Bearer control-test'}).status_code,422)

    def test_device_uses_separate_token_and_handshake_reports_no_old_command(self):
        for token in ('','control-test'):
            with self.assertRaises(WebSocketDisconnect):
                with self.client.websocket_connect('/dispositivo/ws/vehiculos/1',headers={'Authorization':'Bearer '+token}): pass
        with self.client.websocket_connect('/dispositivo/ws/vehiculos/1',headers={'Authorization':'Bearer device-test'}) as socket:
            hello=socket.receive_json()
            self.assertEqual(set(hello), {'tipo','sesion'})
            socket.send_json({'tipo':'listo','sesion':hello['sesion'],'modo':'wifi','codigo':0,'encendido_estimado':False})
            status=self.client.get('/vehiculos/1/dispositivo',headers={'Authorization':'Bearer control-test'}).json()
            self.assertTrue(status['conectado'])

    def test_oversized_and_malformed_device_frames_close_connection(self):
        for raw in ('x'*1025, '[]', '{'):
            with self.client.websocket_connect('/dispositivo/ws/vehiculos/2',headers={'Authorization':'Bearer device-test'}) as socket:
                socket.receive_json();socket.send_text(raw)
                with self.assertRaises(WebSocketDisconnect):socket.receive_json()
