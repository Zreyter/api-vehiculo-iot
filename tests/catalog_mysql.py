"""Simulación explícita de SP para probar HTTP + repositorios + transacciones.

No es MySQL y no accede a servidores. Las firmas proceden de los CSV del usuario.
"""
import csv
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


class Result:
    def __init__(self, rows):
        self.rows = deepcopy(rows)

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def callproc(self, name, args):
        self.rows = self.connection.server.call(self.connection, name, args)
        return args

    def stored_results(self):
        return iter([Result(self.rows)] if self.rows else [])

    def execute(self, sql):
        assert sql == "SELECT LAST_INSERT_ID() AS nuevo_id"
        self.connection.server.id_queries.append(self.connection)
        self.rows = [{"nuevo_id": self.connection.last_id}]

    def fetchone(self):
        return self.rows[0]

    def close(self):
        pass


class Connection:
    def __init__(self, server):
        self.server = server
        self.last_id = 0
        self.closed = False

    def start_transaction(self, *, isolation_level, readonly):
        self.readonly = readonly
        self.data = deepcopy(self.server.data)

    def cursor(self, dictionary=False):
        assert dictionary
        return Cursor(self)

    def commit(self):
        if not self.readonly:
            if self.server.fail_commit:
                raise mysql.connector.Error("commit simulado privado")
            self.server.data = self.data
            self.server.commits += 1

    def rollback(self):
        self.server.rollbacks += 1

    def close(self):
        self.closed = True


class FakeMySQL:
    def __init__(self):
        self.data = {
            "vehiculos": {
                v: {"id_vehiculo": v, "nombre": f"Vehículo de prueba {v}", "modelo": "Lab", "descripcion": "Doble de prueba", "microcontrolador": "ESP8266", "fecha_registro": NOW, "activo": 1}
                for v in (1, 2)
            },
            "comandos": {
                102: {"id_comando": 102, "id_vehiculo": 1, "nombre": "ADELANTE", "codigo": 2, "descripcion": "", "activo": 1},
                110: {"id_comando": 110, "id_vehiculo": 1, "nombre": "GIRO_CARRO_IZQUIERDA", "codigo": 10, "descripcion": "", "activo": 1},
                202: {"id_comando": 202, "id_vehiculo": 2, "nombre": "ADELANTE", "codigo": 2, "descripcion": "", "activo": 1},
            },
            "demos": {
                42: {"id_demo": 42, "id_vehiculo": 1, "nombre": "DEMO de prueba", "descripcion": "", "activo": 1},
                43: {"id_demo": 43, "id_vehiculo": 2, "nombre": "DEMO ajena", "descripcion": "", "activo": 1},
            },
            "movimientos": {
                501: {"id_demo_movimiento": 501, "id_demo": 42, "id_comando": 102, "orden": 1, "duracion_ms": 1000, "pausa_ms": 5},
                502: {"id_demo_movimiento": 502, "id_demo": 43, "id_comando": 202, "orden": 1, "duracion_ms": 1000, "pausa_ms": 5},
            },
            "estado": {
                1: {"id_vehiculo": 1, "id_comando": 102, "conectado": 0, "fecha_actualizacion": NOW},
            },
            "historial": {},
        }
        self.calls = []
        self.connections = []
        self.id_queries = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit = False
        self.fail_procedure = None
        self.fail_errno = None
        self.signatures = {}
        with (Path(__file__).resolve().parents[1] / "docs/sp_parametros.csv").open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                self.signatures.setdefault(row["procedimiento"], []).append(row)
        self.signatures["sp_obtener_vehiculos"] = []

    def connect(self, **kwargs):
        connection = Connection(self)
        self.connections.append(connection)
        return connection

    def call(self, connection, name, args):
        assert name in self.signatures, name
        assert len(args) == len(self.signatures[name]), (name, args)
        self.calls.append((name, args))
        if name == self.fail_procedure:
            raise mysql.connector.Error("detalle privado simulado", errno=self.fail_errno)
        data = connection.data
        vehicle_id = args[0] if args else None
        if name == "sp_obtener_vehiculos":
            return sorted(deepcopy(list(data["vehiculos"].values())), key=lambda r: r["id_vehiculo"])
        if name == "sp_obtener_vehiculo":
            return [deepcopy(data["vehiculos"][vehicle_id])] if vehicle_id in data["vehiculos"] else []
        if name in ("sp_obtener_comandos_vehiculo", "sp_obtener_demos"):
            table, order = ("comandos", "codigo") if name == "sp_obtener_comandos_vehiculo" else ("demos", "id_demo")
            return sorted(deepcopy([r for r in data[table].values() if r["id_vehiculo"] == vehicle_id]), key=lambda r: r[order])
        if name == "sp_obtener_movimientos_demo":
            rows = []
            for movement in data["movimientos"].values():
                if movement["id_demo"] == args[0] and movement["id_comando"] in data["comandos"]:
                    command = data["comandos"][movement["id_comando"]]
                    row = {k: v for k, v in movement.items() if k != "id_demo"}
                    rows.append(dict(row, comando=command["nombre"], codigo=command["codigo"]))
            return sorted(rows, key=lambda r: r["orden"])
        if name == "sp_obtener_estado":
            if vehicle_id not in data["estado"]:
                return []
            state = deepcopy(data["estado"][vehicle_id])
            command = data["comandos"].get(state["id_comando"], {})
            return [dict(state, vehiculo=data["vehiculos"][vehicle_id]["nombre"], comando=command.get("nombre"), codigo=command.get("codigo"))]
        if name == "sp_obtener_historial":
            rows = []
            for record in data["historial"].values():
                if record["id_vehiculo"] == vehicle_id:
                    command = data["comandos"].get(record["id_comando"], {})
                    rows.append(dict(record, comando=command.get("nombre"), codigo=command.get("codigo")))
            return sorted(rows, key=lambda r: (r["fecha_hora"], r["id_historial"]), reverse=True)
        assert not connection.readonly, "Escritura en una transacción de lectura"
        if name == "sp_actualizar_estado":
            data["estado"][vehicle_id] = dict(zip(("id_vehiculo", "id_comando", "conectado"), args), fecha_actualizacion=NOW)
            return []
        if name == "sp_registrar_historial":
            key = max(data["historial"], default=0) + 1
            data["historial"][key] = dict(zip(("id_vehiculo", "id_comando", "origen"), args), id_historial=key, fecha_hora=NOW)
            return []
        tables = {"vehiculo": "vehiculos", "comando": "comandos", "demo": "demos", "movimiento_demo": "movimientos"}
        operation, resource = name.removeprefix("sp_").split("_", 1)
        table = tables[resource]
        identifier = "id_demo_movimiento" if resource == "movimiento_demo" else "id_" + resource
        if operation in ("crear", "agregar"):
            key = max(data[table], default=0) + 1
            fields = {p["parametro"].removeprefix("p_"): value for p, value in zip(self.signatures[name], args)}
            fields[identifier] = key
            if resource != "movimiento_demo":
                fields["activo"] = 1
            if resource == "vehiculo":
                fields["fecha_registro"] = NOW
            data[table][key] = fields
            connection.last_id = key
            return [] if operation == "agregar" else [{identifier: key}]
        if operation == "actualizar":
            fields = {p["parametro"].removeprefix("p_"): value for p, value in zip(self.signatures[name], args)}
            if args[0] in data[table]:
                data[table][args[0]].update(fields)
            return []
        if operation == "eliminar":
            # Este doble simula RESTRICT para probar la traducción de error 1451.
            # Las reglas reales CASCADE/RESTRICT no se deducen de los CSV.
            blocked = (
                (resource == "vehiculo" and any(r["id_vehiculo"] == args[0] for t in ("comandos", "demos", "estado", "historial") for r in data[t].values()))
                or (resource == "comando" and any(r["id_comando"] == args[0] for t in ("movimientos", "estado", "historial") for r in data[t].values()))
                or (resource == "demo" and any(r["id_demo"] == args[0] for r in data["movimientos"].values()))
            )
            if blocked:
                raise mysql.connector.Error("foreign key privada simulada", errno=1451)
            data[table].pop(args[0], None)
            return []
        raise AssertionError(name)
