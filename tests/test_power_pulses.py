import unittest
from pydantic import ValidationError
from app.core.errors import ServiceError
from app.models.device import DeviceCommand
from tests import test_device as existing


class PowerPulseTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=existing.DeviceTests.asyncSetUp
    asyncTearDown=existing.DeviceTests.asyncTearDown
    acquire=existing.DeviceTests.acquire

    async def test_both_durations_work_without_any_power_estimate(self):
        key=await self.acquire()
        self.device.power=None
        for duration in (200,2000,200,2000):
            result=await self.service.command(1,key,9,pulso_ms=duration)
            self.assertEqual(result['duracion_ms'],duration)
            self.assertIsNone(self.service.status(1)['encendido_estimado'])
            await self.service.command(1,key,0)

    async def test_invalid_or_missing_duration_never_activates(self):
        key=await self.acquire()
        before=len(self.socket.frames)
        for value in (None,0,199,201,1999,2001,True,200.0,'200'):
            with self.assertRaises(ServiceError): await self.service.command(1,key,9,pulso_ms=value)
        with self.assertRaises(ServiceError): await self.service.command(1,key,2,pulso_ms=200)
        self.assertEqual(len(self.socket.frames),before)

    async def test_old_firmware_is_rejected_instead_of_guessing(self):
        key=await self.acquire()
        self.device.explicit_power=False
        before=len(self.socket.frames)
        with self.assertRaises(ServiceError): await self.service.command(1,key,9,pulso_ms=2000)
        self.assertEqual(len(self.socket.frames),before)

    async def test_wrong_ack_duration_stops_and_does_not_log_success(self):
        key=await self.acquire()
        original=self.socket.send_json
        async def wrong_ack(frame):
            if frame['tipo']=='orden':frame={**frame,'pulso_ms':2000}
            await original(frame)
        self.socket.send_json=wrong_ack
        with self.assertRaises(ServiceError): await self.service.command(1,key,9,pulso_ms=200)
        self.assertEqual(self.device.code,0)
        self.assertNotIn(1,self.service.leases)
        self.assertEqual(self.repo.records,[])

    async def test_stop_then_another_power_pulse_does_not_require_resetting_state(self):
        key=await self.acquire()
        await self.service.command(1,key,9,pulso_ms=2000)
        await self.service.command(1,key,0)
        result=await self.service.command(1,key,9,pulso_ms=200)
        self.assertEqual(result['duracion_ms'],200)

    async def test_reported_old_estimates_are_never_shown_as_actual_power(self):
        await self.service.message(1,self.device,dict(tipo='estado',sesion=self.device.session,
            modo='wifi',codigo=0,encendido_estimado=True,pulsos_encendido_explicitos=True))
        self.assertIsNone(self.service.status(1)['encendido_estimado'])

    def test_http_duration_is_strict_integer(self):
        for value in ('200',200.0,True):
            with self.assertRaises(ValidationError):DeviceCommand(lease_id='a'*32,codigo=9,pulso_ms=value)
