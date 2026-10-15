from contextlib import contextmanager
from collections.abc import Iterator

import mysql.connector
from mysql.connector.abstracts import MySQLConnectionAbstract

from app.core.config import Settings
from app.core.errors import DatabaseUnavailable, ServiceError


class Database:
    """Una conexión por unidad de trabajo; nunca se comparte entre hilos."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[MySQLConnectionAbstract]:
        if not self.settings.mysql_password.get_secret_value():
            raise ServiceConfigError()
        connection = None
        try:
            connection = mysql.connector.connect(
                host=self.settings.mysql_host,
                port=self.settings.mysql_port,
                user=self.settings.mysql_user,
                password=self.settings.mysql_password.get_secret_value(),
                database=self.settings.mysql_database,
                autocommit=False,
                connection_timeout=5,
                read_timeout=5,
                write_timeout=5,
                use_pure=True,
            )
            # Las lecturas de conectado participan en la transacción de escritura.
            connection.start_transaction(
                isolation_level="SERIALIZABLE" if write else "REPEATABLE READ",
                readonly=not write,
            )
            yield connection
            connection.commit()
        except mysql.connector.Error as exc:
            if connection is not None:
                try:
                    connection.rollback()
                except mysql.connector.Error:
                    pass
            # No exponer mensajes del driver (servidor, usuario o SQL internos).
            if exc.errno == 1062:
                raise ServiceError(409, "Ya existe un registro con esos valores únicos.") from None
            if exc.errno == 1451:
                raise ServiceError(409, "No se puede eliminar o actualizar: existen registros relacionados.") from None
            if exc.errno in (1452, 1048, 1264, 1406):
                raise ServiceError(422, "Los datos no cumplen las restricciones de la base de datos.") from None
            if exc.errno in (1205, 1213):
                raise ServiceError(409, "Conflicto entre transacciones. Consulta el recurso antes de reintentar.") from None
            raise DatabaseUnavailable() from None
        except BaseException:
            if connection is not None:
                try:
                    connection.rollback()
                except mysql.connector.Error:
                    pass
            raise
        finally:
            if connection is not None:
                try:
                    connection.close()
                except mysql.connector.Error:
                    pass


class ServiceConfigError(DatabaseUnavailable):
    def __init__(self):
        super().__init__()
        self.detail = "Configura MYSQL_PASSWORD personalmente en .env y reinicia la API."
