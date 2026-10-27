# Administración — Actividad 2.5

Esta ampliación integra los 13 procedimientos pendientes y expone cinco consultas auxiliares. Mantiene las rutas originales de movimiento, historial y ejecución DEMO. No cambia la base de datos ni inicia ejecuciones al editar catálogos.

## Arranque

Desde la raíz, con tu entorno `.venv` seleccionado y la API anterior detenida con Ctrl+C:

```bash
source .venv/bin/activate
python scripts/diagnosticar_mysql.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Swagger: <http://localhost:8000/docs>. Pulsa **Authorize** e introduce únicamente el valor local de `CONTROL_TOKEN`. Todas las rutas `/admin` requieren token, incluidas las consultas.

## Las 13 operaciones agregadas

En la tabla, `v` es ID de vehículo, `c` de comando, `d` de DEMO y `m` de movimiento de DEMO.

| Método | Ruta | Operación |
| --- | --- | --- |
| POST | `/admin/vehiculos` | Crear vehículo |
| GET | `/admin/vehiculos` | Listar vehículos |
| PUT | `/admin/vehiculos/{v}` | Actualizar vehículo |
| DELETE | `/admin/vehiculos/{v}` | Eliminar vehículo |
| POST | `/admin/vehiculos/{v}/comandos` | Crear comando |
| PUT | `/admin/vehiculos/{v}/comandos/{c}` | Actualizar comando |
| DELETE | `/admin/vehiculos/{v}/comandos/{c}` | Eliminar comando |
| POST | `/admin/vehiculos/{v}/demos` | Crear definición DEMO |
| PUT | `/admin/vehiculos/{v}/demos/{d}` | Actualizar DEMO |
| DELETE | `/admin/vehiculos/{v}/demos/{d}` | Eliminar DEMO |
| POST | `/admin/vehiculos/{v}/demos/{d}/movimientos` | Agregar paso |
| PUT | `/admin/vehiculos/{v}/demos/{d}/movimientos/{m}` | Actualizar paso |
| DELETE | `/admin/vehiculos/{v}/demos/{d}/movimientos/{m}` | Eliminar paso |

Las consultas auxiliares GET son `/admin/vehiculos/{v}`, `/admin/vehiculos/{v}/estado`, `/admin/vehiculos/{v}/comandos`, `/admin/vehiculos/{v}/demos` y `/admin/vehiculos/{v}/demos/{d}/movimientos`. El estado puede ser `null` si aún no se ha creado. Los catálogos incluyen activos e inactivos.

Crear una DEMO en `/admin/vehiculos/{v}/demos` guarda su definición. Para ejecutarla usa el POST original `/vehiculos/{v}/demos` con `{"id_demo":d}`; para cancelarla usa el DELETE original `/vehiculos/{v}/demos/activa`.

## Cuerpos JSON

Crear vehículo:

```json
{
  "nombre": "Vehículo de prueba",
  "modelo": "Laboratorio",
  "descripcion": "Registro auxiliar",
  "microcontrolador": "ESP8266"
}
```

Crear comando, usando el vehículo de la ruta:

```json
{
  "nombre": "COMANDO_PRUEBA",
  "codigo": 9001,
  "descripcion": "Código independiente del ID"
}
```

Crear definición DEMO:

```json
{
  "nombre": "DEMO de prueba",
  "descripcion": "Secuencia auxiliar"
}
```

Agregar o actualizar un paso, usando el ID real del comando creado:

```json
{
  "id_comando": 123,
  "orden": 1,
  "duracion_ms": 200,
  "pausa_ms": 100
}
```

Para actualizar vehículo, comando o DEMO usa sus mismos campos y agrega `"activo":1` o `"activo":0`. PUT exige todos los campos obligatorios; `descripcion` puede omitirse y se guarda como cadena vacía. Las altas no admiten `activo` porque sus SP no lo reciben: su valor inicial procede del esquema existente. Los pasos no tienen campo activo.

Límites confirmados: nombre de vehículo/DEMO y modelo, 80 caracteres; nombre de comando, 60; descripción, 255; microcontrolador, 50. IDs y orden son enteros positivos hasta 2147483647; duración y pausa son enteros no negativos hasta ese límite. codigo admite el rango de un INT firmado y nunca se obtiene a partir del ID. No se aceptan propiedades extra ni booleanos/cadenas en campos que exigen enteros.

La API exige código único por vehículo y orden único por DEMO. Para cambiar un orden a otro ya ocupado hay que liberar primero ese orden; no reordena automáticamente la secuencia. La pertenencia vehículo/comando/DEMO/paso se comprueba dentro de la transacción. Se pueden editar catálogos inactivos para reactivarlos; la ejecución sigue exigiendo recursos activos.

## Respuestas y transacciones

- POST de creación: `201` y recurso con su ID confirmado.
- GET/PUT: `200` y recurso o lista; estado ausente devuelve `null`.
- DELETE: `204` sin cuerpo, después de COMMIT.
- `401`: token ausente/incorrecto; `404`: recurso inexistente o ajeno a la ruta; `409`: DEMO activa, código/orden duplicado o conflicto de integridad; `422`: datos/referencias inválidos; `503`: fallo de configuración o MySQL.

Cada escritura usa su propia conexión y transacción SERIALIZABLE, con rollback ante errores y cierre de recursos. Una actualización/eliminación de un ID inexistente no devuelve éxito. No se expone el mensaje original del driver. Un fallo de comunicación durante COMMIT puede dejar un resultado incierto; consulta el catálogo antes de repetir una creación.

Se utiliza el mismo bloqueo por vehículo que en la DEMO. Durante una ejecución se rechazan con `409` cambios en ese vehículo, sus comandos y cualquier DEMO/paso de su catálogo. Las lecturas siguen disponibles y la cancelación conserva su señal prioritaria. Editar el catálogo no cambia conectado ni registra historial ni emite eventos de movimiento. Eliminar un vehículo con éxito cierra sus WebSocket; si la transacción falla, permanecen conectados.

## Eliminaciones físicas y pruebas auxiliares

**DELETE borra registros realmente.** Los SP existentes no desactivan ni implementan recuperación. No se modificaron sus cuerpos ni las llaves foráneas: si tu esquema tiene CASCADE, MySQL aplicará esa regla; si tiene RESTRICT, una relación pendiente devolverá `409`. Los CSV no incluyen esas reglas. Ejecuta el diagnóstico para verlas antes de probar eliminaciones.

Importa `postman/administracion_2_5.postman_collection.json` y configura `control_token` como valor local. Sus variables de IDs empiezan vacías: no tienen vehículo 1, comando 2 ni DEMO 1 como valores predeterminados. Las peticiones guardan automáticamente los IDs de registros nuevos con nombre `LAB_API_2_5`.

Ejecuta sus carpetas en orden:

1. **A. Crear registros nuevos:** vehículo, comando, DEMO y paso. Espera `201` en las cuatro peticiones. No inicia una DEMO ni envía movimiento individual.
2. **B. Consultar catálogos:** comprueba los registros creados y sus IDs; el estado del vehículo nuevo puede ser `null`.
3. **C. Actualizar:** espera `200` en los cuatro PUT; puedes repetir las consultas para comprobar los campos.
4. **D. Limpieza física:** elimina únicamente los IDs creados, en orden paso → DEMO → comando → vehículo; espera `204`. Una variable vacía impide ejecutar su petición. Si una operación falla, corrige ese punto antes de continuar.

No reemplaces esas variables con IDs de tu carro real. La limpieza está diseñada para un catálogo de prueba sin historial ni ejecución. Si ya utilizaste ese vehículo para movimientos o agregaste otras relaciones, revisa sus dependencias antes de eliminarlo.

Estas pruebas completan la validación del CRUD. Los tres escenarios de `actividad_2_5.postman_collection.json` comprueban POST individual, GET historial y WebSocket DEMO sin cambio de historial. **El entregable final será este mismo conjunto de APIs ejecutándose en EC2 y conectándose a RDS**, después de comprobar su funcionamiento local. La guía pide Thunder Client y no se presupone autorización del profesor para sustituirlo por Postman.

## Verificación automática

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -v
```

Las pruebas usan SP simulados, con firmas obtenidas de los CSV. No se conectan a MySQL ni crean/eliminan registros reales. Hay que completar la comprobación manual contra tu MySQL; el diagnóstico solo consulta metadatos y recursos existentes.
