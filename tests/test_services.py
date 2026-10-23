import asyncio
import unittest

from app.core.errors import ServiceError
from app.models.schemas import MovementRequest
from app.services.coordinator import VehicleCoordinator
from app.services.demo_service import DemoService
from app.services.vehicle_service import VehicleService
from tests.fakes import MemoryRepository, RecordingManager


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repo = MemoryRepository(duration=1000)
        self.manager = RecordingManager()
        self.coordinator = VehicleCoordinator()
        self.demos = DemoService(self.repo, self.manager, self.coordinator)
        self.vehicles = VehicleService(self.repo, self.manager, self.coordinator)

    async def asyncTearDown(self):
        self.repo.release.set()
        await self.demos.close()

    async def test_cancel_interrupts_long_wait_and_prevents_later_steps(self):
        await self.demos.start(1, 1)
        while not self.repo.calls:
            await asyncio.sleep(.001)
        event = await asyncio.wait_for(self.demos.cancel(1), timeout=.2)
        self.assertEqual(event.tipo, "demo_cancelada")
        self.assertEqual(len(self.repo.calls), 1)
        self.assertEqual(self.repo.records, [])
        self.assertEqual(self.manager.events[-1].tipo, "demo_cancelada")

    async def test_cancel_during_sql_suppresses_event_and_waits_for_commit(self):
        self.repo.block = True
        await self.demos.start(1, 1)
        while not self.repo.entered.is_set():
            await asyncio.sleep(.001)
        cancellation = asyncio.create_task(self.demos.cancel(1))
        await asyncio.sleep(.01)
        # El bucle sigue respondiendo mientras SQL está bloqueado en otro hilo.
        self.assertTrue(self.coordinator.active[1].stop.is_set())
        self.assertFalse(cancellation.done())
        self.repo.release.set()
        await asyncio.wait_for(cancellation, timeout=.5)
        self.assertEqual(len(self.repo.calls), 1)
        self.assertEqual([e.tipo for e in self.manager.events], ["demo_iniciada", "demo_cancelada"])

    async def test_duplicate_demo_and_manual_movement_conflict(self):
        await self.demos.start(1, 1)
        with self.assertRaises(ServiceError) as error:
            await self.demos.start(1, 1)
        self.assertEqual(error.exception.status_code, 409)
        with self.assertRaises(ServiceError):
            await self.vehicles.move(1, MovementRequest(id_comando=102))
        await self.demos.cancel(1)
        await self.vehicles.move(1, MovementRequest(id_comando=102))

    async def test_demo_error_has_no_success_or_history(self):
        self.repo.fail = True
        await self.demos.start(1, 1)
        task = self.coordinator.active[1].task
        await asyncio.wait_for(task, timeout=.5)
        self.assertEqual([e.tipo for e in self.manager.events], ["demo_iniciada", "error"])
        self.assertEqual(self.repo.records, [])
        self.assertNotIn(1, self.coordinator.active)

    async def test_manual_failure_emits_only_error(self):
        self.repo.fail = True
        with self.assertRaises(ServiceError):
            await self.vehicles.move(1, MovementRequest(id_comando=102))
        self.assertEqual([e.tipo for e in self.manager.events], ["error"])

    async def test_two_vehicles_can_run_demos_independently(self):
        await self.demos.start(1, 1)
        await self.demos.start(2, 1)
        await self.demos.cancel(1)
        self.assertIn(2, self.coordinator.active)
        await self.demos.cancel(2)

    async def test_remote_controller_or_pending_log_blocks_legacy_writes(self):
        for remote, pending in ((True,0),(False,1)):
            self.coordinator.remote = {1:object()} if remote else {}
            self.coordinator.device_pending[1] = pending
            with self.assertRaises(ServiceError):
                await self.vehicles.move(1,MovementRequest(id_comando=102))
            with self.assertRaises(ServiceError):
                await self.demos.start(1,1)
