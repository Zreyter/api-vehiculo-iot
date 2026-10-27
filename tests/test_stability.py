"""Regresiones de red: permisos opcionales, parada y respuestas tardías."""
import asyncio
import time
import unittest
from unittest.mock import patch

from app.core.errors import ServiceError
from app.services.coordinator import VehicleCoordinator
from app.services.device_service import DeviceService
from tests.fakes import RecordingManager
from tests.test_device import Repository
from tests.test_latency import DelayedDevice


class ReplyRelay:
    def __init__(self, service):
        self.service = service
        self.delay = {}
        self.drop = {}

    async def message(self, vehicle, device, reply):
        kind = reply['tipo']
        if self.drop.get(kind, 0):
            self.drop[kind] -= 1
            return
        await asyncio.sleep(self.delay.get(kind, 0))
        await self.service.message(vehicle, device, reply)


class StabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = DeviceService(Repository(), RecordingManager(), VehicleCoordinator())
        self.service.start()
        self.relay = ReplyRelay(self.service)
        self.socket = DelayedDevice(self.relay, .005)
        self.device = await self.service.connect(1, self.socket)
        self.socket.device = self.device
        await self.service.message(1, self.device, {
            'tipo': 'listo', 'sesion': self.device.session, 'modo': 'wifi', 'codigo': 0})
        self.key = (await self.service.acquire(1))['lease_id']
        self.renewal = asyncio.create_task(self.keep_alive())

    async def keep_alive(self):
        while True:
            await asyncio.sleep(.1)
            try:
                await self.service.renew(1, self.key)
            except ServiceError:
                return

    async def asyncTearDown(self):
        self.renewal.cancel()
        await asyncio.gather(self.renewal, return_exceptions=True)
        self.relay.delay.clear()
        self.relay.drop.clear()
        await self.service.close()

    async def test_optional_permission_timeout_does_not_revoke_held_command(self):
        await self.service.command(1, self.key, 2)
        self.relay.delay['preparado'] = .7
        await asyncio.sleep(.78)
        self.assertIn(1, self.service.leases)
        self.assertTrue(self.device.ready)
        self.assertEqual(self.socket.code, 2)

    async def test_release_waits_for_late_ack_without_disconnecting(self):
        await self.service.command(1, self.key, 2)
        self.relay.delay['ack'] = .7
        result = await self.service.command(1, self.key, 0)
        self.assertTrue(result['salidas_confirmadas'])
        self.assertIn(1, self.service.leases)
        self.assertTrue(self.device.ready)
        self.assertEqual(self.socket.code, 0)

    async def test_overlapping_releases_share_one_stop_confirmation(self):
        self.relay.delay['ack'] = .05
        before = len(self.socket.frames)
        results = await asyncio.gather(*(self.service.command(1, self.key, 0) for _ in range(5)))
        self.assertTrue(all(r['salidas_confirmadas'] for r in results))
        self.assertEqual(sum(f['tipo'] == 'parar' for f in self.socket.frames[before:]), 1)

    async def test_missing_stop_ack_retries_only_release_never_movement(self):
        await self.service.command(1, self.key, 2)
        self.relay.drop['ack'] = 1
        before = len(self.socket.frames)
        with patch('app.services.device_service.STOP_ACK_SECONDS', .1):
            result = await self.service.command(1, self.key, 0)
        self.assertTrue(result['salidas_confirmadas'])
        self.assertEqual([f['tipo'] for f in self.socket.frames[before:] if f['tipo'] != 'latido'], ['parar', 'parar'])

    async def test_old_ack_cannot_restore_pre_stop_state(self):
        seq = self.device.sequence
        await self.service.command(1, self.key, 0)
        await self.service.message(1, self.device, {'tipo': 'ack', 'sesion': self.device.session,
            'seq': seq, 'modo': 'wifi', 'codigo': 2, 'ok': True})
        self.assertEqual(self.service.status(1)['codigo_activo'], 0)

    async def test_new_movement_waits_for_pending_release(self):
        self.relay.delay['ack'] = .08
        release = asyncio.create_task(self.service.command(1, self.key, 0))
        await asyncio.sleep(.02)
        before = len(self.socket.frames)
        movement = asyncio.create_task(self.service.command(1, self.key, 2))
        await asyncio.sleep(.02)
        self.assertFalse(any(f['tipo'] == 'orden' for f in self.socket.frames[before:]))
        await release
        self.relay.delay['ack'] = 0
        self.assertTrue((await movement)['salidas_confirmadas'])

    async def test_timed_out_movement_is_not_retried_and_lease_ends(self):
        self.relay.drop['ack'] = 1
        before = len(self.socket.frames)
        with patch('app.services.device_service.ACK_SECONDS', .04):
            with self.assertRaises(ServiceError):
                await self.service.command(1, self.key, 2)
        self.assertNotIn(1, self.service.leases)
        self.assertEqual(sum(f['tipo'] == 'orden' for f in self.socket.frames[before:]), 1)
        self.assertEqual(self.socket.code, 0)

    async def test_unconfirmed_release_ends_session_and_does_not_claim_success(self):
        await self.service.command(1, self.key, 2)
        self.relay.drop['ack'] = 2
        with patch('app.services.device_service.STOP_ACK_SECONDS', .1):
            with self.assertRaises(ServiceError):
                await self.service.command(1, self.key, 0)
        self.assertNotIn(1, self.service.leases)
        self.assertFalse(self.device.ready)

    async def test_cancelled_http_request_does_not_cancel_physical_release(self):
        await self.service.command(1, self.key, 2)
        self.relay.delay['ack'] = .08
        release = asyncio.create_task(self.service.command(1, self.key, 0))
        await asyncio.sleep(.02)
        release.cancel()
        await asyncio.gather(release, return_exceptions=True)
        self.assertFalse(self.device.stopping.cancelled())
        ack = await self.device.stopping
        self.assertTrue(ack['ok'])
        self.assertEqual(self.socket.code, 0)

    async def test_retry_does_not_interrupt_serial_takeover(self):
        self.relay.drop['ack'] = 1
        release = asyncio.create_task(self.service.command(1, self.key, 0))
        await asyncio.sleep(.02)
        self.socket.mode, self.socket.code = 'serial', 10
        await self.service.message(1, self.device, {'tipo': 'estado', 'sesion': self.device.session,
            'modo': 'serial', 'codigo': 10})
        with self.assertRaises(ServiceError):
            await release
        self.assertEqual(self.socket.code, 10)

    async def test_prefetch_cooldown_and_fresh_command_after_delayed_reply(self):
        self.relay.delay['preparado'] = .5
        lease = self.service.leases[1]
        lease.prepared = None
        await asyncio.sleep(.65)
        self.assertIsNone(lease.prepared)  # El permiso tardío se descarta.
        self.assertGreater(lease.next_prepare_at, time.monotonic())
        self.relay.delay['preparado'] = 0
        before = len(self.socket.frames)
        result = await self.service.command(1, self.key, 2)
        self.assertTrue(result['salidas_confirmadas'])
        self.assertFalse(result['permiso_anticipado'])
        self.assertEqual([f['tipo'] for f in self.socket.frames[before:] if f['tipo'] != 'latido'], ['preparar', 'orden'])

    async def test_slow_optional_permission_keeps_origin_age(self):
        lease = self.service.leases[1]
        lease.prepared = None
        self.relay.delay['preparado'] = .18
        started = time.monotonic()
        async with lease.command_lock:
            await self.service._prepare(1, self.key, lease)
        self.assertLess(lease.prepared[2] - started, .02)


class AcquisitionStabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_optional_permission_failure_still_allows_safe_session(self):
        service = DeviceService(Repository(), RecordingManager(), VehicleCoordinator())
        relay = ReplyRelay(service)
        relay.drop['preparado'] = 1
        socket = DelayedDevice(relay, .005)
        socket.device = await service.connect(1, socket)
        await service.message(1, socket.device, {'tipo': 'listo', 'sesion': socket.device.session,
            'modo': 'wifi', 'codigo': 0})
        try:
            result = await service.acquire(1)
            self.assertTrue(result['lease_id'])
            self.assertTrue(socket.device.ready)
            self.assertEqual(socket.code, 0)
        finally:
            await service.close()

    async def test_session_lifetime_starts_after_handshake(self):
        service = DeviceService(Repository(), RecordingManager(), VehicleCoordinator())
        relay = ReplyRelay(service)
        relay.delay['ack'] = .3
        socket = DelayedDevice(relay, .005)
        socket.device = await service.connect(1, socket)
        await service.message(1, socket.device, {'tipo': 'listo', 'sesion': socket.device.session,
            'modo': 'wifi', 'codigo': 0})
        try:
            await service.acquire(1)
            self.assertGreater(service.leases[1].deadline - time.monotonic(), .85)
        finally:
            relay.delay.clear()
            await service.close()
