# Excavadora IoT

## Páginas

| Página | Dirección | Función |
| --- | --- | --- |
| Control | `/` en Vercel | Joysticks, teclado personalizable, mando estándar y demos. |
| Monitor | `/monitor.html` en Vercel | Diez movimientos y tramas del ESP8266. |
| Swagger | `/docs` en la API | Operaciones REST y administración del catálogo. |

El panel habilita el teclado y los joysticks al pulsar **Activar control**, incluso si la placa sigue desconectada. El estado de la placa se muestra por separado. La API solicita la sesión de conducción por WebSocket al recibir el primer movimiento. Si la placa aún no está lista, la orden se descarta. Cuando la placa esté lista, pulsa el control de nuevo.

**Recordar código en este dispositivo** guarda el código en el navegador después de iniciar sesión y solo lo reutiliza con la misma dirección de la API. **Salir** borra el código guardado.

El código de acceso dura lo que dura la sesión de la pestaña. En Swagger se ingresa en **Authorize** para las operaciones protegidas. La aplicación instalable usa las mismas entradas y el mismo acceso que Control. En Android/Chrome o Windows/Edge usa **Instalar**. En iPhone/Safari usa **Compartir → Añadir a pantalla de inicio**. El control requiere conexión a la API y a la excavadora.

## Probar y ejecutar el servidor

Se usa Python 3.11 o superior. En Windows ejecuta desde la raíz:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe scripts/generar_token.py
```

En Debian, instala los paquetes `python3` y `python3-venv` y ejecuta:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python scripts/generar_token.py
```

Si ya existe `.env`, actualízalo en lugar de copiar el ejemplo. Configura las variables `MYSQL_*` del RDS, `CONTROL_TOKEN` con el código de ocho caracteres generado y `DEVICE_TOKEN` con una credencial independiente. Puedes generar la del ESP8266 con `python -c "import secrets; print(secrets.token_urlsafe(32))"` usando el Python del entorno. Configura `MYSQL_SSL_CA` con el certificado de RDS cuando corresponda.

Activa el entorno virtual y arranca la API:

```text
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Un solo proceso mantiene sesiones de placa, demos y observadores en la misma memoria. Para una prueba local del navegador, ejecuta en otra terminal:

```text
node control-iot/build.mjs
python -m http.server 4173 --bind 127.0.0.1 --directory control-iot/dist
```

Abre `http://localhost:4173`. Por defecto el frontend local consulta `http://127.0.0.1:8000` y el vehículo ID 1. La API debe incluir `http://localhost:4173` en `BROWSER_ORIGINS`.

Para probar el canal con AWS apagado, instala `requirements-dev.txt` y ejecuta `python -m unittest tests.test_socket_gateway`. La suite usa MySQL y ESP8266 simulados.

## Publicar desde GitHub en Vercel y conectar EC2

### Instalar FastAPI en una EC2 Debian desde Windows

Desde PowerShell, en la raíz del proyecto, ejecuta:

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\deploy_debian.ps1
```

El instalador carga la API por SSH, crea `vehiculo-iot.service` y habilita el arranque automático.
Puedes indicar `-IdentityFile`, `-Server` y `-RdsHost` al ejecutar el instalador. Si omites las direcciones, el instalador las pide.
Para `-IdentityFile`, puedes indicar el archivo `.pem` o la carpeta donde está `ClavesServer1.pem`.
La primera instalación pide la contraseña de RDS en la terminal y permite conservar el `DEVICE_TOKEN` anterior.
Deja la configuración privada en `/etc/vehiculo-iot/api.env` y la conserva al actualizar la API.
Puedes editarla con `sudoedit /etc/vehiculo-iot/api.env` y aplicar cambios con `sudo systemctl restart vehiculo-iot`.

`active`, `enabled` y `Swagger HTTP: 200` confirman el servicio local y su arranque automático.
La lectura del historial también requiere RDS disponible. Para probar Swagger antes de configurar Caddy, abre un túnel desde PowerShell:

```powershell
ssh -i .\ClavesServer1.pem -N -L 8000:127.0.0.1:8000 admin@IP_PUBLICA_EC2
```

Mientras el túnel esté abierto, entra a `http://localhost:8000/docs`.

### Configurar HTTPS y Vercel

1. En EC2, conserva RDS y configura HTTPS para FastAPI. Por ejemplo, apunta un dominio a EC2 y usa Caddy con un `Caddyfile` así. Caddy sirve HTTPS y reenvía WebSocket a Uvicorn.

   ```caddyfile
   api.ejemplo.mx {
       reverse_proxy 127.0.0.1:8000
   }
   ```

   Mantén Uvicorn y Caddy como servicios del sistema. En el grupo de seguridad, permite la entrada TCP 80 y 443 para ese dominio. Uvicorn escucha en loopback. Para Windows o Debian cambia el ejecutable del servicio según las rutas anteriores.
2. Importa este repositorio en Vercel, con la raíz del repositorio como **Root Directory**. El archivo `vercel.json` ya define la compilación. Agrega `IOT_API_URL=https://api.ejemplo.mx` y, si corresponde, `IOT_VEHICLE_ID=1`. Estos valores son públicos. Los tokens y la contraseña de MySQL pertenecen al servidor.
3. En la configuración privada de la EC2 agrega el origen exacto de Vercel. En una instalación manual se usa `.env`. Con el instalador Debian se usa `/etc/vehiculo-iot/api.env`, por ejemplo `BROWSER_ORIGINS='["https://excavadora.vercel.app"]'`. Para autorizar un preview incluye su URL exacta en la lista. Reinicia FastAPI.
4. Para llegar a EC2 desde otra red, ejecuta Caddy en un equipo de la misma red privada que el ESP8266. Cambia la IP del ejemplo por la de ese equipo. El proxy pasa a WSS, conservando la ruta y la credencial del dispositivo. El puerto 8080 solo se usa dentro de esa red.

   ```caddyfile
   http://192.168.1.40:8080 {
       bind 192.168.1.40
       handle /ws/vehiculos/1 {
           reverse_proxy https://api.ejemplo.mx {
               header_up Host api.ejemplo.mx
           }
       }
       respond 404
   }
   ```

   Si usas un túnel temporal de Cloudflare en EC2, usa su dominio `trycloudflare.com` en `reverse_proxy` y `header_up Host`. En la placa, `API_HOST` corresponde a la IP local del equipo que ejecuta Caddy.

   En `firmware/ControlCarroWiFi/config_carro.h` conserva el Wi-Fi y configura `API_HOST=192.168.1.40`, `API_PORT=8080` y el `DEVICE_TOKEN` de la API. El ESP8266 usa WS asíncrono para que la red no bloquee el control serial ni el watchdog. Si Uvicorn y la placa están en la misma red privada, configura en la placa la IP y el puerto de Uvicorn, con el servidor escuchando en esa interfaz.

   Compila con `arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 --library firmware/libraries/WebSockets firmware/ControlCarroWiFi` y sube la revisión a la placa. Consulta la [documentación de `reverse_proxy`](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
5. Abre Monitor y Control. Activa el control y prueba un movimiento breve. En Monitor deben aparecer `orden`, `ack` y el movimiento registrado. Al soltar debe aparecer la parada; una confirmación de la placa describe sus salidas eléctricas.

## Cómo se organiza el código

| Ruta | Responsabilidad |
| --- | --- |
| `control-iot/index.html`, `monitor.html`, `css/styles.css` | Interfaces responsivas y estilos compartidos. |
| `control-iot/js/api.js` | Sesión en la pestaña, peticiones del catálogo y mensajes WebSocket con correlación. |
| `control-iot/js/app.js`, `joystick.js` | Control, puntero táctil, WASD, flechas, reasignación de teclas y Gamepad API. Usa el controlador existente `app/panel/drive-controller.js`. |
| `control-iot/js/monitor.js` | Tabla de diez movimientos y búfer de tramas en vivo. |
| `control-iot/build.mjs`, `manifest.webmanifest`, `sw.js` | Compilación, instalación y caché de la interfaz. |
| `app/websocket/gateway.py` | Identifica el rol, valida las solicitudes, mantiene control y demo por conexión y publica tramas observables. |
| `app/websocket/manager.py` | Sala por vehículo y cola FIFO para cada observador o controlador. |
| `app/services`, `app/repositories` | Arbitraje del control, watchdog, demos, catálogo e historial MySQL mediante los procedimientos existentes. |
| `firmware/ControlCarroWiFi` | Cliente Wi-Fi/serial, confirmaciones, liberación de salidas y protocolo físico. |

El catálogo de comandos y las demos viven en RDS. La compilación reutiliza las asignaciones del panel anterior. Los joysticks y el mando seleccionan un código activo por vez. WASD mueve el vehículo, las flechas controlan la pala y Espacio detiene el control. El giro derecho de la pala usa un pulso de 200 ms por toque. Los botones Y, A y X corresponden a luz, velocidad y mute en el mapeo estándar Xbox. Start enciende, el gatillo izquierdo apaga, B ejecuta la demo seleccionada y Back detiene.

## WebSocket

Todos los participantes usan `/ws/vehiculos/{id}`. Un WebSocket por cliente es necesario para que la placa y los navegadores tengan su propia conexión al mismo canal del vehículo.

| Subprotocolo | Autenticación | Mensajes |
| --- | --- | --- |
| `iot-device` | `Authorization: Bearer DEVICE_TOKEN` | Saludo, preparación, orden, latido y ACK del ESP8266. |
| `iot-control` | Subprotocolo adicional `token.<base64url>` y origen permitido | `activar`, `orden`, `latido`, `liberar`, `estado`, `demo_iniciar`, `demo_latido` y `demo_cancelar`. |
| `iot-monitor` | Igual que el control | Estado, historial inicial, eventos y tramas del ESP8266 con campos de diagnóstico. |

Ejemplo de una orden cuando se activó el control:

```json
{"id": 7, "accion": "orden", "datos": {"codigo": 2, "intencion": 4}}
```

La API responde con `tipo: "respuesta"`, el mismo `id`, `ok` y `datos` o `error`.
`codigo: 0` libera salidas. El botón de apagado usa `codigo: 9` con `pulso_ms: 2000`.
`demo_iniciar` recibe el `id_demo` de RDS. El monitor recibe los pasos de demo mientras la conexión está abierta. Al reconectar, se carga el historial persistido por MySQL. La opción de latidos permite ver también los reportes periódicos del dispositivo.

Los accesos antiguos `/panel/`, `/panel/ws/vehiculos/{id}` y `/dispositivo/ws/vehiculos/{id}` se conservan para la app de escritorio y firmware anteriores. Los dos accesos WebSocket antiguos usan el mismo gateway y también alimentan el monitor nuevo.

## Integración de IA

`control-iot/js/assist.js` define las entradas para ambos proveedores.

- **Voz.** Capturar una frase en español y enviarla al backend que alojará el modelo. El modelo devuelve `{"pasos":[{"codigo":1,"duracion_ms":400,"pausa_ms":200}]}`. Pasar el resultado por `validateVoicePlan` también en el punto de ejecución. Para «saluda» el proveedor puede proponer alternar la pala de lado a lado. Para «baila» puede combinar movimientos cortos y pausas. Mostrar el plan y, tras confirmarlo, ejecutarlo a través del servicio de demos o del controlador vigente. Cancelar al parar, perder la sesión u ocultar la página. El modelo se limita a proponer datos y la clave del proveedor vive en el backend.
- **Gestos.** Inyectar a `CameraGestureInput` un detector `detect(video)` que retorne `{abierta, x, y}` con coordenadas normalizadas según el video que ve el usuario. Centrar la palma abierta y moverla a un borde. Arriba avanza, abajo retrocede y los lados giran. Volver al centro, cerrar la mano o perder el seguimiento libera la orden. Conecta `press` y `release` al controlador existente. Activa la cámara por acción explícita del usuario y llama a `stop()` al salir del modo o detener el vehículo.

Quedan por conectar el modelo de lenguaje, la captura de voz, el detector de manos y sus controles visibles.
