"""Red con demora y permisos/seq iguales al firmware; nunca usa la placa real."""
import asyncio
import time
import unittest

from app.core.errors import ServiceError
from app.services.coordinator import VehicleCoordinator
from app.services.device_service import DeviceService
from tests.fakes import RecordingManager
from tests.test_device import Repository


class DelayedDevice:
    def __init__(self, service, delay=.02):
        self.service, self.delay = service, delay
        self.device = None
        self.frames, self.applied, self.tasks = [], [], set()
        self.mode, self.code, self.sequence = 'wifi', 0, 0
        self.permission = None

    async def accept(self): pass

    async def close(self, **kwargs):
        for task in tuple(self.tasks): task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def send_json(self, frame):
        self.frames.append(dict(frame))
        if frame['tipo'] == 'saludo': return
        task = asyncio.create_task(self.deliver(dict(frame)))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def deliver(self, frame):
        await asyncio.sleep(self.delay)
        kind, seq = frame['tipo'], frame.get('seq', 0)
        if kind == 'latido': return
        response = {'sesion':self.device.session, 'seq':seq}
        if seq <= self.sequence:
            response.update(tipo='ack',modo=self.mode,codigo=self.code,ok=False,motivo='secuencia_antigua')
        elif kind == 'preparar':
            nonce = 'nonce-'+str(seq)
            self.permission = (seq, frame['control'], nonce, time.monotonic()+.5)
            response.update(tipo='preparado',permiso=nonce if self.mode=='wifi' else '')
        else:
            ok = kind == 'parar' or bool(self.permission and self.mode=='wifi' and
                self.permission[:3] == (seq,frame['control'],frame['permiso']) and time.monotonic()<self.permission[3])
            self.permission = None
            if ok:
                self.sequence = seq
                self.code = frame.get('codigo',0)
                self.applied.append(self.code)
            response.update(tipo='ack',modo=self.mode,codigo=self.code,ok=ok,duracion_ms=0)
        await asyncio.sleep(self.delay)
        await self.service.message(1,self.device,response)


async def connected(*,prepare_ahead=True,delay=.02):
    service = DeviceService(Repository(),RecordingManager(),VehicleCoordinator(),prepare_ahead=prepare_ahead)
    service.start()
    socket = DelayedDevice(service,delay)
    socket.device = await service.connect(1,socket)
    await service.message(1,socket.device,{'tipo':'listo','sesion':socket.device.session,'modo':'wifi','codigo':0})
    key = (await service.acquire(1))['lease_id']
    return service,socket,key


class LatencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service,self.socket,self.key = await connected()

    async def asyncTearDown(self):
        await self.service.close()

    async def test_ready_input_uses_one_roundtrip_and_old_firmware_protocol(self):
        before=len(self.socket.frames)
        result=await self.service.command(1,self.key,2)
        self.assertTrue(result['permiso_anticipado'])
        self.assertEqual([f['tipo'] for f in self.socket.frames[before:]],['orden'])
        self.assertEqual(self.socket.applied[-1],2)

    async def test_expired_cached_permission_is_not_reused(self):
        lease=self.service.leases[1]
        seq,nonce,created=lease.prepared
        lease.prepared=(seq,nonce,created-1)
        before=len(self.socket.frames)
        result=await self.service.command(1,self.key,2)
        self.assertFalse(result['permiso_anticipado'])
        self.assertEqual([f['tipo'] for f in self.socket.frames[before:]],['preparar','orden'])

    async def test_background_refresh_does_not_activate_or_renew_outputs(self):
        await asyncio.sleep(.28)
        self.assertGreaterEqual(sum(f['tipo']=='preparar' for f in self.socket.frames),2)
        self.assertEqual(self.socket.applied,[0])
        self.assertFalse(any(f['tipo'] in ('orden','latido') for f in self.socket.frames))

    async def test_stop_overtakes_waiting_permission_and_prevents_late_activation(self):
        self.service.leases[1].prepared=None
        before=len(self.socket.frames)
        command=asyncio.create_task(self.service.command(1,self.key,2))
        while not any(f['tipo']=='preparar' for f in self.socket.frames[before:]):await asyncio.sleep(.001)
        response=await self.service.command(1,self.key,0)
        self.assertTrue(response['salidas_confirmadas'])
        self.assertTrue((await command)['cancelado'])
        self.assertNotIn(2,self.socket.applied)
        self.assertTrue(self.service.status(1)['listo'])

    async def test_stop_overtakes_pending_ack_and_late_reply_does_not_restore_output(self):
        command=asyncio.create_task(self.service.command(1,self.key,2))
        while 2 not in self.socket.applied:await asyncio.sleep(.001)
        await self.service.command(1,self.key,0)
        await command
        await self.service.queues[1].join()
        self.assertEqual(self.service.repository.records,[(1,102)])
        self.assertEqual(self.socket.code,0)
        self.assertEqual(self.service.status(1)['codigo_activo'],0)

    async def test_serial_takeover_discards_prepared_permission(self):
        self.socket.mode,self.socket.code='serial',10
        await self.service.message(1,self.socket.device,{'tipo':'estado','sesion':self.socket.device.session,'modo':'serial','codigo':10})
        before=len(self.socket.frames)
        with self.assertRaises(ServiceError):await self.service.command(1,self.key,2)
        await self.service.stop(1,self.key)
        self.assertEqual(len(self.socket.frames),before)
        self.assertEqual(self.socket.code,10)

    async def test_disconnect_and_new_session_cannot_reuse_prefetched_permission(self):
        lease=self.service.leases[1]
        await self.service.disconnect(1,self.socket.device)
        self.assertIsNone(lease.prepared)
        with self.assertRaises(ServiceError):await self.service.command(1,self.key,2)

    async def test_background_permission_is_single_use(self):
        await self.service.command(1,self.key,2)
        before=len(self.socket.frames)
        await self.service.command(1,self.key,10)
        types=[f['tipo'] for f in self.socket.frames[before:]]
        self.assertEqual(types,['preparar','orden'])
        self.assertEqual(self.socket.applied[-2:],[2,10])
