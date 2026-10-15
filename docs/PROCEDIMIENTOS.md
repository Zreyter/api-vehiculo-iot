# Contrato de los 21 procedimientos almacenados

Fuentes: `sp_parametros.csv` y `sp_definiciones.csv`, exportadas por el usuario desde su MySQL local. Todos los parámetros son IN; no se inventaron parámetros OUT. `sp_obtener_vehiculos()` no recibe argumentos.

En las rutas: `v=id_vehiculo`, `c=id_comando`, `d=id_demo`, `m=id_demo_movimiento`. Los SP de estado/historial se integran en operaciones de control; no se expone una escritura arbitraria de conectado.

| Procedimiento | Integración HTTP / servicio |
| --- | --- |
| `sp_obtener_vehiculos` | `GET /admin/vehiculos` |
| `sp_obtener_vehiculo` | `GET /admin/vehiculos/{v} y validación de recursos` |
| `sp_crear_vehiculo` | `POST /admin/vehiculos` |
| `sp_actualizar_vehiculo` | `PUT /admin/vehiculos/{v}` |
| `sp_eliminar_vehiculo` | `DELETE /admin/vehiculos/{v}` |
| `sp_obtener_comandos_vehiculo` | `GET /admin/vehiculos/{v}/comandos y validación de movimiento` |
| `sp_crear_comando` | `POST /admin/vehiculos/{v}/comandos` |
| `sp_actualizar_comando` | `PUT /admin/vehiculos/{v}/comandos/{c}` |
| `sp_eliminar_comando` | `DELETE /admin/vehiculos/{v}/comandos/{c}` |
| `sp_obtener_estado` | `GET /admin/vehiculos/{v}/estado, snapshot WebSocket y conservación de conectado` |
| `sp_actualizar_estado` | `POST /vehiculos/{v}/movimientos y tarea DEMO (controlado, no admite editar conectado)` |
| `sp_registrar_historial` | `Solo POST /vehiculos/{v}/movimientos; nunca durante DEMO` |
| `sp_obtener_historial` | `GET /vehiculos/{v}/historial?limite=10` |
| `sp_obtener_demos` | `GET /admin/vehiculos/{v}/demos y validación al ejecutar DEMO` |
| `sp_crear_demo` | `POST /admin/vehiculos/{v}/demos` |
| `sp_actualizar_demo` | `PUT /admin/vehiculos/{v}/demos/{d}` |
| `sp_eliminar_demo` | `DELETE /admin/vehiculos/{v}/demos/{d}` |
| `sp_obtener_movimientos_demo` | `GET /admin/vehiculos/{v}/demos/{d}/movimientos y lectura de secuencia al iniciar DEMO` |
| `sp_agregar_movimiento_demo` | `POST /admin/vehiculos/{v}/demos/{d}/movimientos` |
| `sp_actualizar_movimiento_demo` | `PUT /admin/vehiculos/{v}/demos/{d}/movimientos/{m}` |
| `sp_eliminar_movimiento_demo` | `DELETE /admin/vehiculos/{v}/demos/{d}/movimientos/{m}` |

## Firmas confirmadas

- `sp_obtener_vehiculos()`
- `sp_obtener_vehiculo(IN p_id_vehiculo int)`
- `sp_crear_vehiculo(IN p_nombre varchar(80), IN p_modelo varchar(80), IN p_descripcion varchar(255), IN p_microcontrolador varchar(50))`
- `sp_actualizar_vehiculo(IN p_id_vehiculo int, IN p_nombre varchar(80), IN p_modelo varchar(80), IN p_descripcion varchar(255), IN p_microcontrolador varchar(50), IN p_activo tinyint(1))`
- `sp_eliminar_vehiculo(IN p_id_vehiculo int)`
- `sp_obtener_comandos_vehiculo(IN p_id_vehiculo int)`
- `sp_crear_comando(IN p_id_vehiculo int, IN p_nombre varchar(60), IN p_codigo int, IN p_descripcion varchar(255))`
- `sp_actualizar_comando(IN p_id_comando int, IN p_nombre varchar(60), IN p_codigo int, IN p_descripcion varchar(255), IN p_activo tinyint(1))`
- `sp_eliminar_comando(IN p_id_comando int)`
- `sp_obtener_estado(IN p_id_vehiculo int)`
- `sp_actualizar_estado(IN p_id_vehiculo int, IN p_id_comando int, IN p_conectado tinyint(1))`
- `sp_registrar_historial(IN p_id_vehiculo int, IN p_id_comando int, IN p_origen varchar(30))`
- `sp_obtener_historial(IN p_id_vehiculo int)`
- `sp_obtener_demos(IN p_id_vehiculo int)`
- `sp_crear_demo(IN p_id_vehiculo int, IN p_nombre varchar(80), IN p_descripcion varchar(255))`
- `sp_actualizar_demo(IN p_id_demo int, IN p_nombre varchar(80), IN p_descripcion varchar(255), IN p_activo tinyint(1))`
- `sp_eliminar_demo(IN p_id_demo int)`
- `sp_obtener_movimientos_demo(IN p_id_demo int)`
- `sp_agregar_movimiento_demo(IN p_id_demo int, IN p_id_comando int, IN p_orden int, IN p_duracion_ms int, IN p_pausa_ms int)`
- `sp_actualizar_movimiento_demo(IN p_id_demo_movimiento int, IN p_id_comando int, IN p_orden int, IN p_duracion_ms int, IN p_pausa_ms int)`
- `sp_eliminar_movimiento_demo(IN p_id_demo_movimiento int)`

## Semántica verificada en las definiciones

- Los 21 cuerpos no contienen COMMIT, ROLLBACK ni START TRANSACTION internos. La aplicación administra la transacción.
- Crear vehículo, comando y DEMO devuelve su ID mediante SELECT LAST_INSERT_ID().
- Agregar un movimiento DEMO no devuelve ID; la aplicación lo recupera inmediatamente en la misma conexión antes del COMMIT.
- Los cuatro procedimientos eliminar ejecutan DELETE físico. Los CSV no describen llaves foráneas ni triggers; sus posibles efectos de cascada deben revisarse con el diagnóstico local.
- UPDATE/DELETE no informan inexistencia. La API consulta primero el recurso y su relación dentro de la misma transacción; devuelve 404 si no existe en la ruta indicada.
- Los SP de consulta de catálogos incluyen registros inactivos. La API de administración los conserva; las operaciones de movimiento y ejecución DEMO sí exigen actividad.

El ensayo automatizado de extremo a extremo invoca los 21 nombres con firmas de estos CSV, usando un servidor simulado. No acredita por sí solo el comportamiento de MySQL real.
