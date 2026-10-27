from app.core.database import Database
from app.core.errors import DatabaseUnavailable


class ProcedureRepository:
    """Acceso común a SP con valores enlazados y resultados completos."""

    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _call(connection, procedure: str, args: tuple) -> list[dict]:
        # Los nombres son constantes del código, nunca entradas del usuario.
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.callproc(procedure, args)
            rows = []
            for result in cursor.stored_results():
                try:
                    rows.extend(result.fetchall())
                finally:
                    result.close()
            return rows
        finally:
            cursor.close()

    @staticmethod
    def _created_id(connection, rows: list[dict], key: str) -> int:
        if rows and key in rows[0]:
            value = rows[0][key]
        else:
            # sp_agregar_movimiento_demo no devuelve ID. LAST_INSERT_ID pertenece
            # a ESTA conexión, por lo que no se cruza con inserciones de otros clientes.
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute("SELECT LAST_INSERT_ID() AS nuevo_id")
                value = cursor.fetchone()["nuevo_id"]
            finally:
                cursor.close()
        if value is None or int(value) <= 0:
            raise DatabaseUnavailable()
        return int(value)
