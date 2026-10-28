# Demos creadas en la página: ejecución física

Integración desplegada en EC2 y firmware cargado en la ESP8266 sobre la versión 1.6.4. El 27 de octubre de 2026, el usuario confirmó que las nuevas demos creadas en la página funcionan correctamente con la excavadora real.

El botón **Iniciar secuencia** del panel envía los pasos de la demo guardada al ESP8266. Es independiente de **DEMO del carro**, código 8, que pulsa el botón de demo automática del mando.

## Prueba con la excavadora real — 27 de octubre de 2026

Después de actualizar la API de EC2 y cargar el firmware corregido en la ESP8266, el usuario creó y ejecutó nuevas demos desde la página con la excavadora real. Confirmó en este chat: «ya probe nuevas demos y funcionan perfectamente» y que nota que «responde hasta mas rapido».

**Resultado registrado: las demos creadas en la página fueron probadas con la excavadora real y funcionan correctamente, según la comprobación manual del usuario.** La respuesta más rápida es una observación cualitativa del operador; no se midió una nueva latencia mecánica ni se asigna un porcentaje de mejora.

Esta confirmación corresponde a las nuevas demos ejecutadas. No detalla una prueba manual de cada caso de cancelación, desconexión o duración; esos casos tienen la cobertura automatizada y de enlace descrita más adelante. La API y el firmware confirman salidas del microcontrolador, sin sensores de movimiento o encendido: se conserva `ejecucion_fisica_confirmada=false` y `encendido_estimado=null`.

## Actualizar

1. Detén la API de EC2 y combina la carpeta `app` del paquete con la carpeta `app` del proyecto. Conserva `.env`, `certs`, `.venv` y la configuración de arranque existentes. Reinicia usando un solo proceso Uvicorn. No cambian dependencias ni procedimientos de MySQL.
2. Actualiza **ambos** archivos del sketch: `ControlCarroWiFi.ino` y `ControlCore.h`. Conserva `ControlCarroWiFi.ino.globals.h` y tu `config_carro.h` privado.
3. Compila y sube el sketch a tu ESP8266 seleccionando explícitamente la biblioteca corregida `firmware/libraries/WebSockets`; no uses en su lugar la copia global sin corregir. Consulta `ENLACE-ESTABLE.md` y `firmware/libraries/WebSockets/LOCAL-CHANGES.md`. La compilación se comprobó para NodeMCU 1.0 / ESP-12E, Core 3.1.2. Consulta `ESP8266_WIFI_SERIAL.md` para el procedimiento completo.
4. Abre de nuevo la página `/panel/`, conecta la API y selecciona el vehículo. La placa debe estar conectada en modo WIFI y la conducción manual desactivada.

La API rechaza la ejecución física si la placa no anuncia `demo_temporizada: true`; el firmware anterior no ejecuta estas secuencias. El control manual sigue usando su protocolo anterior. El ejecutable 1.6.4 ya distribuido conserva su interfaz anterior: esta entrega habilita la **página web** y actualiza el código fuente del escritorio para una futura compilación, sin reemplazar ejecutables existentes.

## Preparar y ejecutar una secuencia

En Administración, utiliza comandos activos del vehículo y configura su orden, duración y pausa:

| Códigos admitidos | Acción |
| --- | --- |
| 1–4 y 10–13 | Movimientos de la excavadora, duración de 1 a 60000 ms |
| 0 | Parar/liberar; permite una espera de 0 a 60000 ms si está definido en el catálogo |

La pausa de cada paso admite 0 a 60000 ms. No se admiten 5–9: mute, velocidad, luces, demo automática y encendido tienen pulsaciones o efectos propios que no permiten garantizar una secuencia cancelable de movimientos. Se valida toda la demo antes de activar las salidas; no se ejecuta parcialmente un plan inválido.

Pulsa **Iniciar secuencia** y mantén abierta y conectada esa página. Cada movimiento se limita en la propia placa a la duración solicitada. El servidor también libera las salidas y espera confirmación de cero antes de comenzar la pausa y preparar el siguiente paso. La red y las consultas a RDS pueden añadir tiempo entre pasos; no alargan la activación limitada por el temporizador local. No se promete sincronización mecánica al milisegundo.

**Cancelar** solicita liberación inmediatamente, sin esperar consultas MySQL. Si una consulta ya estaba en curso, la respuesta HTTP puede esperar su término, pero no se envían movimientos posteriores. La finalización o cancelación solo se informa como tal después de confirmar la parada; sin confirmación se informa un error.

## Conexión y parada

- La página renueva cada 250 ms. Si transcurren 900 ms sin renovación válida, la API termina la demo y solicita parada; comprueba el vencimiento aproximadamente cada 150 ms.
- Si se cierra la página, se cambia de vehículo o se pierde su canal de eventos, cesan las renovaciones. No se reanuda la demo automáticamente.
- La placa conserva su watchdog de hasta 800 ms sin latidos válidos y libera al detectar desconexión de su WebSocket. El temporizador local del paso sigue siendo un límite adicional.
- Si el servidor detecta desconexión, rechazo de orden, toma del puerto serial o un error de base de datos, omite los pasos pendientes. Cuando no puede confirmar cero, informa el error sin declarar ejecución física confirmada.
- Una demo reserva el vehículo: no puede mezclarse con otra demo, conducción manual o edición de su catálogo. Reconectar requiere iniciar una ejecución nueva.

La confirmación acredita salidas del microcontrolador, **no movimiento mecánico medido**. Se conserva `ejecucion_fisica_confirmada=false`; no hay sensores que permitan cambiarlo. Las demos conservan el comportamiento anterior de no agregar historial de movimientos individuales.

## API y compatibilidad

`POST /vehiculos/{id}/demos` acepta `{"id_demo":42,"modo":"fisico"}` y devuelve `id_ejecucion`. El cliente debe renovar con `POST /vehiculos/{id}/demos/activa/latido`, cuerpo `{"id_ejecucion":"<identificador devuelto>"}`. Ambas rutas requieren el token de control. Un identificador vencido o de otra ejecución recibe 409 y no puede reactivar nada.

`DELETE /vehiculos/{id}/demos/activa` cancela. Para conservar clientes anteriores, omitir `modo` equivale a `modo: "registro"`, que solo actualiza RDS y emite eventos. La página actualizada solicita explícitamente el modo físico.

El firmware recibe `demo_ms` junto a la orden, limita los movimientos a ese intervalo y devuelve la duración en el ACK. Los comandos manuales sin ese campo conservan su comportamiento anterior.

## Validación automatizada de la integración inicial

- 134 pruebas Python: API, catálogo, autenticación, exclusión de controles, registro, estabilidad y demos; incluyen 20 pruebas específicas de ejecución física.
- 34 pruebas JavaScript: controles existentes y renovación de la página, incluidas respuestas tardías y cierre de ejecución.
- 15 pruebas del intermediario de escritorio y preparación de sus siete recursos públicos. No se construyó un nuevo ejecutable.
- Navegador Edge con API real local, MySQL simulado y ESP8266 simulado por WebSocket: secuencia de dos pasos, duraciones locales, liberación y pausas, cancelación, pérdida del canal de eventos y desconexión/reconexión de placa sin repetir pasos. Sin errores JavaScript en los recorridos comprobados.
- Sketch completo compilado con Arduino CLI para `esp8266:esp8266:nodemcuv2`, usando configuración de ejemplo, sin cargar hardware.

La integración inicial anterior se comprobó con simuladores. La prueba física posterior del usuario está registrada al comienzo de esta guía; los resultados vigentes del enlace y de las suites ampliadas están en `ENLACE-ESTABLE.md` y `../VALIDACION.md`. Para futuras comprobaciones de una demo modificada, crea una demo corta (por ejemplo avance 300 ms, pausa 500 ms y giro 300 ms) y observa orden y parada. Comprueba también cancelar durante un paso y durante una pausa, y cortar la conexión de la página y de la placa. Elimina o sustituye cualquier paso 5–9 antes de iniciar una secuencia física.

## Publicación 1.6.5 — 28 de octubre de 2026

La release 1.6.5 incluye el panel revisado en el ejecutable reconstruido, la actualización manual de EC2 y las fuentes del firmware con su biblioteca corregida. Los comentarios anteriores sobre el ejecutable ya distribuido corresponden a 1.6.4. Consulta [RELEASE-1.6.5.md](RELEASE-1.6.5.md).
