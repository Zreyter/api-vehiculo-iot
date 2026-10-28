import asyncio
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import ServiceError
from app.main import create_app
from app.services.coordinator import VehicleCoordinator
from app.services.demo_service import DemoService
from app.services.device_service import DeviceService
from tests.fakes import MemoryRepository, RecordingManager
from tests.test_device import Socket


class DemoRepository(MemoryRepository):
    def __init__(self, duration=80, pause=70):
        super().__init__(duration)
        self.pause = pause
        self.bad_code = None

    def device_catalog(self, vehicle):
        return {0: 100, 2: 102, 10: 110, 8: 108, 9: 109}

    def demo_plan(self, vehicle, demo):
        steps, state = super().demo_plan(vehicle, demo)
        for step in steps:
            step.pausa_ms = self.pause
        if self.bad_code is not None:
            steps[-1].codigo = self.bad_code
        return steps, state


class TimedSocket(Socket):
    def __init__(self, *args):
        super().__init__(*args)
        self.timeline = []
        self.reject_order = False
        self.drop_order_ack = False
        self.drop_stop_ack = False
        self.ack_delay = 0
        self.timers = []

    async def send_json(self, frame):
        self.timeline.append((time.monotonic(), frame.copy()))
        self.frames.append(frame)
        if frame['tipo'] == 'saludo' or self.no_ack:
            return
        response = {'sesion':self.device.session,'seq':frame.get('seq'), 'demo_temporizada':True}
        if frame['tipo'] == 'preparar':
            response.update(tipo='preparado',permiso='test-timed-nonce')
        elif frame['tipo'] in ('orden','parar'):
            self.code = frame.get('codigo',0)
            response.update(tipo='ack',modo=self.mode,codigo=self.code,encendido_estimado=self.power,
                ok=not self.reject_order or frame['tipo']=='parar',duracion_ms=frame.get('demo_ms',0))
            if frame.get('demo_ms'):
                async def release():
                    await asyncio.sleep(frame['demo_ms']/1000)
                    self.code=0
                self.timers.append(asyncio.create_task(release()))
            if self.drop_order_ack and frame['tipo']=='orden':
                return
            if self.drop_stop_ack and frame['tipo']=='parar':
                return
        else:
            return
        if frame['tipo']=='orden' and self.ack_delay:
            async def delayed_ack():
                await asyncio.sleep(self.ack_delay)
                await self.service.message(self.vehicle,self.device,response)
            self.timers.append(asyncio.create_task(delayed_ack()))
        else:
            await self.service.message(self.vehicle,self.device,response)


class PhysicalDemoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repo, self.manager = DemoRepository(), RecordingManager()
        self.coordinator = VehicleCoordinator()
        self.devices = DeviceService(self.repo, self.manager, self.coordinator, prepare_ahead=False)
        self.demos = DemoService(self.repo, self.manager, self.coordinator, self.devices)
        self.devices.start()
        self.socket = TimedSocket(self.devices, 1)
        self.device = await self.devices.connect(1, self.socket)
        self.socket.device = self.device
        await self.devices.message(1, self.device, dict(tipo='listo', sesion=self.device.session,
            modo='wifi', codigo=0, encendido_estimado=True, demo_temporizada=True))
        self.pump = None

    async def asyncTearDown(self):
        self.repo.release.set()
        self.socket.no_ack = False
        if self.pump:
            self.pump.cancel()
            await asyncio.gather(self.pump, return_exceptions=True)
        await self.demos.close()
        await self.devices.close()
        for timer in self.socket.timers:
            timer.cancel()
        await asyncio.gather(*self.socket.timers, return_exceptions=True)

    async def until(self, predicate, timeout=2):
        async with asyncio.timeout(timeout):
            while not predicate():
                await asyncio.sleep(.002)

    async def start(self, renew=True):
        event = await self.demos.start(1, 1, physical=True)
        run = self.coordinator.active[1]
        if renew:
            async def pump():
                while not run.terminal:
                    self.demos.renew(1, event.id_ejecucion)
                    await asyncio.sleep(.1)
            self.pump = asyncio.create_task(pump())
        return run

    def orders(self):
        return [frame for frame in self.socket.frames if frame['tipo'] == 'orden']

    async def test_order_duration_pause_release_and_confirmed_terminal(self):
        run = await self.start()
        await asyncio.wait_for(run.task, 2)
        self.assertEqual([f['codigo'] for f in self.orders()], [2, 10])
        frames = [(t, f) for t, f in self.socket.timeline if f['tipo'] in ('orden','parar')]
        self.assertEqual([f['tipo'] for _, f in frames], ['parar','orden','parar','orden','parar','parar'])
        for start, stop, next_start in [(frames[1][0], frames[2][0], frames[3][0])]:
            self.assertGreaterEqual(stop-start, .075)
            self.assertLess(stop-start, .18)
            self.assertGreaterEqual(next_start-stop, .065)
        self.assertEqual(run.terminal.tipo, 'demo_finalizada')
        self.assertTrue(run.terminal.salidas_aplicadas_confirmadas)
        self.assertFalse(run.terminal.ejecucion_fisica_confirmada)
        self.assertEqual(self.device.code, 0)
        self.assertNotIn(1, self.devices.leases)
        self.assertEqual(self.repo.records, [])

    async def test_cancel_held_movement_is_immediate_and_suppresses_next_step(self):
        self.repo.duration = 5000
        run = await self.start()
        await self.until(lambda: self.device.code == 2)
        terminal = await asyncio.wait_for(self.demos.cancel(1), .3)
        self.assertEqual(terminal.tipo, 'demo_cancelada')
        self.assertEqual(self.device.code, 0)
        self.assertEqual(len(self.orders()), 1)

    async def test_cancel_pause_never_starts_next_movement(self):
        self.repo.pause = 5000
        run = await self.start()
        await self.until(lambda: len(self.orders()) == 1 and self.device.code == 0)
        await self.demos.cancel(1)
        self.assertEqual(len(self.orders()), 1)
        self.assertEqual(run.terminal.tipo, 'demo_cancelada')

    async def test_browser_connection_loss_stops_and_expired_id_cannot_resume(self):
        self.repo.duration = 5000
        run = await self.start(renew=False)
        await asyncio.wait_for(run.task, 1.5)
        self.assertEqual(run.terminal.tipo, 'error')
        self.assertIn('página', run.terminal.mensaje)
        self.assertEqual(self.device.code, 0)
        self.assertEqual(len(self.orders()), 1)
        with self.assertRaises(ServiceError): self.demos.renew(1, run.execution)

    async def test_loss_during_pause_stops_without_next_order(self):
        self.repo.pause = 5000
        run = await self.start(renew=False)
        await asyncio.wait_for(run.task, 1.5)
        self.assertEqual(len(self.orders()), 1)
        self.assertEqual(self.device.code, 0)

    async def test_device_disconnect_never_replays_after_reconnection(self):
        self.repo.duration = 5000
        run = await self.start()
        await self.until(lambda: self.device.code == 2)
        await self.devices.disconnect(1, self.device)
        await asyncio.wait_for(run.task, .5)
        self.assertEqual(run.terminal.tipo, 'error')
        self.assertFalse(run.terminal.salidas_aplicadas_confirmadas)
        replacement = TimedSocket(self.devices, 1)
        replacement.device = await self.devices.connect(1, replacement)
        self.assertEqual([f['tipo'] for f in replacement.frames], ['saludo'])
        self.assertEqual(len(self.orders()), 1)

    async def test_serial_takeover_interrupts_sequence(self):
        self.repo.duration = 5000
        run = await self.start()
        await self.until(lambda: self.device.code == 2)
        self.socket.mode = 'serial'
        await self.devices.message(1, self.device, dict(tipo='estado',sesion=self.device.session,
            modo='serial',codigo=0,motivo='modo_serial'))
        await asyncio.wait_for(run.task, .5)
        self.assertEqual(run.terminal.tipo, 'error')
        self.assertEqual(len(self.orders()), 1)

    async def test_rejected_ack_stops_without_success_event_or_retry(self):
        self.socket.reject_order = True
        run = await self.start()
        await asyncio.wait_for(run.task, .5)
        self.assertEqual(run.terminal.tipo, 'error')
        self.assertEqual(len(self.orders()), 1)
        self.assertFalse(any(e.tipo == 'demo_movimiento' for e in self.manager.events))
        self.assertEqual(self.device.code, 0)

    async def test_sql_blocked_does_not_block_physical_cancellation(self):
        self.repo.block = True
        run = await self.start()
        await self.until(self.repo.entered.is_set)
        cancellation = asyncio.create_task(self.demos.cancel(1))
        await self.until(lambda: 1 not in self.devices.leases)
        self.assertEqual(self.device.code, 0)
        self.assertEqual(self.orders(), [])
        self.repo.release.set()
        await asyncio.wait_for(cancellation, .5)
        self.assertEqual(run.terminal.tipo, 'demo_cancelada')
        self.assertEqual(self.orders(), [])

    async def test_sql_failure_leaves_outputs_zero(self):
        self.repo.fail = True
        run = await self.start()
        await asyncio.wait_for(run.task, .5)
        self.assertEqual(run.terminal.tipo, 'error')
        self.assertEqual(self.orders(), [])
        self.assertEqual(self.device.code, 0)

    async def test_demo_excludes_manual_control_other_demo_and_wrong_heartbeat(self):
        self.repo.duration = 5000
        run = await self.start()
        with self.assertRaises(ServiceError): await self.devices.acquire(1)
        with self.assertRaises(ServiceError): await self.demos.start(1, 1, physical=True)
        with self.assertRaises(ServiceError): self.demos.renew(1, '0'*32)
        await self.demos.cancel(1)

    async def test_manual_lease_prevents_demo(self):
        result = await self.devices.acquire(1)
        with self.assertRaises(ServiceError): await self.demos.start(1, 1, physical=True)
        await self.devices.stop(1, result['lease_id'])

    async def test_unsupported_plan_is_rejected_before_any_order(self):
        for code in (8, 9, 99, 'no-codigo'):
            self.repo.bad_code = code
            with self.assertRaises(ServiceError) as error: await self.demos.start(1, 1, physical=True)
            self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.orders(), [])

    async def test_no_device_or_zero_duration_is_rejected(self):
        self.repo.duration = 0
        with self.assertRaises(ServiceError): await self.demos.start(1, 1, physical=True)
        self.device.ready = False
        with self.assertRaises(ServiceError): await self.demos.start(1, 1, physical=True)
        self.assertEqual(self.orders(), [])

    async def test_old_firmware_cannot_silently_ignore_duration(self):
        self.device.timed_demo = False
        with self.assertRaises(ServiceError) as error: await self.demos.start(1, 1, physical=True)
        self.assertIn('firmware', error.exception.detail)
        self.assertEqual(self.orders(), [])

    async def test_cancel_during_delayed_ack_releases_before_response_and_ignores_stale_ack(self):
        self.repo.duration = 5000
        self.socket.ack_delay = .18
        run = await self.start()
        await self.until(lambda: self.socket.code == 2)
        cancellation = asyncio.create_task(self.demos.cancel(1))
        await self.until(lambda: self.socket.code == 0, .1)
        await asyncio.wait_for(cancellation, .5)
        self.assertEqual(self.device.code,0)
        self.assertEqual(len(self.orders()),1)
        self.assertFalse(any(e.tipo=='demo_movimiento' for e in self.manager.events))
        self.assertEqual(run.terminal.tipo,'demo_cancelada')

    async def test_unconfirmed_stop_is_error_never_success(self):
        run = await self.start()
        await self.until(lambda: self.device.code == 2)
        self.socket.drop_stop_ack = True
        with patch('app.services.device_service.STOP_ACK_SECONDS', .025):
            with self.assertRaises(ServiceError):
                await asyncio.wait_for(self.demos.cancel(1), .5)
        self.assertEqual(run.terminal.tipo,'error')
        self.assertFalse(run.terminal.salidas_aplicadas_confirmadas)
        self.assertEqual(self.socket.code,0)

    async def test_missing_order_ack_still_releases_at_local_duration(self):
        self.socket.drop_order_ack = True
        run = await self.start()
        await self.until(lambda: len(self.orders()) == 1)
        await asyncio.sleep(.12)
        self.assertEqual(self.socket.code, 0)
        self.assertFalse(run.task.done())
        await asyncio.wait_for(run.task, 1)
        self.assertEqual(run.terminal.tipo, 'error')
        self.assertEqual(len(self.orders()), 1)

    async def test_shutdown_releases_held_outputs(self):
        self.repo.duration = 5000
        run = await self.start()
        await self.until(lambda: self.device.code == 2)
        await asyncio.wait_for(self.demos.close(), .3)
        self.assertEqual(self.device.code, 0)
        self.assertEqual(len(self.orders()), 1)


class PhysicalDemoHttpTests(unittest.TestCase):
    def test_physical_requests_validate_auth_and_input_and_do_not_fall_back_to_record(self):
        app = create_app(Settings(_env_file=None,control_token=SecretStr('test-only')), DemoRepository())
        auth = {'Authorization':'Bearer test-only'}
        with TestClient(app) as client:
            path = '/vehiculos/1/demos'
            self.assertEqual(client.post(path, json={'id_demo':1,'modo':'fisico'}).status_code, 401)
            self.assertEqual(client.post(path, headers=auth,json={'id_demo':1,'modo':'fisico'}).status_code, 409)
            self.assertEqual(client.post(path, headers=auth,json={'id_demo':1,'modo':'otro'}).status_code, 422)
            heartbeat = path+'/activa/latido'
            self.assertEqual(client.post(heartbeat,json={'id_ejecucion':'0'*32}).status_code, 401)
            self.assertEqual(client.post(heartbeat,headers=auth,json={'id_ejecucion':'0'*32}).status_code, 409)
            self.assertEqual(client.post(heartbeat,headers=auth,json={'id_ejecucion':'bad'}).status_code, 422)
            self.assertEqual(client.get('/panel/demo-control.js').status_code, 200)
