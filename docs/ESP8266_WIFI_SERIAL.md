# ESP8266 por WiFi y por puerto serial

El firmware `firmware/ControlCarroWiFi/ControlCarroWiFi.ino` conserva los comandos **0–13**, los **9600 baudios** y los seis GPIO de los dos registros 74HC595 del programa original. Añade un cliente WebSocket asíncrono hacia EC2 y un watchdog local. No se conecta directamente a RDS ni contiene credenciales MySQL.

El recorrido remoto es: **Conducción → API de EC2 → WebSocket del ESP8266 → 74HC595**. La placa confirma qué salidas aplicó; esto no constituye una medición de movimiento o encendido físico del carro.

## Estado vigente — 27 de octubre de 2026

EC2 y la ESP8266 ya están actualizados. El usuario probó nuevas demos creadas en la página con la excavadora real y confirmó que funcionan correctamente; observó una respuesta más rápida, sin medición de latencia física. Consulta [DEMOS-FISICAS.md](DEMOS-FISICAS.md) y [ENLACE-ESTABLE.md](ENLACE-ESTABLE.md).

El firmware actual requiere la copia corregida de WebSockets en `firmware/libraries/WebSockets`, con reintentos asíncronos de uno en uno. Selecciónala explícitamente desde la raíz del proyecto:

```powershell
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 --library firmware/libraries/WebSockets firmware/ControlCarroWiFi
```

En Arduino IDE, instala esa copia local en la carpeta de bibliotecas y verifica que la compilación use su ruta, en lugar de otra copia global. Conserva `config_carro.h` privado y `ControlCarroWiFi.ino.globals.h`. Los comandos seriales `ENCENDER` y `APAGAR` envían 200 y 2000 ms por la salida 9, sin estimar el estado físico.

Las instrucciones siguientes se conservan para futuras instalaciones. Las referencias a la preparación sin carga de hardware describen el estado histórico anterior.

## 1. Actualizar EC2 antes de cargar el firmware

Copia la carpeta **`app` completa de esta versión** a la carpeta del proyecto en EC2 y reinicia la API. El panel anterior, por sí solo, no contiene el canal del dispositivo.

Conserva `.env`, `certs` y `.venv`. Las dependencias Python no cambiaron. Continúa usando un solo proceso:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

El dispositivo se conecta a `/dispositivo/ws/vehiculos/1` en el mismo puerto de la API, sustituyendo 1 por el ID configurado. Necesita salida a Internet y acceso a ese puerto de EC2. No abras el puerto 3306 para el ESP8266.

Por compatibilidad, el dispositivo utiliza `CONTROL_TOKEN` cuando la API no tiene `DEVICE_TOKEN`. Opcionalmente puedes añadir un `DEVICE_TOKEN` separado a `.env` en EC2 y usar ese mismo valor en el firmware; el navegador seguirá usando `CONTROL_TOKEN`. Reinicia la API tras cambiar variables.

Esta versión del transporte asíncrono utiliza **`ws://`**, adecuado para el entorno de laboratorio HTTP actual: autentica el canal pero no cifra el token ni los mensajes. El HTTPS requerido por el mando en el navegador es una configuración aparte; no habilita automáticamente WSS en la placa. Este firmware no usa `setInsecure` ni presenta WS como una conexión cifrada.

## 2. Preparar la configuración privada en PC-ORION

Conecta el ESP8266 por USB. Desde PowerShell, en la raíz de `api-vehiculo-iot-rds`:

```powershell
python scripts/configurar_esp8266.py
```

El asistente solicita SSID, contraseña WiFi sin mostrarla, host de EC2, puerto e ID de vehículo. Si existe el token en el `.env` de esta copia, lo toma sin imprimirlo; de lo contrario lo solicita sin mostrarlo. **No modifica `.env`.**

Genera `firmware/ControlCarroWiFi/config_carro.h`, excluido de Git. Si ya existe, edítalo directamente. También puedes copiar `config_carro.example.h` con ese nombre y rellenarlo. No compartas `config_carro.h`: contiene la contraseña WiFi y el token.

La red debe ser de **2.4 GHz**. `API_HOST` lleva solo la IP o nombre del servidor, sin `http://`, puerto ni ruta. Si EC2 usa una IP pública que cambia al reiniciar, actualiza ese valor o usa su dirección estable.

## 3. Compilar y cargar con Arduino IDE

En el gestor de placas instala **esp8266 by ESP8266 Community 3.1.2** si todavía no lo tienes. En el gestor de bibliotecas instala:

| Biblioteca | Versión usada en la compilación verificada |
| --- | --- |
| WebSockets, Markus Sattler / Links2004 | 2.7.2 |
| ESPAsyncTCP, dvarrel | 1.2.4 |
| ArduinoJson, Benoit Blanchon | 7.4.3 |

1. Abre `firmware/ControlCarroWiFi/ControlCarroWiFi.ino`.
2. Conserva en la misma carpeta `ControlCore.h`, `config_carro.h` y **`ControlCarroWiFi.ino.globals.h`**. Este último activa el transporte asíncrono también en las bibliotecas; no basta con copiar solo el texto del `.ino`.
3. Selecciona tu placa ESP8266 y el puerto COM. La compilación se verificó con **NodeMCU 1.0 (ESP-12E Module)**, FQBN `esp8266:esp8266:nodemcuv2`.
4. Pulsa **Verificar** y luego **Subir**. Cierra primero otras aplicaciones que tengan abierto ese puerto COM.
5. Abre el monitor serial a **9600 baudios**, con **Nueva línea**. Escribe `ESTADO` para ver modo, salida y conexión a WiFi/API.

No se cargó automáticamente el firmware a ningún dispositivo durante la preparación.

### Pines conservados

| Registro | Datos | Reloj | Latch |
| --- | --- | --- | --- |
| Primer 74HC595, funciones 1–8 | GPIO 13 / D7 | GPIO 14 / D5 | GPIO 12 / D6 |
| Segundo 74HC595, funciones 9–13 | GPIO 4 / D2 | GPIO 5 / D1 | GPIO 16 / D0 |

Se apagan ambos registros antes de activar exclusivamente la salida del comando. No se cambió el cableado del programa original.

## 4. Elegir control WiFi o serial

El valor inicial `START_IN_WIFI=true` arranca en WiFi con todas las salidas liberadas. La conexión y reconexión usan ESPAsyncTCP, de modo que el programa no espera en un bucle TCP ni usa `readStringUntil` para el serial.

| Entrada por serial | Resultado |
| --- | --- |
| `1` a `13`, con nueva línea | Toma prioridad **SERIAL** y ejecuta esa función |
| `0` | Libera salidas, sin cambiar el modo actual |
| `SERIAL` | Libera salidas y selecciona control local |
| `WIFI` | Libera salidas, selecciona WiFi y permite una nueva sesión del panel |
| `ESTADO` | Muestra modo, salida, WiFi y canal API |
| `ENCENDIDO 0` | Con las salidas liberadas, establece la suposición de carro apagado |
| `ENCENDIDO 1` | Con las salidas liberadas, establece la suposición de carro encendido |

La aplicación C# original sigue enviando números a 9600 baudios. Su primera orden no nula toma control serial. Para regresar al panel, cierra esa aplicación si mantiene ocupado el COM, abre el monitor serial y envía `WIFI`. No se mezclan órdenes seriales no nulas y órdenes remotas. El comando de parada 0 puede liberar desde ambos canales.

En modo serial, perder WiFi o apagar EC2/RDS **no libera ni interrumpe una salida local mantenida**; se libera con el 0 del programa local. Los cambios seriales se reportan como estado de la placa cuando hay conexión, pero no se escriben en RDS.

## 5. Usar Conducción

Recarga `/panel/` con **Ctrl + F5**, conecta con tu token y selecciona **Conducción → ESP8266 por WiFi**. Debe aparecer el ESP8266 en modo WIFI y con salidas liberadas. Pulsa **Activar conducción**.

Teclado, ratón/tacto y mando usan las mismas asignaciones personalizables. El modo alternativo **Solo registro en API / RDS** conserva el comportamiento anterior y no activa salidas del dispositivo. Las secuencias DEMO guardadas del panel principal continúan siendo de software; **DEMO del carro (código 8)** sí pulsa la salida 8 por el canal físico.

La liberación WiFi no necesita crear el código 0 en MySQL. Los códigos activos 1–13 se resuelven a los IDs reales del catálogo al abrir la sesión. Mientras hay control WiFi o registros pendientes, se rechazan movimientos individuales, cambios administrativos y DEMO del mismo vehículo para evitar controles contradictorios.

### Pulsaciones y encendido

Los códigos 1–4 y 10–13 se mantienen hasta liberar. Los códigos 5–8 generan un pulso local de **200 ms**. El 9 utiliza la estimación de la propia placa: **200 ms para encender** y **2 s para apagar**. El panel utiliza la duración confirmada por el firmware.

Un pulso en curso rechaza otros comandos no nulos para no acortarlo. Parar o cambiar explícitamente de modo puede interrumpirlo. Si se interrumpe el pulso 9, el encendido queda **sin determinar**; corrígelo con `ENCENDIDO 0` o `ENCENDIDO 1` por serial antes de volver a utilizarlo. La estimación inicial es apagado, igual que en el programa original; no es una lectura de un sensor.

### Qué se guarda en RDS

Cada orden no nula que la placa confirma se coloca en una cola de registro FIFO; los SP guardan estado e historial con origen **Panel WiFi**. La respuesta inmediata distingue la confirmación de salidas del registro todavía pendiente. Si falla el registro, se termina esa sesión WiFi y el panel muestra el error para evitar reintentos a ciegas de una orden que ya pudo actuar.

La cola de registros está en memoria: el cierre normal intenta drenarla durante hasta tres segundos, pero un reinicio abrupto puede perder registros pendientes. La parada 0 no espera a MySQL ni necesita un registro de catálogo: su confirmación se consulta en el estado del dispositivo. Por eso el último estado de RDS puede conservar el último comando no nulo aun cuando las salidas ya estén liberadas. La línea **ESP8266 · salida 0** de Conducción muestra el estado reportado por la placa.

### Pérdida de comunicación y reconexión

- Un solo navegador obtiene la sesión de control del vehículo. Debe renovarla cada 200 ms; la API la termina si pasan 900 ms sin renovación.
- La placa limita cada orden WiFi a **800 ms sin latidos válidos**, incluso durante un pulso largo. Si dejan de llegar, libera las salidas localmente y no continúa automáticamente al volver la red.
- Cada orden requiere primero un permiso de la placa, válido durante **500 ms según el reloj local del ESP8266**. Una orden atrasada no puede iniciar un movimiento después de una reconexión o usando un permiso vencido. No se requieren relojes sincronizados con EC2.
- Una reconexión recibe una identidad nueva, libera las salidas remotas y exige reactivar el panel. Nunca ejecuta automáticamente el último comando de RDS.
- Cerrar/ocultar la pestaña, perder foco, cambiar de sección o desconectar el mando solicita parada y termina la sesión. El watchdog de la placa cubre la pérdida de ese último mensaje.

No hay garantía de tiempo real estricto ni confirmación mecánica; los intervalos son límites de software que deben comprobarse con la placa, su alimentación y el circuito real.

## Validación realizada

El sketch completo compiló para ESP8266 Core 3.1.2/NodeMCU usando las versiones de bibliotecas indicadas. También se verificó la API con dispositivos y MySQL simulados: autenticación, sesión exclusiva, catálogo código/ID, ACK y permisos, rechazo de sesiones antiguas, prioridad serial, paradas sin esperar SQL, expiración, pulsación larga y errores de registro.

La prueba de navegador recorrió Conducción → API real local → ESP8266 simulado, incluidos mantener/liberar, código 8, encendido/apagado, pérdida de renovación y paso a serial. **Queda pendiente cargar el sketch y validar las salidas en el ESP8266 y el carro físicos.**

Referencias de implementación: [ESP8266 Core 3.1.2](https://github.com/esp8266/Arduino/releases/tag/3.1.2), [WebSockets](https://github.com/Links2004/arduinoWebSockets), [ESPAsyncTCP](https://github.com/dvarrel/ESPAsyncTCP), [ArduinoJson 7](https://arduinojson.org/v7/).
