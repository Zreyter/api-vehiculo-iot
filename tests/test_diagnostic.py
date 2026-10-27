import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from scripts import diagnosticar_mysql as diagnostic


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.definitions = [{"ROUTINE_NAME": name, "ROUTINE_DEFINITION": "BEGIN SELECT 1; END"} for name in diagnostic.EXPECTED]
        self.parameters = [
            {"SPECIFIC_NAME": name, "PARAMETER_NAME": row["parametro"], "PARAMETER_MODE": row["modo"], "DTD_IDENTIFIER": row["tipo"]}
            for name, params in diagnostic.EXPECTED.items() for row in params
        ]
        self.cursor = MagicMock()
        self.connection = MagicMock()
        self.connection.cursor.return_value = self.cursor
        self.database = MagicMock()
        self.database.transaction.return_value.__enter__.return_value = self.connection
        self.repository = MagicMock()
        self.repository.snapshot.return_value = {"conectado": 0}
        self.repository.demo_plan.return_value = ([], None)
        self.queries = []

        def execute(sql, args):
            self.assertTrue(sql.startswith("SELECT "))
            self.assertIsInstance(args, tuple)
            self.queries.append(sql)
            if "information_schema.ROUTINES" in sql:
                rows = self.definitions
            elif "information_schema.PARAMETERS" in sql:
                rows = self.parameters
            elif "information_schema.TABLES" in sql:
                rows = [{"TABLE_NAME": table, "ENGINE": "InnoDB"} for table in diagnostic.TABLES]
            elif "information_schema.STATISTICS" in sql:
                rows = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": "id_vehiculo"}]
            elif "information_schema.REFERENTIAL_CONSTRAINTS" in sql:
                rows = [{"TABLE_NAME": "comandos", "CONSTRAINT_NAME": "fk_test", "REFERENCED_TABLE_NAME": "vehiculos", "UPDATE_RULE": "RESTRICT", "DELETE_RULE": "CASCADE"}]
            elif "COUNT(*)" in sql:
                rows = [{"total": 0}]
            else:
                raise AssertionError(sql)
            self.cursor.fetchall.return_value = rows
            self.cursor.fetchone.return_value = rows[0] if rows else None

        self.cursor.execute.side_effect = execute

    def run_diagnostic(self):
        settings = SimpleNamespace(mysql_password=SecretStr("test-only-password"), mysql_database="vehiculo_iot")
        output = io.StringIO()
        with patch.object(diagnostic, "Settings", return_value=settings), patch.object(diagnostic, "Database", return_value=self.database), patch.object(diagnostic, "VehicleRepository", return_value=self.repository), redirect_stdout(output):
            code = diagnostic.main()
        return code, output.getvalue()

    def test_checks_all_21_contracts_engines_and_cascades_with_only_selects(self):
        code, output = self.run_diagnostic()
        self.assertEqual(code, 0, output)
        for name in diagnostic.EXPECTED:
            self.assertIn(name + ": OK", output)
        self.assertIn("ON DELETE CASCADE", output)
        self.assertEqual(len(self.queries), 6)
        self.cursor.close.assert_called_once()

    def test_zero_argument_procedure_must_exist_even_without_parameter_rows(self):
        self.definitions = [row for row in self.definitions if row["ROUTINE_NAME"] != "sp_obtener_vehiculos"]
        code, output = self.run_diagnostic()
        self.assertEqual(code, 1)
        self.assertIn("sp_obtener_vehiculos: REVISAR", output)
        self.repository.snapshot.assert_not_called()

    def test_parameter_type_drift_is_detected(self):
        parameter = next(row for row in self.parameters if row["SPECIFIC_NAME"] == "sp_actualizar_comando" and row["PARAMETER_NAME"] == "p_nombre")
        parameter["DTD_IDENTIFIER"] = "varchar(20)"
        code, output = self.run_diagnostic()
        self.assertEqual(code, 1)
        self.assertIn("sp_actualizar_comando: REVISAR", output)
        self.repository.demo_plan.assert_not_called()
