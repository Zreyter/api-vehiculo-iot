import unittest
from unittest.mock import MagicMock, patch

import mysql.connector
from pydantic import SecretStr

from app.core.config import Settings
from app.core.database import Database
from app.core.errors import DatabaseUnavailable, ServiceError
from app.repositories.vehicle_repository import VehicleRepository


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        settings = Settings(_env_file=None, mysql_password=SecretStr("test-only"))
        self.repo = VehicleRepository(Database(settings))
        self.calls = []
        self.state = {"id_vehiculo": 1, "id_comando": 102, "comando": "ADELANTE", "codigo": 2, "conectado": 1}
        self.fail_history = False
        self.command_active = 1
        self.command_vehicle = 1
        self.vehicle_active = 1
        self.demo_active = 1
        self.demo_vehicle = 1
        self.steps = [
            {"id_demo_movimiento": 700, "orden": 77, "id_comando": 102, "comando": "texto previo", "codigo": 999, "duracion_ms": 23, "pausa_ms": 17},
            {"id_demo_movimiento": 701, "orden": 12, "id_comando": 102, "comando": "texto previo", "codigo": 999, "duracion_ms": 11, "pausa_ms": 3},
        ]

        def call(connection, procedure, args):
            self.calls.append((procedure, args))
            if procedure == "sp_obtener_vehiculo":
                return [{"id_vehiculo": 1, "activo": self.vehicle_active}]
            if procedure == "sp_obtener_comandos_vehiculo":
                return [{"id_comando": 102, "id_vehiculo": self.command_vehicle, "nombre": "ADELANTE", "codigo": 2, "activo": self.command_active}]
            if procedure == "sp_obtener_estado":
                return [self.state.copy()]
            if procedure == "sp_registrar_historial" and self.fail_history:
                raise mysql.connector.Error("detalle privado simulado")
            if procedure == "sp_obtener_historial":
                return [{"id_historial": i} for i in reversed(range(25))]
            if procedure == "sp_obtener_demos":
                return [{"id_demo": 42, "id_vehiculo": self.demo_vehicle, "activo": self.demo_active}]
            if procedure == "sp_obtener_movimientos_demo":
                return self.steps
            return []

        self.repo._call = call
        self.patcher = patch("app.core.database.mysql.connector.connect", return_value=self.connection)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_move_preserves_connected_and_commits_both_sps(self):
        result = self.repo.apply(1, 102, "Postman")
        self.assertIn(("sp_actualizar_estado", (1, 102, 1)), self.calls)
        self.assertIn(("sp_registrar_historial", (1, 102, "Postman")), self.calls)
        self.assertEqual(result["codigo"], 2)  # Código distinto del ID.
        self.connection.commit.assert_called_once()
        self.connection.rollback.assert_not_called()
        self.connection.close.assert_called_once()

    def test_history_failure_rolls_back_without_commit(self):
        self.fail_history = True
        with self.assertRaises(DatabaseUnavailable) as error:
            self.repo.apply(1, 102, "Postman")
        self.assertNotIn("privado", str(error.exception))
        self.connection.rollback.assert_called_once()
        self.connection.commit.assert_not_called()
        self.connection.close.assert_called_once()

    def test_commit_failure_rolls_back(self):
        self.connection.commit.side_effect = mysql.connector.Error("private")
        with self.assertRaises(DatabaseUnavailable):
            self.repo.apply(1, 102, "API")
        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()

    def test_demo_never_calls_history(self):
        self.repo.apply(1, 102, None)
        self.assertFalse(any(name == "sp_registrar_historial" for name, _ in self.calls))
        self.connection.commit.assert_called_once()

    def test_inactive_command_prevents_writes(self):
        self.command_active = 0
        with self.assertRaises(ServiceError):
            self.repo.apply(1, 102, "API")
        self.assertFalse(any(name == "sp_actualizar_estado" for name, _ in self.calls))
        self.connection.rollback.assert_called_once()

    def test_unrelated_command_prevents_writes(self):
        self.command_vehicle = 2
        with self.assertRaises(ServiceError):
            self.repo.apply(1, 102, "API")
        self.connection.commit.assert_not_called()

    def test_inactive_vehicle_prevents_writes(self):
        self.vehicle_active = 0
        with self.assertRaises(ServiceError):
            self.repo.apply(1, 102, "API")
        self.connection.commit.assert_not_called()

    def test_history_truncates_to_ten(self):
        self.assertEqual(len(self.repo.history(1, 10)), 10)

    def test_callproc_binds_arguments_and_closes_resources(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        result = MagicMock()
        cursor.stored_results.return_value = [result]
        result.fetchall.return_value = [{"ok": 1}]
        origin = "x'); DROP TABLE comandos; --"
        rows = VehicleRepository._call(connection, "sp_registrar_historial", (1, 102, origin))
        cursor.callproc.assert_called_once_with("sp_registrar_historial", (1, 102, origin))
        result.close.assert_called_once()
        cursor.close.assert_called_once()
        self.assertEqual(rows, [{"ok": 1}])

    def test_callproc_failure_closes_cursor(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.callproc.side_effect = mysql.connector.Error("failure")
        with self.assertRaises(mysql.connector.Error):
            VehicleRepository._call(connection, "sp_obtener_estado", (1,))
        cursor.close.assert_called_once()

    def test_demo_plan_reads_database_orders_steps_and_resolves_catalog_code(self):
        steps, _ = self.repo.demo_plan(1, 42)
        self.assertIn(("sp_obtener_movimientos_demo", (42,)), self.calls)
        self.assertEqual([s.orden for s in steps], [12, 77])
        self.assertEqual([s.duracion_ms for s in steps], [11, 23])
        self.assertEqual([s.codigo for s in steps], [2, 2])

    def test_inactive_demo_is_rejected_before_sequence(self):
        self.demo_active = 0
        with self.assertRaises(ServiceError) as error:
            self.repo.demo_plan(1, 42)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(any(name == "sp_obtener_movimientos_demo" for name, _ in self.calls))

    def test_unrelated_demo_is_rejected(self):
        self.demo_vehicle = 2
        with self.assertRaises(ServiceError) as error:
            self.repo.demo_plan(1, 42)
        self.assertEqual(error.exception.status_code, 404)

    def test_negative_demo_duration_is_rejected(self):
        self.steps[0]["duracion_ms"] = -1
        with self.assertRaises(ServiceError) as error:
            self.repo.demo_plan(1, 42)
        self.assertEqual(error.exception.status_code, 422)

    def test_repeated_demo_order_is_rejected(self):
        self.steps[1]["orden"] = 77
        with self.assertRaises(ServiceError) as error:
            self.repo.demo_plan(1, 42)
        self.assertEqual(error.exception.status_code, 422)
