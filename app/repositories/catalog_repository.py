from app.core.errors import ServiceError
from app.repositories.procedures import ProcedureRepository


class CatalogRepository(ProcedureRepository):
    """CRUD de administración con las firmas confirmadas en los CSV de MySQL."""

    @staticmethod
    def _find(rows, key, value, detail):
        row = next((r for r in rows if r.get(key) == value), None)
        if row is None:
            raise ServiceError(404, detail)
        return row

    def _vehicle(self, connection, vehicle_id):
        return self._find(self._call(connection, "sp_obtener_vehiculo", (vehicle_id,)),
                          "id_vehiculo", vehicle_id, "Vehículo inexistente.")

    def _commands(self, connection, vehicle_id):
        return [r for r in self._call(connection, "sp_obtener_comandos_vehiculo", (vehicle_id,))
                if r.get("id_vehiculo") == vehicle_id]

    def _command(self, connection, vehicle_id, command_id):
        return self._find(self._commands(connection, vehicle_id), "id_comando", command_id,
                          "El comando no existe o no pertenece al vehículo.")

    def _demos(self, connection, vehicle_id):
        return [r for r in self._call(connection, "sp_obtener_demos", (vehicle_id,))
                if r.get("id_vehiculo") == vehicle_id]

    def _demo(self, connection, vehicle_id, demo_id):
        return self._find(self._demos(connection, vehicle_id), "id_demo", demo_id,
                          "La DEMO no existe o no pertenece al vehículo.")

    def _movements(self, connection, demo_id):
        return [dict(row, id_demo=demo_id) for row in
                self._call(connection, "sp_obtener_movimientos_demo", (demo_id,))]

    def _movement(self, connection, demo_id, movement_id):
        return self._find(self._movements(connection, demo_id), "id_demo_movimiento", movement_id,
                          "El movimiento no existe o no pertenece a la DEMO.")

    @staticmethod
    def _unique(rows, field, value, *, id_field, excluding=None):
        if any(row[field] == value and row[id_field] != excluding for row in rows):
            raise ServiceError(409, f"Ya existe un registro con ese {field} en este catálogo.")

    def vehicles(self):
        with self.database.transaction() as connection:
            return self._call(connection, "sp_obtener_vehiculos", ())

    def vehicle(self, vehicle_id):
        with self.database.transaction() as connection:
            return self._vehicle(connection, vehicle_id)

    def commands(self, vehicle_id):
        with self.database.transaction() as connection:
            self._vehicle(connection, vehicle_id)
            return self._commands(connection, vehicle_id)

    def demos(self, vehicle_id):
        with self.database.transaction() as connection:
            self._vehicle(connection, vehicle_id)
            return self._demos(connection, vehicle_id)

    def movements(self, vehicle_id, demo_id):
        with self.database.transaction() as connection:
            self._vehicle(connection, vehicle_id)
            self._demo(connection, vehicle_id, demo_id)
            return self._movements(connection, demo_id)

    def state(self, vehicle_id):
        with self.database.transaction() as connection:
            self._vehicle(connection, vehicle_id)
            rows = self._call(connection, "sp_obtener_estado", (vehicle_id,))
            return next((r for r in rows if r.get("id_vehiculo") == vehicle_id), None)

    def create_vehicle(self, data):
        with self.database.transaction(write=True) as connection:
            rows = self._call(connection, "sp_crear_vehiculo", (
                data.nombre, data.modelo, data.descripcion, data.microcontrolador,
            ))
            return self._vehicle(connection, self._created_id(connection, rows, "id_vehiculo"))

    def update_vehicle(self, vehicle_id, data):
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            self._call(connection, "sp_actualizar_vehiculo", (
                vehicle_id, data.nombre, data.modelo, data.descripcion, data.microcontrolador, data.activo,
            ))
            return self._vehicle(connection, vehicle_id)

    def delete_vehicle(self, vehicle_id):
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            self._call(connection, "sp_eliminar_vehiculo", (vehicle_id,))

    def create_command(self, vehicle_id, data):
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            self._unique(self._commands(connection, vehicle_id), "codigo", data.codigo, id_field="id_comando")
            rows = self._call(connection, "sp_crear_comando", (
                vehicle_id, data.nombre, data.codigo, data.descripcion,
            ))
            return self._command(connection, vehicle_id, self._created_id(connection, rows, "id_comando"))

    def update_command(self, vehicle_id, command_id, data):
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            self._command(connection, vehicle_id, command_id)
            self._unique(self._commands(connection, vehicle_id), "codigo", data.codigo,
                         id_field="id_comando", excluding=command_id)
            self._call(connection, "sp_actualizar_comando", (
                command_id, data.nombre, data.codigo, data.descripcion, data.activo,
            ))
            return self._command(connection, vehicle_id, command_id)

    def delete_command(self, vehicle_id, command_id):
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            self._command(connection, vehicle_id, command_id)
            self._call(connection, "sp_eliminar_comando", (command_id,))

    def create_demo(self, vehicle_id, data):
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            rows = self._call(connection, "sp_crear_demo", (vehicle_id, data.nombre, data.descripcion))
            return self._demo(connection, vehicle_id, self._created_id(connection, rows, "id_demo"))

    def update_demo(self, vehicle_id, demo_id, data):
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            self._demo(connection, vehicle_id, demo_id)
            self._call(connection, "sp_actualizar_demo", (demo_id, data.nombre, data.descripcion, data.activo))
            return self._demo(connection, vehicle_id, demo_id)

    def delete_demo(self, vehicle_id, demo_id):
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            self._demo(connection, vehicle_id, demo_id)
            self._call(connection, "sp_eliminar_demo", (demo_id,))

    def create_movement(self, vehicle_id, demo_id, data):
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            self._demo(connection, vehicle_id, demo_id)
            self._command(connection, vehicle_id, data.id_comando)
            self._unique(self._movements(connection, demo_id), "orden", data.orden, id_field="id_demo_movimiento")
            rows = self._call(connection, "sp_agregar_movimiento_demo", (
                demo_id, data.id_comando, data.orden, data.duracion_ms, data.pausa_ms,
            ))
            movement_id = self._created_id(connection, rows, "id_demo_movimiento")
            return self._movement(connection, demo_id, movement_id)

    def update_movement(self, vehicle_id, demo_id, movement_id, data):
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            self._demo(connection, vehicle_id, demo_id)
            self._movement(connection, demo_id, movement_id)
            self._command(connection, vehicle_id, data.id_comando)
            self._unique(self._movements(connection, demo_id), "orden", data.orden,
                         id_field="id_demo_movimiento", excluding=movement_id)
            self._call(connection, "sp_actualizar_movimiento_demo", (
                movement_id, data.id_comando, data.orden, data.duracion_ms, data.pausa_ms,
            ))
            return self._movement(connection, demo_id, movement_id)

    def delete_movement(self, vehicle_id, demo_id, movement_id):
        with self.database.transaction(write=True) as connection:
            self._vehicle(connection, vehicle_id)
            self._demo(connection, vehicle_id, demo_id)
            self._movement(connection, demo_id, movement_id)
            self._call(connection, "sp_eliminar_movimiento_demo", (movement_id,))
