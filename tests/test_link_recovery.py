import asyncio,time,unittest
from unittest.mock import patch
from tests import test_device as existing


class LinkRecoveryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=existing.DeviceTests.asyncSetUp
    asyncTearDown=existing.DeviceTests.asyncTearDown

    async def test_missing_initial_greeting_is_retried_without_reconnecting(self):
        self.device.handshake=False;self.device.seen=time.monotonic();self.device.greeted=0
        original=self.socket.send_json
        async def reply(frame):
            await original(frame)
            if frame['tipo']=='saludo':
                await self.service.message(1,self.device,dict(tipo='listo',sesion=self.device.session,modo='wifi',codigo=0))
        self.socket.send_json=reply
        with patch('app.services.device_service.GREETING_RETRY_SECONDS',.02):
            async with asyncio.timeout(.3):
                while not self.device.handshake:await asyncio.sleep(.005)
        self.assertIs(self.service.devices[1],self.device)
        self.assertTrue(self.service.status(1)['listo'])
        self.assertEqual(self.service.status(1)['diagnostico_enlace']['conexiones'],1)
        self.assertEqual(self.device.greetings,2)

    async def test_retries_do_not_keep_a_silent_device_alive(self):
        self.device.handshake=False;self.device.seen=time.monotonic();self.device.greeted=0
        with patch('app.services.device_service.GREETING_RETRY_SECONDS',.02),patch('app.services.device_service.DEVICE_SILENCE_SECONDS',.12):
            async with asyncio.timeout(.5):
                while 1 in self.service.devices:await asyncio.sleep(.005)
        self.assertEqual(self.service.status(1)['diagnostico_enlace']['ultimo_cierre'],'reportes_dispositivo_vencidos')
        self.assertFalse(self.service.status(1)['conectado'])
        self.assertEqual(self.socket.code,0)

    async def test_active_control_never_receives_another_initial_greeting(self):
        await self.service.acquire(1)
        count=sum(f['tipo']=='saludo' for f in self.socket.frames)
        with patch('app.services.device_service.GREETING_RETRY_SECONDS',.02):await asyncio.sleep(.12)
        self.assertEqual(sum(f['tipo']=='saludo' for f in self.socket.frames),count)

    async def test_serial_mode_is_not_reset_by_greeting_retry(self):
        await self.service.message(1,self.device,dict(tipo='estado',sesion=self.device.session,modo='serial',codigo=0))
        count=self.device.greetings
        with patch('app.services.device_service.GREETING_RETRY_SECONDS',.02):await asyncio.sleep(.12)
        self.assertEqual(self.device.greetings,count)
        self.assertEqual(self.device.mode,'serial')
