"""HTTP, permisos comerciales y SP simulados, sin cuentas ni vehículos reales."""
import unittest
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.claves_comerciales import huella
from app.core.config import Settings
from app.core.database import Database
from app.main import create_app
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.comercial import ComercialRepository
from app.repositories.vehicle_repository import VehicleRepository
from tests.catalog_mysql import FakeMySQL


class Accounts:
    """Simula solo las filas SQL de sesión y propiedad; usa los permisos reales."""
    def __init__(self):
        self.sessions = {
            huella(token): {"id_usuario": ident, "rol": role, "segundos": 3600}
            for token, ident, role in (("admin-session", 10, "admin"),
                                       ("buyer-session", 20, "usuario"),
                                       ("other-session", 30, "usuario"))
        }
        self.ownership = {(20, 1)}

    @contextmanager
    def transaction(self, **kwargs):
        yield self

    @contextmanager
    def cursor(self, **kwargs):
        yield AccountCursor(self)


class AccountCursor:
    def __init__(self, database):
        self.database = database
        self.row = None

    def execute(self, sql, args):
        if "s.token_hash=%s" in sql:
            self.row = self.database.sessions.get(args[0])
        elif "FROM comercial_propiedad" in sql:
            self.row = {"ok": 1} if tuple(args) in self.database.ownership else None
        else:
            raise AssertionError("Consulta inesperada en la prueba de permisos")

    def fetchone(self):
        return self.row


class CommercialCatalogPermissions(unittest.TestCase):
    def setUp(self):
        self.mysql = FakeMySQL()
        patcher = patch("app.core.database.mysql.connector.connect", side_effect=self.mysql.connect)
        patcher.start()
        self.addCleanup(patcher.stop)
        settings = Settings(_env_file=None, comercial_habilitado=True,
                            mysql_password="test-only-password", control_token="legacy-token")
        db = Database(settings)
        self.app = create_app(settings, VehicleRepository(db), CatalogRepository(db))
        self.accounts = Accounts()
        self.app.state.comercial = ComercialRepository(self.accounts)
        self.app.state.catalog_service.verificar_demo = None
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def send(self, method, path, token="admin-session", body=None):
        headers = {"Authorization": "Bearer " + token} if token else {}
        return self.client.request(method, path, headers=headers, json=body)

    def test_admin_reads_edits_deactivates_and_reactivates_without_ownership(self):
        history = deepcopy(self.mysql.data["historial"])
        for unit in (1, 2):
            result = self.send("GET", f"/admin/vehiculos/{unit}/comandos")
            self.assertEqual(result.status_code, 200, result.text)
        path = "/admin/vehiculos/1/comandos/102"
        for active in (0, 1):
            data = {"nombre": "Avanzar", "codigo": 2, "descripcion": "Editado por administrador", "activo": active}
            result = self.send("PUT", path, body=data)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["activo"], active)
            rows = self.send("GET", "/admin/vehiculos/1/comandos").json()
            self.assertEqual(next(c for c in rows if c["id_comando"] == 102)["activo"], active)
        self.assertEqual(self.mysql.data["historial"], history)

    def test_buyer_reads_only_own_unit_and_cannot_edit_commands(self):
        path = "/admin/vehiculos/1/comandos"
        self.assertEqual(self.send("GET", path, "buyer-session").status_code, 200)
        self.assertEqual(self.send("GET", "/admin/vehiculos/2/comandos", "buyer-session").status_code, 403)
        self.assertEqual(self.send("GET", path, "other-session").status_code, 403)
        before = deepcopy(self.mysql.data)
        data = {"nombre": "Bloqueado", "codigo": 2, "descripcion": "", "activo": 0}
        self.assertEqual(self.send("PUT", path + "/102", "buyer-session", data).status_code, 403)
        self.assertEqual(self.mysql.data, before)

    def test_admin_catalog_access_does_not_grant_vehicle_control(self):
        for path in ("/vehiculos/1/dispositivo", "/vehiculos/1/historial",
                     "/admin/vehiculos/1/estado", "/admin/vehiculos/1/demos"):
            self.assertEqual(self.send("GET", path).status_code, 403)
        self.assertEqual(self.send("POST", "/vehiculos/1/movimientos", body={"id_comando": 102}).status_code, 403)
        self.assertEqual(self.send("GET", "/vehiculos/1/dispositivo", "buyer-session").status_code, 200)

    def test_missing_invalid_and_expired_sessions_are_rejected(self):
        path = "/admin/vehiculos/1/comandos"
        for token in (None, "invalid-session", "legacy-token"):
            self.assertEqual(self.send("GET", path, token).status_code, 401)
        del self.accounts.sessions[huella("admin-session")]
        self.assertEqual(self.send("GET", path).status_code, 401)

    def test_admin_still_gets_not_found_and_catalog_conflicts(self):
        self.assertEqual(self.send("GET", "/admin/vehiculos/999/comandos").status_code, 404)
        data = {"nombre": "Duplicado", "codigo": 10, "descripcion": "", "activo": 1}
        self.assertEqual(self.send("PUT", "/admin/vehiculos/1/comandos/102", body=data).status_code, 409)
        self.assertEqual(self.send("GET", "/admin/vehiculos", "buyer-session").status_code, 403)
