"""Diagnóstico de solo lectura. No imprime credenciales ni definiciones SQL."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.core.database import Database
from app.core.errors import ServiceError
from app.repositories.vehicle_repository import VehicleRepository

EXPECTED = {
    "sp_obtener_vehiculo": ["p_id_vehiculo"],
    "sp_obtener_comandos_vehiculo": ["p_id_vehiculo"],
    "sp_obtener_estado": ["p_id_vehiculo"],
    "sp_actualizar_estado": ["p_id_vehiculo", "p_id_comando", "p_conectado"],
    "sp_registrar_historial": ["p_id_vehiculo", "p_id_comando", "p_origen"],
    "sp_obtener_historial": ["p_id_vehiculo"],
    "sp_obtener_demos": ["p_id_vehiculo"],
    "sp_obtener_movimientos_demo": ["p_id_demo"],
}


def main():
    settings = Settings()
    if not settings.mysql_password.get_secret_value():
        print("Pendiente: introduce personalmente MYSQL_PASSWORD en .env (o usa scripts/configurar_password.py).")
        return 2
    database = Database(settings)
    repo = VehicleRepository(database)
    problems = []
    try:
        with database.transaction() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT SPECIFIC_NAME, PARAMETER_NAME, PARAMETER_MODE, DATA_TYPE, "
                    "CHARACTER_MAXIMUM_LENGTH FROM information_schema.PARAMETERS "
                    "WHERE SPECIFIC_SCHEMA=%s ORDER BY SPECIFIC_NAME, ORDINAL_POSITION",
                    (settings.mysql_database,),
                )
                signatures = {}
                for row in cursor.fetchall():
                    signatures.setdefault(row["SPECIFIC_NAME"], []).append(row)
                for name, expected in EXPECTED.items():
                    rows = signatures.get(name, [])
                    actual = [r["PARAMETER_NAME"].lower() for r in rows]
                    ok = actual == expected and all(r["PARAMETER_MODE"] == "IN" for r in rows)
                    print(f"{name}: {'OK' if ok else 'REVISAR firma o permisos de metadatos'}")
                    if not ok:
                        problems.append(name)
                    if name == "sp_registrar_historial" and rows:
                        origin = rows[-1]
                        if origin["DATA_TYPE"].lower() != "varchar" or origin["CHARACTER_MAXIMUM_LENGTH"] != 30:
                            problems.append("p_origen debe ser VARCHAR(30)")
                print("Firmas disponibles para la futura ampliación (no se implementan):")
                for name, rows in sorted(signatures.items()):
                    if name.startswith("sp_") and name not in EXPECTED:
                        print(name + "(" + ", ".join(f"{r['PARAMETER_MODE']} {r['PARAMETER_NAME']} {r['DATA_TYPE']}" for r in rows) + ")")
                cursor.execute(
                    "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (%s,%s)",
                    (settings.mysql_database, "estado_vehiculo", "historial_comandos"),
                )
                engines = {r["TABLE_NAME"]: r["ENGINE"] for r in cursor.fetchall()}
                for table in ("estado_vehiculo", "historial_comandos"):
                    ok = str(engines.get(table, "")).lower() == "innodb"
                    print(f"{table}: {'InnoDB OK' if ok else 'REVISAR motor transaccional'}")
                    if not ok:
                        problems.append(table + " requiere InnoDB")
                cursor.execute(
                    "SELECT INDEX_NAME, COLUMN_NAME FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND NON_UNIQUE=0 ORDER BY INDEX_NAME, SEQ_IN_INDEX",
                    (settings.mysql_database, "estado_vehiculo"),
                )
                indexes = {}
                for row in cursor.fetchall():
                    indexes.setdefault(row["INDEX_NAME"], []).append(row["COLUMN_NAME"])
                if ["id_vehiculo"] not in indexes.values():
                    problems.append("estado_vehiculo requiere clave única por id_vehiculo para el upsert existente")
                cursor.execute(
                    "SELECT ROUTINE_NAME, ROUTINE_DEFINITION FROM information_schema.ROUTINES "
                    "WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME IN (%s,%s)",
                    (settings.mysql_database, "sp_actualizar_estado", "sp_registrar_historial"),
                )
                definitions = cursor.fetchall()
                for row in definitions:
                    definition = row["ROUTINE_DEFINITION"]
                    if definition is None:
                        problems.append(row["ROUTINE_NAME"] + ": no se pudo verificar COMMIT interno por permisos")
                    elif re.search(r"\b(COMMIT|ROLLBACK|START\s+TRANSACTION)\b", definition, re.I):
                        problems.append(row["ROUTINE_NAME"] + ": revisar control transaccional interno")
                cursor.execute("SELECT COUNT(*) AS total FROM historial_comandos WHERE id_vehiculo=%s", (1,))
                print("Total de historial del vehículo 1:", cursor.fetchone()["total"])
            finally:
                cursor.close()
        if problems:
            print("Pendientes:")
            for problem in problems:
                print("-", problem)
            return 1
        state = repo.snapshot(1)
        steps, _ = repo.demo_plan(1, 1)
        print("Vehículo 1 activo; conectado actual:", state.get("conectado") if state else "sin estado")
        print("DEMO 1 activa; movimientos leídos:", len(steps))
        print("orden / id_comando / codigo / duracion_ms / pausa_ms")
        for step in steps:
            print(step.orden, step.id_comando, step.codigo, step.duracion_ms, step.pausa_ms, sep=" / ")
        print("Diagnóstico de lectura completado; no se modificaron datos.")
        return 0
    except ServiceError as exc:
        print(exc.detail)
        return 1
    except Exception:
        print("No se pudo completar el diagnóstico. Revisa permisos y columnas de los SP en MySQL Workbench; no se muestran detalles internos.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
