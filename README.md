# Actividad 2.5 — APIs para IoT en entorno Dev

Laboratorio con FastAPI, MySQL local y WebSocket. Integra los 21 procedimientos: administración de vehículos, comandos, DEMO y sus movimientos, además de movimiento individual, historial y ejecución DEMO con inicio/cancelación. El código utiliza las firmas confirmadas en los CSV; no crea ni modifica el esquema MySQL.

## Preparación y ejecución local

Si acabas de clonar el repositorio, prepara tu propio entorno y configuración desde la raíz del proyecto:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
chmod 600 .env
python -c "import secrets; from dotenv import set_key; set_key('.env', 'CONTROL_TOKEN', secrets.token_urlsafe(32))"
```

Estos pasos son para una copia nueva: no reemplaces un `.env` existente. El repositorio incluye solo `.env.example`; la contraseña, el token y los entornos virtuales se quedan en cada computadora. Después configura personalmente la contraseña como se indica abajo.

Desde VS Code abre esta carpeta y selecciona **Python: Select Interpreter → Enter interpreter path → `.venv/bin/python`**. Tu terminal ya comprobó que el entorno original `.venv` funciona; úsalo para ejecutar el proyecto. `.venv-lab` se utilizó únicamente para verificar desde la sesión de Codex con otro Python y no es necesario activarlo en tu terminal.

```bash
source .venv/bin/activate
python --version
python -m pip --version
```

Para instalar o actualizar dependencias usa `python -m pip install -r requirements.txt`; para ejecutar las pruebas usa `requirements-dev.txt`, que agrega el cliente de pruebas.

`.env` es tu configuración privada. Conserva los valores de MySQL y `CONTROL_TOKEN` que ya usaste en las pruebas. Si falta la contraseña, introdúcela personalmente con el asistente; no es necesario volver a configurarla si ya funciona:

```bash
python scripts/configurar_password.py
```

Comprueba MySQL e inicia la API desde la raíz del proyecto:

```bash
python scripts/diagnosticar_mysql.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Para una copia nueva usa `.env.example` como base y define personalmente `MYSQL_PASSWORD` y un `CONTROL_TOKEN` aleatorio. No reemplaces tu `.env` existente. Reinicia la API después de cambiarlo. Swagger: <http://localhost:8000/docs>. Usa **Authorize → HTTPBearer** e introduce solo el token local. El token se consulta personalmente en `.env`; no lo copies a capturas, chats, repositorios ni exportaciones compartidas.

La aplicación arranca aunque falte la contraseña: Swagger sigue disponible y las operaciones que requieren MySQL responden `503`. Una configuración de token vacía también bloquea los controles con `503`. No se usa `conectado=1` por iniciar la API o abrir un WebSocket.

Usa **un solo proceso** y una sola instancia de la API para esta base. Las salas, colas y exclusión de DEMO están en memoria. Varios procesos requerirían coordinación compartida antes de utilizarlos. Puedes añadir `--reload` para editar, sabiendo que una recarga cancela la DEMO en curso. No publiques la API ni cambies el enlace a `0.0.0.0` para este laboratorio.

## Organización y POO

```text
app/
  core/          Settings, Database, autenticación y errores
  models/        Peticiones, secuencia DEMO, historial y eventos Pydantic
  repositories/  ProcedureRepository, VehicleRepository y CatalogRepository
  services/      VehicleService, DemoService, CatalogService y coordinación por vehículo
  api/           Endpoints HTTP y WebSocket
  websocket/     WebSocketManager: salas y cola independiente por cliente
  main.py        Creación de la aplicación y ciclo de vida
scripts/         Configuración personal y diagnóstico de solo lectura
tests/           Pruebas con dobles de MySQL, sin datos reales
postman/         Colección de tres escenarios y colección auxiliar de administración
docs/            Contratos de los 21 SP y guía de administración
```

El repositorio ejecuta MySQL en hilos mediante `asyncio.to_thread`, con conexiones independientes que se cierran al terminar. Los parámetros se enlazan con `callproc`; los nombres de SP son constantes. La capa HTTP no contiene SQL.

## Contrato HTTP

| Método y ruta | Cuerpo / consulta | Resultado |
| --- | --- | --- |
| `POST /vehiculos/1/movimientos` | `{"id_comando":2,"origen":"Postman"}` | `200` y evento del movimiento confirmado en BD |
| `GET /vehiculos/1/historial?limite=10` | `limite` entre 1 y 10 | Hasta diez registros, más recientes primero |
| `POST /vehiculos/1/demos` | `{"id_demo":1}` | `202` y `demo_iniciada` |
| `DELETE /vehiculos/1/demos/activa` | Sin cuerpo | `200` y `demo_cancelada`, o `409` si no hay DEMO |

Los controles POST/DELETE requieren `Authorization: Bearer <token local>`. El historial es lectura local sin token. Los IDs de ruta son positivos. `id_comando` e `id_demo` exigen enteros positivos; no se permiten propiedades extra. `origen` tiene entre 1 y 30 caracteres. `limite>10` devuelve `422`.

Las validaciones distinguen vehículo/DEMO inexistente (`404`), inactivos o DEMO simultánea (`409`), comando inválido/inactivo/ajeno (`422`), autenticación (`401`) y configuración o fallo SQL (`503`). La ausencia de estado inicial se interpreta como conexión desconocida y se guarda `conectado=0` al primer movimiento. Si ya hay estado, se conserva exactamente su `conectado`. Ninguna petición permite editar ese campo.

Los IDs de comando se validan contra `sp_obtener_comandos_vehiculo`. El código se toma del catálogo/estado devuelto por MySQL: nunca se deduce del ID. El comando llamado `DEMO` se dirige al endpoint de inicio y no se registra como movimiento individual.

Para un movimiento individual, `sp_actualizar_estado` y `sp_registrar_historial` comparten conexión y transacción. Primero se ejecuta `COMMIT`; después se publica el evento. Un fallo de escritura o confirmación provoca intento de `ROLLBACK`, error HTTP y ningún evento de éxito. Se conserva la causa SQL fuera de las respuestas; no se imprimen mensajes del driver.

Esto requiere tablas **InnoDB**, una clave única por `estado_vehiculo.id_vehiculo` para el upsert existente y SP sin `COMMIT` interno. Las transacciones de escritura usan aislamiento `SERIALIZABLE` para proteger la lectura de `conectado` frente a escrituras concurrentes. Un conflicto de integridad o entre transacciones devuelve `409`/`422`; los fallos de conexión devuelven `503`; no se reintenta automáticamente un POST para evitar duplicados. Si se pierde la conexión durante `COMMIT`, el resultado de la transacción puede ser incierto: consulta el historial antes de repetirla.

`sp_obtener_historial` devuelve actualmente todo el historial ordenado; la API recorta la respuesta a diez. Reducir la lectura en MySQL requerirá una futura revisión del SP, que no se modifica aquí.

## WebSocket

Conecta a `ws://localhost:8000/ws/vehiculos/1` con el encabezado `Authorization: Bearer <token local>`. Se acepta más de un cliente por vehículo. El primer evento es `estado`, con el último estado leído de MySQL; si no existe, `estado` es `null`. Snapshot y suscripción se coordinan con los movimientos de esta API.

El canal es de observación: no ejecuta órdenes recibidas por WebSocket. Usa HTTP para controlar. Un token inválido, un vehículo inexistente/inactivo o un fallo al leer el estado impiden la conexión (rechazo previo al handshake; código interno de cierre `1008`). No se transporta el token en la URL. Postman admite encabezados para WebSocket; un cliente de navegador necesitaría otra estrategia de autenticación antes de integrarlo.

Todos los eventos incluyen:

```json
{
  "tipo": "demo_movimiento",
  "id_vehiculo": 1,
  "id_comando": 2,
  "comando": "ADELANTE",
  "codigo": 2,
  "marca_temporal": "2026-10-14T18:00:00Z",
  "estado": {"id_vehiculo": 1, "id_comando": 2, "conectado": 0},
  "id_demo": 1,
  "orden": 1,
  "duracion_ms": 2000,
  "pausa_ms": 400,
  "mensaje": null,
  "ejecucion_fisica_confirmada": false
}
```

Es un ejemplo ilustrativo; el estado real también incluye las columnas devueltas por tu SP. `marca_temporal` es UTC de emisión; la fecha del estado/historial conserva la información de MySQL y puede no incluir zona horaria.

| `tipo` | Significado |
| --- | --- |
| `estado` | Último estado al conectar |
| `movimiento_individual` | Estado e historial confirmados |
| `demo_iniciada` | Secuencia validada y tarea creada |
| `demo_movimiento` | Estado de este paso confirmado en BD |
| `demo_finalizada` | Se consumió la secuencia con duración y pausas |
| `demo_cancelada` | Cancelación terminada; no habrá más pasos de esa ejecución |
| `error` | Fallo de una operación o de la tarea DEMO; `mensaje` explica el problema |

Las claves `id_comando`, `comando` y `codigo` siempre existen, pero son `null` cuando no se conoce un comando. Para DEMO se incluye `id_demo`; `orden`, `duracion_ms` y `pausa_ms` son `null` al iniciar y describen el último paso procesado en los eventos terminales. Un error al iniciar puede no tener estado. Cada cliente recibe solamente la sala de su vehículo y conserva orden FIFO. Se retiran desconexiones y se cierra un cliente lento si agota su cola de 64 eventos o excede dos segundos al enviar; debe reconectar para recuperar el estado actual.

La DEMO lee `sp_obtener_demos` y `sp_obtener_movimientos_demo` en cada inicio, ordena por `orden` y valida todos los comandos antes de empezar. Cada paso vuelve a validar vehículo y comando, actualiza estado sin llamar `sp_registrar_historial`, emite y espera duración + pausa de forma asíncrona. Se rechazan movimientos individuales durante DEMO con `409` para no mezclar órdenes.

Cancelar activa una señal sin esperar el candado del vehículo e interrumpe las esperas. Si MySQL ya procesa un paso, no es seguro interrumpir ese hilo: se espera su conclusión y se suprime su evento de movimiento. Ese paso puede quedar confirmado en el estado; el evento terminal lo refleja. No se inician pasos posteriores. Eventos ya enviados o en cola antes de cancelar pueden llegar antes del evento terminal. No se inventa `DETENER` ni se modifica `conectado`. Cancelar la secuencia **no demuestra que el vehículo físico se haya detenido**; para eso falta definir el comando real e integrar el ESP8266.

## Los tres escenarios de entrega en Postman

Importa `postman/actividad_2_5.postman_collection.json`. Define `control_token` como variable local sensible, sin guardar su valor en el archivo compartido. Las demás variables vienen con localhost, vehículo 1, comando 2 y DEMO 1; verifica los IDs reales con el diagnóstico. Para impedir cambios simultáneos al historial, realiza la evidencia sin otro cliente enviando movimientos individuales.

1. **POST individual.** Abre dos pestañas WebSocket al vehículo 1, agrega el encabezado de autorización a ambas y pulsa Connect. Verifica el evento inicial. Ejecuta el POST de la carpeta 1 con `id_comando=2` y `origen=Postman`. Espera `200`, un `movimiento_individual` idéntico en ambos clientes y `conectado` conservado. El código viene de MySQL. Oculta tokens en la captura.
2. **GET historial.** Ejecuta la carpeta 2 después del POST. Espera `200`, hasta diez registros, el nuevo movimiento primero y origen `Postman`. Un límite de once debe responder `422`; esta es una comprobación auxiliar del mismo servicio.
3. **WebSocket DEMO e historial sin cambios.** Con ambos WebSocket conectados, ejecuta `3.1 Historial antes`; su prueba guarda la lista localmente. Opcionalmente ejecuta `python scripts/diagnosticar_mysql.py` y anota el total completo de historial. Ejecuta `3.2 Iniciar DEMO`: espera `202`, `demo_iniciada`, cada `demo_movimiento` y `demo_finalizada` en ambos clientes. Con los datos confirmados son ocho pasos y aproximadamente 11.4 segundos más el tiempo SQL; la secuencia siempre viene de MySQL. **Espera el evento final antes de ejecutar `3.3 Historial después`**: su prueba exige la misma lista e IDs. Repite el diagnóstico para comprobar también que el total completo no cambió. Durante la secuencia, otro inicio debe responder `409`. Como comprobación auxiliar, reinicia DEMO y ejecuta `3.4 Cancelar DEMO`; verifica `demo_cancelada` y ausencia de movimientos posteriores de esa ejecución.

La colección contiene HTTP. Crea manualmente las dos pestañas WebSocket en Postman: el formato de colección HTTP utilizado no incluye su sesión de WebSocket. No ejecutes toda la carpeta 3 automáticamente sin esperar la finalización: las solicitudes HTTP no esperan los eventos del socket. El botón de cancelación se prueba en una segunda ejecución, después de obtener la evidencia de finalización.

La guía pide **Thunder Client**. Postman es la preferencia del estudiante para probar; la aceptación de su evidencia sigue pendiente de confirmación con el profesor. No se da por autorizada la sustitución ni se presentan escenarios adicionales como entregables.

## Verificación y límites

```bash
python -m unittest discover -v
```

Las pruebas automatizadas usan dobles explícitos: validan contratos HTTP, autenticación, dos clientes, aislamiento de salas, desconexiones, límites, parámetros enlazados, conservación de conexión, transacción/rollback, fallo de commit, DEMO sin historial y cancelación durante espera o SQL. **No acreditan que los SP reales estén instalados ni que MySQL ejecute correctamente sus transacciones.** Consulta `VALIDACION.md` para el resultado de esta sesión.

El diagnóstico local consulta firmas de SP, motores, índice único, control transaccional interno, estado y secuencia sin modificar datos. Requiere tu contraseña y permisos de lectura/ejecución y metadatos. No cambia el esquema si detecta un problema; informa lo que debe revisarse.

## APIs de administración y cobertura de los 21 SP

Las 13 operaciones pendientes ya están implementadas bajo `/admin`: crear/listar/actualizar/eliminar vehículos; crear/actualizar/eliminar comandos y DEMO; agregar/actualizar/eliminar movimientos de DEMO. Se incluyen cinco consultas auxiliares para inspeccionar los recursos. Swagger documenta **22 operaciones HTTP en total**, además del WebSocket.

Consulta [la guía de administración](docs/ADMINISTRACION.md) para las rutas, cuerpos, colección Postman y precauciones de las eliminaciones físicas; [la correspondencia de procedimientos](docs/PROCEDIMIENTOS.md) relaciona los 21 SP con sus endpoints. Todas las operaciones `/admin`, incluidas las lecturas, requieren Bearer Token. La colección original conserva exactamente los tres escenarios de entrega; la colección de administración es auxiliar.

No se permite modificar un vehículo ni su catálogo mientras tenga una DEMO activa. La administración permite consultar y reactivar registros inactivos. Los movimientos HTTP y las ejecuciones DEMO mantienen sus validaciones de actividad originales. Agregar o actualizar un paso exige un comando del mismo vehículo; ejecutar la DEMO vuelve a exigir que esté activo.

Los SP `sp_eliminar_*` ejecutan `DELETE` físico. No se convierten en desactivaciones ni se modifican sus reglas: los efectos sobre registros relacionados dependen de las llaves foráneas de tu MySQL. El diagnóstico ahora verifica las **21 firmas**, los seis motores y muestra las reglas `ON DELETE`/`ON UPDATE` de solo lectura. Las pruebas nuevas automatizadas usan SP simulados y no borran datos reales.


Para Amazon RDS se podrá cambiar la configuración de conexión, pero antes harán falta TLS, permisos de red y revisión del entorno. Esta etapa no crea recursos AWS ni despliega públicamente la API. Versionar el código en GitHub no inicia un servidor.

Referencias técnicas consultadas: [WebSockets en FastAPI](https://fastapi.tiangolo.com/advanced/websockets/), [parámetros de callproc](https://dev.mysql.com/doc/connector-python/en/connector-python-api-mysqlcursor-callproc.html) y [confirmación de transacciones en Connector/Python](https://dev.mysql.com/doc/connector-python/en/connector-python-api-mysqlconnection-commit.html).

Para recuperar el ID de un paso recién agregado, la API consulta LAST_INSERT_ID() en la misma conexión que llamó al SP, conforme a [la documentación de MySQL](https://dev.mysql.com/doc/refman/8.4/en/stored-routines-last-insert-id.html).
