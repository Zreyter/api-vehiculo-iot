# API de vehículo IoT — versión 1.6.4

## Pulsaciones rápidas y conducción: 1.6.4

Actualiza **la API de EC2 y el exe a 1.6.4**. El servidor comprueba la capacidad de registro antes de activar, conserva la sesión si RDS está ocupado y descarta solicitudes anteriores a una liberación. El cliente exige una nueva pulsación tras el aviso de guardado; el firmware actual sigue siendo compatible. Consulta la [guía y pruebas de pulsaciones rápidas](docs/TECLAS-RAPIDAS.md).

[Descargar exe 1.6.4 para Windows x64](https://github.com/Zreyter/api-vehiculo-iot/releases/download/v1.6.4/Vehiculo-IoT-1.6.4-Windows-x64.exe) · [Descargar actualización de EC2 1.6.4](https://github.com/Zreyter/api-vehiculo-iot/releases/download/v1.6.4/Actualizacion-teclas-1.6.4.zip) · [Release v1.6.4](https://github.com/Zreyter/api-vehiculo-iot/releases/tag/v1.6.4).

## Antecedente: conexión y mando 1.6.3

El exe 1.6.3 reserva conexiones para renovar el control, recupera de forma limitada las lecturas/renovaciones sobre sockets reutilizados cerrados y estabiliza las entradas analógicas. Es compatible con la API 1.6.2 de EC2; el paquete de EC2 1.6.3 aplica también las mejoras del panel web. Consulta la [guía y validación](docs/CONEXION-MANDO.md). La release publicada v1.6.2 conserva sus archivos originales.

## Corrección de estabilidad 1.6.2

Corrige cancelaciones de sesión causadas por permisos anticipados tardíos y confirmaciones de liberación. Se actualiza la carpeta `app` de EC2; el exe 1.6.1 y el firmware actual siguen siendo compatibles. Incluye pruebas con red inestable y parada prioritaria; consulta la [guía de actualización y validación](docs/ESTABILIDAD.md).

[Descargar actualización EC2 1.6.2](https://github.com/Zreyter/api-vehiculo-iot/releases/download/v1.6.2/Actualizacion-estabilidad-1.6.2.zip) · [Descargar exe compatible 1.6.1](https://github.com/Zreyter/api-vehiculo-iot/releases/download/v1.6.2/Vehiculo-IoT-1.6.1-Windows-x64.exe) · [Release v1.6.2](https://github.com/Zreyter/api-vehiculo-iot/releases/tag/v1.6.2).

API desarrollada con **FastAPI, MySQL y WebSocket** para administrar un vehículo IoT, registrar movimientos individuales y transmitir secuencias DEMO. El proyecto corresponde a la actividad **2.5: APIs para IoT en entorno Dev** e integra **21 procedimientos almacenados**; conserva las **22 operaciones HTTP** anteriores y añade **cinco operaciones HTTP** para el control del ESP8266, además de los canales WebSocket de eventos y dispositivo.

**Versión 1.6:** añade una aplicación portátil para Windows con la misma interfaz, teclado/mando, configuración del servidor y controles persistentes. Conserva el firmware ESP8266 WiFi/serial y su canal autenticado. La versión actual de OpenAPI es `1.6.4`. Consulta el [registro de validación](VALIDACION.md).

**Antecedente v1.4: funcionamiento en AWS demostrado y confirmado por el estudiante al cierre de esta entrega, el 21 de octubre de 2026.** La API se ejecuta en Amazon EC2 con Windows Server y utiliza MySQL en Amazon RDS. El repositorio incluye el panel web integrado, las colecciones de Postman y las guías de despliegue y operación. Esta confirmación corresponde a la aplicación y su conexión a la base de datos. Posteriormente, el usuario confirmó en este chat el funcionamiento del ESP8266 con el carro real.

## Revisión de latencia 1.6.1

La revisión prepara sesiones y permisos antes de las pulsaciones, prioriza la liberación y reutiliza las conexiones del escritorio. Requiere actualizar la carpeta `app` de EC2 y usar el exe 1.6.1; no requiere volver a cargar el ESP8266. Consulta la [guía y medición de latencia](docs/LATENCIA.md).

## Panel web en la misma instancia

El panel integrado está disponible en `/panel/` al ejecutar esta versión de la API. Usa el mismo `CONTROL_TOKEN` que Postman y permite administración, movimientos, DEMO, historial y eventos. Se sirve desde FastAPI en el mismo puerto, sin instalar dependencias adicionales.

- **Panel local:** [http://localhost:8000/panel/](http://localhost:8000/panel/).
- **Panel en EC2:** `http://<IP_PUBLICA_EC2>:8000/panel/`; usa la dirección vigente de la instancia.
- **Conexión:** pulsa **Conectar API**, introduce el token de EC2 y selecciona el vehículo.

El navegador utiliza las rutas HTTP existentes y el canal autenticado `/panel/ws/vehiculos/{id_vehiculo}` para recibir los mismos eventos que Postman. Consulta [cómo actualizar EC2 Windows y abrir el panel](docs/PANEL_AWS.md).

## Nueva sección: Conducción

El panel incorpora los 13 comandos del control serial original, movimientos mantenidos y pulsaciones, asignaciones de teclado guardadas en el navegador y soporte para mando Xbox mediante Gamepad API. Conserva la paleta del panel y relaciona cada acción por su código real. Permite control del ESP8266 por WiFi o registro de software mediante las rutas anteriores. Consulta la [guía de Conducción](docs/CONDUCCION.md) para personalizar controles y conocer el requisito HTTPS del mando remoto; solo el modo de registro requiere preparar el comando 0 en MySQL.

La integración WiFi se validó automáticamente con MySQL y dispositivo simulados. El usuario confirmó después su funcionamiento con el carro real mediante EC2. El canal del dispositivo confirma salidas aplicadas por el firmware; no mide movimiento mecánico mediante sensores.

## ESP8266: WiFi y serial

El proyecto incluye el [firmware ESP8266 WiFi/serial](firmware/ControlCarroWiFi/ControlCarroWiFi.ino), el canal autenticado de dispositivo y la adaptación de Conducción. Conserva los pines originales, 9600 baudios y comandos 0–13; añade prioridad serial, permisos de activación efímeros y watchdog local.

Sigue la [guía de configuración, actualización de EC2 y carga del firmware](docs/ESP8266_WIFI_SERIAL.md). El asistente `python scripts/configurar_esp8266.py` genera la configuración privada sin modificar `.env`. La liberación WiFi no requiere agregar el código 0 en MySQL. La API y el navegador se validaron con dispositivos/MySQL simulados y el sketch compiló para NodeMCU/ESP8266; la prueba manual de la placa y el carro fue confirmada posteriormente por el usuario.

## Aplicación para Windows

**[Descargar Vehículo IoT 1.6 para Windows x64](https://github.com/Zreyter/api-vehiculo-iot/releases/download/v1.6/Vehiculo-IoT-1.6.0-Windows-x64.exe)** · [Release, instrucciones y SHA256](https://github.com/Zreyter/api-vehiculo-iot/releases/tag/v1.6)


La carpeta [`desktop`](desktop/README.md) contiene la aplicación portátil de Windows x64 con la misma interfaz: Conducción, teclado/mando, administración, historial y eventos. Se conecta a la API de EC2 y solicita el mismo `CONTROL_TOKEN`. La dirección del servidor es editable; las preferencias de control se conservan en el equipo.

El ejecutable incluye su runtime y no necesita Python, Node.js ni Arduino IDE para abrirse. Para construirlo desde las fuentes utiliza `npm ci`, `npm test` y `npm run dist` dentro de `desktop`. Las credenciales y archivos privados quedan fuera del paquete.

## Alcance y etapas

| Etapa | Qué se realiza | Estado documentado |
| --- | --- | --- |
| Desarrollo local | Implementar las APIs y conectarlas a MySQL local | Implementado |
| Validación local | Comprobar movimientos, historial, DEMO y administración con la base real | Pruebas locales completas, según confirmación del estudiante del 16 de octubre de 2026 |
| Entrega en AWS | Ejecutar estas mismas APIs en EC2 y usar RDS como base de datos | Funcionamiento demostrado y confirmado por el estudiante para v1.4 |

La API permite:

- Crear, consultar, actualizar y eliminar vehículos, comandos y definiciones DEMO.
- Agregar, consultar, actualizar y eliminar pasos de una DEMO.
- Registrar un movimiento individual, actualizando estado e historial en una transacción.
- Consultar un máximo de diez registros recientes del historial.
- Iniciar o cancelar una DEMO y transmitir sus eventos a varios clientes WebSocket.

Los eventos de las rutas anteriores representan operaciones de software y cambios confirmados en la base de datos. El nuevo canal del dispositivo distingue la confirmación de salidas de la confirmación de registro en RDS. **Todavía no confirman que el ESP8266 o el vehículo hayan ejecutado un movimiento físico.**

### Versiones del repositorio

| Etiqueta Git | Alcance |
| --- | --- |
| `v1.1` | Movimiento individual, historial y WebSocket DEMO con inicio/cancelación |
| `v1.2` | Integración de los 21 SP y operaciones de administración |
| `v1.3` | Preparación para EC2 Windows y conexión TLS con RDS |
| `v1.4` | Funcionamiento en AWS confirmado e incorporación del panel web integrado con autenticación y eventos en tiempo real |
| `v1.5` | Conducción con teclado/mando, firmware ESP8266 WiFi/serial, prioridad serial, watchdog y confirmación de salidas |
| `v1.6` | Aplicación portátil Windows x64 con las funciones del panel, controles persistentes y ejecutable descargable en GitHub Releases |

## Requisitos para ejecutar localmente

- Python 3.12 o 3.13 y un entorno virtual creado en la computadora donde se ejecutará la API.
- MySQL local con el esquema `vehiculo_iot`, sus seis tablas y los 21 SP instalados.
- Un usuario MySQL con los permisos de lectura y ejecución necesarios, además de permisos sobre los datos que modifican los SP.
- Postman de escritorio u otro cliente HTTP/WebSocket para las pruebas.

Las tablas esperadas son `vehiculos`, `comandos`, `estado_vehiculo`, `historial_comandos`, `demos` y `demo_movimientos`. Las escrituras requieren un motor transaccional como InnoDB. El estado requiere una clave única por `id_vehiculo` para el upsert existente.

**La aplicación no crea automáticamente la base, las tablas ni los SP.** Deben prepararse o importarse previamente. Los CSV de `docs/` documentan las firmas y definiciones exportadas de MySQL; no son un script de instalación del esquema completo.

## Instalación y configuración local

### 1. Obtener el proyecto e instalar dependencias

Desde una terminal de Linux:

```bash
git clone https://github.com/Zreyter/api-vehiculo-iot.git
cd api-vehiculo-iot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Si el proyecto y su entorno ya existen, abre la carpeta y activa `.venv`; no es necesario volver a clonarlos. En VS Code selecciona `.venv/bin/python` mediante **Python: Select Interpreter**. Los entornos virtuales no se comparten por Git y deben instalarse en cada computadora o instancia.

### 2. Crear la configuración privada

Solo para una instalación nueva, cuando todavía no exista `.env`:

```bash
cp .env.example .env
chmod 600 .env
python -c "import secrets; from dotenv import set_key; set_key('.env', 'CONTROL_TOKEN', secrets.token_urlsafe(32))"
python scripts/configurar_password.py
```

El último comando solicita la contraseña MySQL sin mostrarla en pantalla. Si `.env` ya está configurado, conserva sus valores y omite estos pasos.

| Variable | Uso | Valor local de referencia |
| --- | --- | --- |
| `MYSQL_HOST` | Servidor de base de datos | `127.0.0.1` |
| `MYSQL_PORT` | Puerto de MySQL | `3306` |
| `MYSQL_USER` | Usuario de la base | Usuario configurado en MySQL; la plantilla usa `admin` |
| `MYSQL_PASSWORD` | Contraseña de ese usuario | Configurar personalmente |
| `MYSQL_DATABASE` | Nombre del esquema | `vehiculo_iot` |
| `MYSQL_SSL_CA` | Ruta al certificado CA para verificar TLS e identidad del servidor MySQL | Vacío en local; certificado oficial de AWS en RDS |
| `CONTROL_TOKEN` | Clave de acceso a los controles de la API | Valor aleatorio generado localmente |
| `DEVICE_TOKEN` | Token opcional exclusivo del ESP8266 | Vacío utiliza `CONTROL_TOKEN` |

`.env` contiene la configuración real y está excluido de Git. `.env.example` es la plantilla sin secretos que se incluye en el repositorio. No compartas contraseñas o tokens en capturas ni exportaciones de Postman. Reinicia la API si cambias la configuración.

### 3. Comprobar la base e iniciar la API

Desde la raíz del proyecto, con el entorno activado:

```bash
python scripts/diagnosticar_mysql.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

El diagnóstico es de solo lectura: comprueba las 21 firmas y sus tipos, motores de tablas, clave única del estado, control transaccional interno y reglas de llaves foráneas. También consulta el vehículo y la DEMO de referencia con ID 1; adapta esos datos de referencia si usas otra base de laboratorio. No modifica el esquema ni los registros.

Mantén abierta la terminal del servidor. La documentación interactiva está en **[http://localhost:8000/docs](http://localhost:8000/docs)** y el contrato OpenAPI en [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json). Detén el servidor con **Ctrl+C**.

Usa **un solo proceso** de la API: la coordinación de DEMO y las salas WebSocket están en memoria. Durante desarrollo puede añadirse `--reload`, pero cada recarga interrumpe las conexiones y ejecuciones en curso. La configuración local anterior escucha únicamente en la computadora de desarrollo.

## Autenticación

El token de control y la contraseña MySQL tienen funciones diferentes: el token autentica al cliente de la API; la contraseña permite a la aplicación conectarse a la base.

Requieren token los controles de movimiento/DEMO, el WebSocket y **todas las rutas `/admin`, incluidas las consultas**. El GET de historial local no exige token.

- **Swagger:** pulsa **Authorize** e introduce solamente el valor de `CONTROL_TOKEN`.
- **Postman HTTP:** en **Authorization → Bearer Token**, introduce solamente el token.
- **Postman WebSocket:** en **Headers**, agrega `Authorization` con el valor completo `Bearer TU_TOKEN`, dejando un espacio después de `Bearer`.

Si no está configurada la contraseña, las operaciones que necesitan MySQL responden `503`; Swagger puede seguir disponible. Si el token de la API está vacío, los controles también responden `503`.

## Operaciones de movimiento, historial y ejecución DEMO

Los IDs de la tabla son ejemplos del laboratorio. Consulta los catálogos administrativos para conocer los IDs reales de tu base.

| Método | Ruta de ejemplo | Cuerpo / consulta | Resultado esperado |
| --- | --- | --- | --- |
| POST | `/vehiculos/1/movimientos` | `{"id_comando":2,"origen":"Postman"}` | `200`, estado e historial confirmados y evento de movimiento |
| GET | `/vehiculos/1/historial?limite=10` | `limite` entre 1 y 10 | `200`, hasta diez registros recientes |
| POST | `/vehiculos/1/demos` | `{"id_demo":1}` | `202`, ejecución DEMO iniciada |
| DELETE | `/vehiculos/1/demos/activa` | Sin cuerpo | `200`, cancelación terminada |

El movimiento individual valida vehículo y comando activos y relacionados. Actualiza estado e historial en la misma transacción y confirma antes de publicar el evento. El código del comando se toma de MySQL; no se deduce de su ID.

La DEMO lee su secuencia de MySQL en cada inicio, respeta orden, duración y pausa mediante esperas asíncronas, y actualiza estado **sin registrar historial**. Solo puede existir una ejecución por vehículo. Mientras está activa, se rechazan los movimientos individuales y las modificaciones administrativas de ese vehículo con `409`.

`conectado` conserva su valor existente; si no había estado, se inicializa en 0. Una petición HTTP o una conexión WebSocket no demuestra conexión del microcontrolador.

## Administración de catálogos

El prefijo `/admin` distingue la configuración del catálogo de la ejecución del vehículo. Por ejemplo, **crear una DEMO** en `/admin/vehiculos/1/demos` guarda su definición; **ejecutarla** utiliza `/vehiculos/1/demos`.

| Recurso | Rutas administrativas | Operaciones disponibles |
| --- | --- | --- |
| Vehículos | `/admin/vehiculos`, `/admin/vehiculos/{id_vehiculo}` | Crear, listar, consultar, actualizar y eliminar |
| Estado | `/admin/vehiculos/{id_vehiculo}/estado` | Consultar; puede devolver `null` si aún no existe |
| Comandos | `/admin/vehiculos/{id_vehiculo}/comandos` y `/{id_comando}` | Crear, listar, actualizar y eliminar |
| DEMO | `/admin/vehiculos/{id_vehiculo}/demos` y `/{id_demo}` | Crear, listar, actualizar y eliminar |
| Pasos de DEMO | `/admin/vehiculos/{id_vehiculo}/demos/{id_demo}/movimientos` y `/{id_demo_movimiento}` | Agregar, listar, actualizar y eliminar |

Las altas responden `201`, las consultas/actualizaciones `200` y las eliminaciones `204` sin cuerpo. La administración permite consultar y reactivar recursos inactivos. Valida pertenencia al vehículo/DEMO, códigos únicos por vehículo, orden único por DEMO y tiempos no negativos.

**Los DELETE eliminan físicamente.** Para desactivar un vehículo, comando o DEMO, utiliza su PUT con `activo=0`. Las posibles cascadas o restricciones de eliminación son las de la base MySQL existente; consúltalas con el diagnóstico antes de borrar registros.

Los cuerpos JSON, rutas completas y reglas están en [la guía de administración](docs/ADMINISTRACION.md). La [correspondencia de procedimientos](docs/PROCEDIMIENTOS.md) documenta cómo se integran los 21 SP.

## WebSocket: eventos en tiempo real

En Postman selecciona **New → WebSocket** y utiliza:

```text
ws://localhost:8000/ws/vehiculos/1
```

Antes de conectar, configura el encabezado:

```text
Authorization: Bearer TU_TOKEN
```

Reemplaza `TU_TOKEN` por el valor local y pulsa **Connect**. El primer evento es `estado`, con el último estado de MySQL. Puedes conectar dos o más pestañas al mismo vehículo: reciben los mismos eventos de esa sala y no los de otros vehículos.

**Las órdenes se envían por HTTP en otra pestaña.** Este WebSocket recibe eventos automáticamente; no ejecuta mensajes enviados con el botón Send.

| Evento | Significado |
| --- | --- |
| `estado` | Último estado al conectar |
| `movimiento_individual` | Estado e historial del movimiento confirmados |
| `demo_iniciada` | Secuencia validada y tarea creada |
| `demo_movimiento` | Estado del paso confirmado en la base |
| `demo_finalizada` | Secuencia y sus esperas terminadas |
| `demo_cancelada` | Cancelación terminada; no habrá más pasos de esa ejecución |
| `error` | Fallo al procesar una operación o la DEMO |

Todos incluyen `tipo`, `id_vehiculo`, `id_comando`, `comando`, `codigo`, `marca_temporal`, `estado`, `mensaje` y `ejecucion_fisica_confirmada=false`. Para DEMO también se incluyen `id_demo`, `orden`, `duracion_ms` y `pausa_ms`. Los campos que todavía no correspondan o no se conozcan pueden ser `null`. La marca temporal de emisión es UTC; las fechas devueltas por MySQL conservan su información original.

Cancelar interrumpe las esperas. Si un paso ya está procesándose en MySQL, se espera su conclusión y se suprime su evento de movimiento; ese paso puede quedar confirmado en el estado, pero no se inician pasos posteriores. Los eventos ya enviados pueden recibirse antes del terminal. **Cancelar la secuencia no envía un comando físico de parada.**

Las desconexiones se retiran de la sala. Cada cliente tiene una cola de 64 eventos y un límite de dos segundos por envío; un cliente que no pueda recibirlos se desconecta y debe reconectar para recuperar el estado actual. Un rechazo durante el handshake puede aparecer en Postman como HTTP `403`: revisa autorización, existencia/actividad del vehículo y disponibilidad de MySQL.

## Comprobación de funcionamiento

### Pruebas automatizadas

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -v
node --test tests/test_driving.js tests/test_remote_drive.js
```

La verificación de v1.5 aprobó **80 pruebas Python y 15 pruebas JavaScript**, con repositorios/SP y dispositivos simulados. Incluye los controles anteriores, autenticación, sesiones exclusivas, prioridad serial, confirmación de salidas, registro diferido y lógica de conducción. El firmware compiló para NodeMCU con ESP8266 Core 3.1.2. Estas pruebas **no se conectan a AWS ni a MySQL real**. La validación anterior del funcionamiento en EC2 con RDS fue demostrada por el estudiante; la integración física de v1.5 sigue pendiente. Consulta [VALIDACION.md](VALIDACION.md) para el alcance y los resultados.

### Pruebas manuales con Postman

Las dos colecciones están en `postman/`. Importa la que corresponda y configura su variable `control_token` como valor local. Para pruebas locales configura `base_url` como `http://localhost:8000`; para repetirlas en AWS utiliza `http://<IP_PUBLICA_EC2>:8000` y el token de esa instancia. Los WebSocket se crean manualmente, usando el mismo servidor y puerto que la API.

**Control y transmisión — `actividad_2_5.postman_collection.json`:**

1. Conecta dos clientes WebSocket al mismo vehículo. Envía el POST individual y verifica `200`, el evento en ambos clientes y conservación de `conectado`.
2. Consulta el historial y verifica el nuevo registro y el máximo de diez elementos.
3. Ejecuta **3.1 Historial antes**, inicia DEMO con **3.2**, espera `demo_finalizada` en ambos clientes y ejecuta **3.3 Historial después**. La prueba de historial idéntico debe aprobarse. En otra ejecución prueba **3.4 Cancelar DEMO** y ausencia de pasos posteriores.

No ejecutes toda la carpeta DEMO automáticamente: el GET posterior debe esperar al evento final. Con los datos originales del laboratorio, DEMO 1 tiene ocho pasos y aproximadamente 11.4 segundos de duración y pausas, más el tiempo de MySQL; la API siempre lee la secuencia vigente.

**Administración — `administracion_2_5.postman_collection.json`:**

1. Carpeta A: crear vehículo, comando, DEMO y paso de prueba.
2. Carpeta B: consultar los catálogos y comprobar sus IDs.
3. Carpeta C: actualizar y verificar los cambios.
4. Carpeta D: eliminar los registros creados, en orden paso → DEMO → comando → vehículo.

La colección administrativa captura IDs de registros nuevos `LAB_API_2_5`; sus variables empiezan vacías. Usa esos registros para comprobar CRUD y conserva los datos del vehículo real. Revisa la [guía administrativa](docs/ADMINISTRACION.md) antes de ejecutar la limpieza.

Los tres escenarios de control documentan la validación inicial; las comprobaciones CRUD completan la revisión del conjunto de APIs. **La entrega v1.4 registra que estas mismas APIs integradas ya demostraron su funcionamiento en AWS con RDS.** La guía académica menciona Thunder Client; la aceptación de evidencias hechas con Postman debe confirmarse con el profesor.

## Despliegue validado: las mismas APIs en EC2 con RDS

La API ya se ejecutó y demostró su funcionamiento en la instancia Windows Server con RDS, según la confirmación del estudiante para esta versión. Para reproducir la instalación, consulta la [guía de despliegue en Windows](docs/AWS_WINDOWS.md); para incorporar el panel a una instancia existente, utiliza la [guía del panel en AWS](docs/PANEL_AWS.md).

Arquitectura de la entrega:

```text
Panel web / Postman / cliente
       │ HTTP y WebSocket (HTTPS/WSS al configurar TLS)
       ▼
Mismas APIs FastAPI en la instancia EC2
       │ conexión MySQL
       ▼
Amazon RDS MySQL — esquema vehiculo_iot y 21 SP
```

La migración conserva los endpoints, modelos, servicios y procedimientos. Cambia el lugar donde se ejecuta la aplicación y la configuración de conexión a la base. La confirmación de AWS se registra como resultado de la demostración del estudiante; las pruebas automatizadas locales se documentan por separado.

Pasos para reproducir el despliegue y comprobar futuras actualizaciones:

1. Conservar las evidencias de las pruebas locales de control y CRUD ya completadas.
2. Preparar en RDS el esquema, las seis tablas, relaciones y los 21 SP compatibles con la base validada; revisar el script de importación y los permisos del usuario de aplicación.
3. Copiar o clonar esta versión del proyecto en la instancia EC2, instalar Python y crear allí su propio entorno virtual y sus dependencias.
4. Configurar la conectividad de EC2 a RDS. Para este escenario se usará la misma VPC y una regla de MySQL en el puerto configurado —normalmente 3306— cuyo origen sea el grupo de seguridad de EC2. Véase [la guía de conexión EC2–RDS de AWS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/tutorial-connect-ec2-instance-to-rds-database.html).
5. Crear la configuración privada de la instancia con `MYSQL_HOST` apuntando al **endpoint de RDS**, y definir allí puerto, esquema, usuario, contraseña y token. `127.0.0.1` seguiría apuntando a la propia instancia, no a RDS.
6. Descargar en EC2 el [certificado CA oficial de RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html) y configurar `MYSQL_SSL_CA` con su ruta. El adaptador exige verificación del certificado y de la identidad del servidor cuando se configura esa variable; usar el endpoint DNS de RDS como `MYSQL_HOST`. Las rutas relativas del certificado se resuelven desde la raíz del proyecto. Un archivo inexistente o una verificación fallida impiden la conexión; no se reintenta sin verificación. Dejar esta variable vacía conserva la configuración del laboratorio local. La conexión TLS real a RDS debe comprobarse desde EC2. Referencia: [seguridad de conexiones MySQL en RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/securing-mysql-connections.html).
7. Configurar la ejecución persistente de la API según el sistema operativo de la instancia, su punto de acceso HTTP/WebSocket y HTTPS/WSS. Mantener un solo proceso mientras la coordinación siga en memoria. Revisar el acceso al historial, que actualmente es una lectura local sin token, antes de publicar el servicio.
8. Repetir los escenarios de control y CRUD desde el cliente contra la API de EC2, comprobando que los datos se leen/escriben en RDS y que DEMO no modifica el historial.

El cliente se conecta a **la API de EC2**; la API se conecta a **RDS**. Subir el repositorio a GitHub conserva el código, pero no despliega ni arranca el servidor por sí solo.

## Organización del proyecto

```text
app/
  core/          Configuración, conexión MySQL, autenticación y errores
  models/        Modelos y validaciones Pydantic
  repositories/  Ejecución de SP y acceso a los datos
  services/      Reglas de negocio y coordinación de DEMO
  api/           Endpoints HTTP y WebSocket, incluidas las rutas del panel
  panel/         Interfaz web integrada: HTML, CSS y JavaScript
  websocket/     Salas de clientes y envío de eventos
  main.py        Creación y ciclo de vida de la aplicación
scripts/         Configuración de contraseña y diagnóstico de solo lectura
postman/         Colecciones de control y administración
tests/           Pruebas automatizadas con SP simulados
docs/            Guías de administración, AWS, panel y contratos de los SP
handwrittennotes/ Referencias y carpeta para evidencias de apuntes manuscritos
```

La separación por clases mantiene configuración/conexión, repositorios, servicios, modelos y endpoints independientes. MySQL se ejecuta en hilos para no bloquear el bucle asíncrono. Cada unidad de trabajo libera su conexión y cursores; los valores SQL se enlazan, no se concatenan.

## Respuestas y límites importantes

| Resultado | Interpretación |
| --- | --- |
| `401` | Token HTTP ausente o incorrecto |
| `403` en WebSocket | Handshake rechazado: revisar encabezado y disponibilidad del vehículo/base |
| `404` | Recurso inexistente o ajeno al vehículo/DEMO indicado |
| `409` | DEMO activa, recurso inactivo, código/orden duplicado o conflicto de integridad/transacción |
| `422` | Petición, límites o referencias inválidos |
| `503` | Configuración o MySQL no disponible, o contrato de SP incompatible |

Si falla una escritura se intenta rollback y no se publica éxito. Una pérdida de conexión durante COMMIT puede dejar un resultado incierto: consulta el recurso antes de repetir una creación o un movimiento. No hay reintentos automáticos de escritura.

El SP de historial devuelve actualmente todos los registros ordenados; la API limita su respuesta a diez. Optimizar la lectura en MySQL requeriría una revisión posterior del SP. La coordinación entre varios procesos y la confirmación física del ESP8266 quedan fuera de la implementación actual.
