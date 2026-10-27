"""Pulsaciones rápidas, escrituras RDS lentas y solicitudes HTTP reordenadas."""
import asyncio
import time
import unittest

from app.core.errors import ServiceError
from app.models.device import DeviceCommand
from app.services.coordinator import VehicleCoordinator
from app.services.device_service import DeviceService
from tests.fakes import RecordingManager
from tests.test_device import Repository, Socket


class RapidTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repo=Repository()
        self.service=DeviceService(self.repo,RecordingManager(),VehicleCoordinator())
        self.service.start()
        self.socket=Socket(self.service,1)
        self.device=await self.service.connect(1,self.socket)
        self.socket.device=self.device
        await self.service.message(1,self.device,{'tipo':'listo','sesion':self.device.session,'modo':'wifi','codigo':0})
        self.key=(await self.service.acquire(1))['lease_id']

    async def asyncTearDown(self):
        self.repo.block=False;self.repo.unblock.set()
        await self.service.close()

    async def test_full_log_queue_checks_capacity_before_activating_and_keeps_session(self):
        self.repo.block=True
        await self.service.command(1,self.key,2)
        while not self.repo.entered.is_set():await asyncio.sleep(.001)
        for _ in range(32):
            await self.service.command(1,self.key,2)
        before=len(self.socket.frames)
        receipt=await self.service.command(1,self.key,10)
        self.assertTrue(receipt['cancelado'])
        self.assertTrue(receipt['registro_ocupado'])
        self.assertTrue(receipt['salidas_confirmadas'])
        self.assertFalse(any(f['tipo']=='orden' for f in self.socket.frames[before:]))
        self.assertEqual(self.socket.code,0)
        self.assertIn(1,self.service.leases)
        self.repo.block=False;self.repo.unblock.set()
        await self.service.queues[1].join()
        self.assertEqual(len(self.repo.records),33)
        await self.service.renew(1,self.key)
        self.assertTrue((await self.service.command(1,self.key,10))['salidas_confirmadas'])

    async def test_old_activation_arriving_after_release_is_not_applied(self):
        await self.service.command(1,self.key,0,intent=2)
        before=len(self.socket.frames)
        receipt=await self.service.command(1,self.key,2,intent=1)
        self.assertTrue(receipt['cancelado'])
        self.assertEqual(self.socket.code,0)
        self.assertEqual(len(self.socket.frames),before)

    async def test_old_release_cannot_stop_newer_intent(self):
        await self.service.command(1,self.key,10,intent=2)
        receipt=await self.service.command(1,self.key,0,intent=1)
        self.assertTrue(receipt['cancelado'])
        self.assertEqual(self.socket.code,10)

    async def test_duplicate_activation_is_not_replayed_or_logged_twice(self):
        await self.service.command(1,self.key,2,intent=1)
        self.assertTrue((await self.service.command(1,self.key,2,intent=1))['cancelado'])
        await self.service.queues[1].join()
        self.assertEqual(self.repo.records,[(1,102)])

    async def test_expired_owner_may_release_but_cannot_activate(self):
        self.service.leases[1].deadline=time.monotonic()-1
        result=await self.service.command(1,self.key,0)
        self.assertTrue(result['salidas_confirmadas'])
        self.assertTrue(result['sesion_finalizada'])
        with self.assertRaises(ServiceError):await self.service.command(1,self.key,2)

    async def test_cleanup_after_confirmed_terminal_stop_uses_proof_without_new_frames(self):
        await self.service.stop(1,self.key)
        before=len(self.socket.frames)
        result=await self.service.command(1,self.key,0)
        self.assertTrue(result['salidas_confirmadas'])
        self.assertTrue(result['sesion_finalizada'])
        self.assertEqual(len(self.socket.frames),before)

    async def test_old_cleanup_never_interrupts_new_owner(self):
        await self.service.stop(1,self.key)
        other=(await self.service.acquire(1))['lease_id']
        await self.service.command(1,other,10)
        before=len(self.socket.frames)
        with self.assertRaises(ServiceError):await self.service.command(1,self.key,0)
        self.assertEqual(len(self.socket.frames),before)
        self.assertEqual(self.socket.code,10)

    async def test_terminal_stop_proof_does_not_claim_serial_is_released(self):
        await self.service.stop(1,self.key)
        self.socket.mode,self.socket.code='serial',10
        await self.service.message(1,self.device,{'tipo':'estado','sesion':self.device.session,'modo':'serial','codigo':10})
        before=len(self.socket.frames)
        with self.assertRaises(ServiceError):await self.service.command(1,self.key,0)
        self.assertEqual(len(self.socket.frames),before)
        self.assertEqual(self.socket.code,10)

    async def test_prior_transient_zero_is_not_terminal_proof(self):
        await self.service.command(1,self.key,0)
        self.service._retire(1,'watchdog')
        with self.assertRaises(ServiceError):await self.service.command(1,self.key,0)

    async def test_reordered_intents_while_preparing_apply_only_latest(self):
        from tests.test_latency import connected
        service,socket,key=await connected(delay=.02)
        try:
            service.leases[1].prepared=None
            first=asyncio.create_task(service.command(1,key,2,intent=1))
            await asyncio.sleep(.01)
            second=asyncio.create_task(service.command(1,key,10,intent=2))
            self.assertTrue((await first)['cancelado'])
            self.assertTrue((await second)['salidas_confirmadas'])
            self.assertNotIn(2,socket.applied)
            self.assertEqual(socket.code,10)
        finally:await service.close()

    async def test_duplicate_zero_does_not_release_twice(self):
        await self.service.command(1,self.key,0,intent=2)
        before=len(self.socket.frames)
        self.assertTrue((await self.service.command(1,self.key,0,intent=2))['cancelado'])
        self.assertEqual(len(self.socket.frames),before)

    async def test_model_rejects_invalid_or_unsafe_intent_numbers(self):
        from pydantic import ValidationError
        for value in (True,0,-1,1.5,9007199254740992):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                DeviceCommand(lease_id=self.key,codigo=2,intencion=value)
        self.assertEqual(DeviceCommand(lease_id=self.key,codigo=2,intencion=3).intencion,3)
