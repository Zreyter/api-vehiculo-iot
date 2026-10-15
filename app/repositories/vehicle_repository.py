from pydantic import ValidationError

from app.core.errors import DatabaseUnavailable, ServiceError
from app.models.schemas import DemoStep
from app.repositories.procedures import ProcedureRepository


class VehicleRepository(ProcedureRepository):
    def _vehicle(self, connection, vehicle_id: int) -> dict:
        rows = self._call(connection, "sp_obtener_vehiculo", (vehicle_id,))
        vehicle = next((r for r in rows if r.get("id_vehiculo") == vehicle_id), None)
        if vehicle is None:
            raise ServiceError(404, "Vehículo inexistente.")
        if vehicle.get("activo") != 1:
            raise ServiceError(409, "El vehículo está inactivo.")
        return vehicle

    def _commands(self, connection, vehicle_id: int) -> dict[int, dict]:
        rows = self._call(connection, "sp_obtener_comandos_vehiculo", (vehicle_id,))
        return {
            row["id_comando"]: row for row in rows
            if row.get("id_vehiculo") == vehicle_id and row.get("activo") == 1
        }

    @staticmethod
    def _command(commands: dict, command_id: int) -> dict:
        if command_id not in commands:
            raise ServiceError(422, "El comando no existe, está inactivo o no pertenece al vehículo.")
        return commands[command_id]

    def _state(self, connection, vehicle_id: int) -> dict | None:
        rows = self._call(connection, "sp_obtener_estado", (vehicle_id,))
        return next((r for r in rows if r.get("id_vehiculo") == vehicle_id), None)

    def snapshot(self, vehicle_id: int) -> dict | None:
        with self.database.transaction() as connection:
            self._vehicle(connection, vehicle_id)
            return self._state(connection, vehicle_id)

    def history(self, vehicle_id: int, limit: int) -> list[dict]:
        with self.database.transaction() as connection:
            self._vehicle(connection, vehicle_id)
            # El SP confirmado ordena fecha_hora DESC, id_historial DESC.
            return self._call(connection, "sp_obtener_historial", (vehicle_id,))[:limit]

    def apply(self, vehicle_id: int, command_id: int, origin: str | None) -> dict:
        """origin=None identifica DEMO: jamás se registra historial en ese caso."""
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            command = self._command(self._commands(connection, vehicle_id), command_id)
            # DEMO solo se inicia por su endpoint, con secuencia real de MySQL.
            if origin is not None and (
                str(command.get("nombre", "")).upper() == "DEMO"
                or str(command.get("codigo", "")).upper() == "DEMO"
            ):
                raise ServiceError(422, "Inicia DEMO mediante POST /vehiculos/{id}/demos.")
            previous = self._state(connection, vehicle_id)
            connected = previous["conectado"] if previous is not None else 0
            self._call(connection, "sp_actualizar_estado", (vehicle_id, command_id, connected))
            if origin is not None:
                self._call(connection, "sp_registrar_historial", (vehicle_id, command_id, origin))
            current = self._state(connection, vehicle_id)
            if current is None or current.get("id_comando") != command_id:
                raise DatabaseUnavailable()
        # Al salir del contexto, COMMIT ya terminó: ahora se puede emitir éxito.
        return current

    def demo_plan(self, vehicle_id: int, demo_id: int) -> tuple[list[DemoStep], dict | None]:
        with self.database.transaction() as connection:
            self._vehicle(connection, vehicle_id)
            demos = self._call(connection, "sp_obtener_demos", (vehicle_id,))
            demo = next((r for r in demos if r.get("id_demo") == demo_id and r.get("id_vehiculo") == vehicle_id), None)
            if demo is None:
                raise ServiceError(404, "La DEMO no existe o no pertenece al vehículo.")
            if demo.get("activo") != 1:
                raise ServiceError(409, "La DEMO está inactiva.")
            rows = self._call(connection, "sp_obtener_movimientos_demo", (demo_id,))
            try:
                steps = sorted((DemoStep.model_validate(row) for row in rows), key=lambda s: s.orden)
            except ValidationError:
                raise ServiceError(422, "La secuencia DEMO contiene datos inválidos.") from None
            if not steps or len({step.orden for step in steps}) != len(steps):
                raise ServiceError(422, "La DEMO está vacía o repite un orden.")
            commands = self._commands(connection, vehicle_id)
            for step in steps:
                command = self._command(commands, step.id_comando)
                # Identidad y código vienen del catálogo, nunca de una equivalencia ID=código.
                step.comando, step.codigo = command["nombre"], command["codigo"]
            return steps, self._state(connection, vehicle_id)
