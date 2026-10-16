import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import mysql.connector
from pydantic import SecretStr

from app.core.config import PROJECT_ROOT, Settings
from app.core.database import Database
from app.core.errors import DatabaseUnavailable


class DatabaseTLSTests(unittest.TestCase):
    def settings(self, **kwargs):
        return Settings(_env_file=None, mysql_password=SecretStr("test-only"), **kwargs)

    def test_local_settings_preserve_driver_defaults(self):
        with patch("app.core.database.mysql.connector.connect", return_value=MagicMock()) as connect:
            with Database(self.settings()).transaction():
                pass
        self.assertNotIn("ssl_ca", connect.call_args.kwargs)

    def test_relative_ca_requires_certificate_and_hostname_verification(self):
        # El certificado real se valida en el driver, que aquí se simula.
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            ca = Path(directory) / "rds-ca.pem"
            ca.write_text("simulated CA", encoding="utf-8")
            with patch("app.core.database.mysql.connector.connect", return_value=MagicMock()) as connect:
                with Database(self.settings(mysql_host="db.example", mysql_ssl_ca=str(ca.relative_to(PROJECT_ROOT)))).transaction():
                    pass
            options = connect.call_args.kwargs
            self.assertEqual(options["ssl_ca"], str(ca))
            self.assertTrue(options["ssl_verify_cert"])
            self.assertTrue(options["ssl_verify_identity"])
            self.assertEqual(options["host"], "db.example")

    def test_missing_ca_blocks_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("app.core.database.mysql.connector.connect") as connect:
                with self.assertRaises(DatabaseUnavailable) as error:
                    with Database(self.settings(mysql_ssl_ca=str(Path(directory) / "missing.pem"))).transaction():
                        pass
                connect.assert_not_called()
                self.assertIn("MYSQL_SSL_CA", error.exception.detail)

    def test_tls_rejection_has_no_unverified_retry_or_driver_detail(self):
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / "rds-ca.pem"
            ca.write_text("simulated CA", encoding="utf-8")
            with patch("app.core.database.mysql.connector.connect", side_effect=mysql.connector.Error("private TLS detail")) as connect:
                with self.assertRaises(DatabaseUnavailable) as error:
                    with Database(self.settings(mysql_ssl_ca=str(ca))).transaction():
                        pass
                connect.assert_called_once()
                self.assertNotIn("private TLS detail", error.exception.detail)
