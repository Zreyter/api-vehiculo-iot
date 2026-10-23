import unittest
from unittest.mock import patch

from pydantic import SecretStr

from app.core.config import Settings
from app.core.database import Database
from app.core.errors import ServiceError
from app.repositories.vehicle_repository import VehicleRepository
from tests.catalog_mysql import FakeMySQL


class DeviceRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeMySQL()
        patcher = patch('app.core.database.mysql.connector.connect',side_effect=self.server.connect)
        patcher.start();self.addCleanup(patcher.stop)
        self.repo = VehicleRepository(Database(Settings(_env_file=None,mysql_password=SecretStr('fake-only'))))

    def test_device_catalogue_resolves_codes_and_rejects_inactive_vehicle(self):
        self.assertEqual(self.repo.device_catalog(1),{2:102,10:110})
        self.server.data['vehiculos'][1]['activo']=0
        with self.assertRaises(ServiceError):self.repo.device_catalog(1)

    def test_device_catalogue_rejects_ambiguous_active_codes(self):
        self.server.data['comandos'][110]['codigo']=2
        with self.assertRaises(ServiceError):self.repo.device_catalog(1)

    def test_physical_demo_button_can_be_logged_without_starting_sql_sequence(self):
        self.server.data['comandos'][102].update(nombre='DEMO',codigo=8)
        with self.assertRaises(ServiceError):self.repo.apply(1,102,'Panel web')
        state=self.repo.apply_device(1,102)
        self.assertEqual(state['codigo'],8)
        records=self.repo.history(1,10)
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['origen'],'Panel WiFi')

    def test_device_logging_does_not_claim_sensor_connectivity(self):
        state=self.repo.apply_device(1,102)
        self.assertEqual(state['conectado'],0)
