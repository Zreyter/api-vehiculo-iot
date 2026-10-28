# WebSockets 2.7.2: cambio local para ESP8266 asíncrono

Se conserva la licencia LGPL y el código original en `src`. Referencia: https://github.com/Links2004/arduinoWebSockets

En `WebSocketsClient.cpp` y `.h`, los reintentos de conexión se programan desde `loop()` con el intervalo existente y un solo `AsyncClient` pendiente. Los callbacks de error y cierre no abren conexiones recursivamente. Un cierre tardío solo limpia el canal si pertenece al mismo objeto TCP. El cierre real emite `WStype_DISCONNECTED` y libera las salidas inmediatamente. Se desactiva Nagle en el cliente asíncrono.

El sketch debe llamar `socketAPI.loop()`; esta variante solo despacha conexiones asíncronas y nunca espera una conexión TCP. No modifica watchdog, duración de movimientos, pausas ni permisos. Seleccionar esta biblioteca explícitamente al compilar; no sustituir silenciosamente por la instalada globalmente.

Compilación desde la raíz del proyecto, con ESP8266 Core 3.1.2 y las dependencias ya instaladas:

```powershell
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 --library firmware/libraries/WebSockets firmware/ControlCarroWiFi
```

Conservar el archivo privado `config_carro.h` y `ControlCarroWiFi.ino.globals.h`. El paquete público no contiene credenciales ni binarios con credenciales integradas.
