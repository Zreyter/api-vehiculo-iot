# Versión 1.6.5 — demos físicas y enlace estable

Publicación del 28 de octubre de 2026.

Las demos creadas en la página ahora ejecutan los movimientos guardados en la excavadora: duración limitada en la ESP8266, salidas liberadas en las pausas, cancelación y parada al perder la conexión. El botón DEMO del mando (código 8) sigue siendo independiente.

El usuario confirmó en este chat que probó nuevas demos con la excavadora real y funcionan correctamente. También observó una respuesta más rápida; es una apreciación cualitativa, sin una nueva medición de latencia mecánica. La placa sigue confirmando salidas, sin sensores de movimiento o encendido.

## Cambios incluidos

- Encendido y apagado envían pulsaciones explícitas de 200 y 2000 ms por la salida 9, sin asumir el estado del equipo.
- El panel descarta resultados de renovaciones anteriores a una confirmación posterior; las respuestas tardías no reactivan una sesión suspendida.
- La API recupera el saludo inicial dentro del plazo existente y publica diagnóstico de enlace.
- El firmware usa la biblioteca local WebSockets 2.7.2 con reintentos asíncronos de uno en uno e identificación del objeto TCP al cerrar; incluye contadores seriales de comunicación.
- El ejecutable Windows 1.6.5 incluye los siete recursos del panel, también `demo-control.js`.

Se conservan watchdog de hasta 800 ms, permiso de control de 900 ms, frescura de confirmaciones de 650 ms y detección de silencio del dispositivo a los tres segundos. Una reconexión exige una nueva activación; no reanuda movimientos o demos.

## Actualizar EC2 manualmente

1. Descarga y extrae `Actualizacion-EC2-1.6.5.zip`.
2. En el Programador de tareas de EC2, detén `API Vehiculo IoT`.
3. En `C:\Apps\api-vehiculo-iot`, cambia el nombre de la carpeta `app` actual por un respaldo fechado.
4. Copia la nueva carpeta `app` del ZIP a esa misma ruta. Conserva `.env`, `.venv`, `certs` y la tarea de arranque existentes.
5. Ejecuta `API Vehiculo IoT`, comprueba la API y recarga `/panel/` con Ctrl+F5. OpenAPI debe identificarla como 1.6.5.

La publicación no despliega la instancia automáticamente. No cambian procedimientos de MySQL ni dependencias Python. Por preferencia del usuario, las próximas actualizaciones de la app también se entregan para carga manual.

## Firmware y escritorio

Extrae `Firmware-ESP8266-1.6.5.zip`. Conserva tu `config_carro.h` privado y el archivo `ControlCarroWiFi.ino.globals.h`. Usa ESP8266 Core 3.1.2/NodeMCU, ESPAsyncTCP 1.2.4 y ArduinoJson 7.4.3. Selecciona explícitamente la biblioteca corregida incluida:

```powershell
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 --library firmware/libraries/WebSockets firmware/ControlCarroWiFi
```

Carga el sketch en el puerto de tu placa y consulta `ESTADO` a 9600 baudios. No reemplaces la biblioteca local por otra copia global sin corregir. El paquete de firmware contiene fuentes y licencia, sin binarios con credenciales integradas. Si ya tienes cargada la revisión corregida y probada de esta conversación, estos archivos conservan ese comportamiento; no es necesaria una nueva carga solo por la etiqueta 1.6.5.

Abre `Vehiculo-IoT-1.6.5-Windows-x64.exe`, selecciona la API y escribe tu token habitual. No se incluye ningún token en el ejecutable. Las releases anteriores permanecen intactas; los clientes que no envían `pulso_ms` deben actualizarse para usar el encendido/apagado de la salida 9.

## Evidencia y alcance

La revisión funcional pasó 145 pruebas Python, 37 JavaScript y tres recorridos de navegador. En la placa real, con salidas en cero, se comprobaron 320 renovaciones antes y otras 320 después del reinicio manual de EC2, sin cortes adicionales; la expiración rechazó la renovación tardía con 409. La confirmación posterior del usuario acredita el funcionamiento observado de las nuevas demos con la excavadora real. No documenta una comprobación manual individual de todos los escenarios de fallo.

Detalles: [demos físicas](DEMOS-FISICAS.md), [enlace](ENLACE-ESTABLE.md), [pulsaciones](PULSOS-ENCENDIDO.md) y [registro de validación](../VALIDACION.md).
