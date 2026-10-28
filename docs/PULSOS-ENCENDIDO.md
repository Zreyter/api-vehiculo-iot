# Pulsaciones independientes de encendido y apagado

La ESP8266 acciona el mando. No tiene sensores que indiquen si el mando o la excavadora están encendidos.

En Conducción, **Enviar encendido (200 ms)** y **Enviar apagado (2 s)** envían pulsaciones de distinta duración sobre la misma salida física, código 9. Ambos funcionan sin indicar un estado supuesto. No se afirma que el equipo haya encendido o apagado: observa el resultado físicamente.

Se conserva la exclusión de pulsos simultáneos, la liberación al finalizar, la parada prioritaria y el watchdog. Una interrupción puede acortar un pulso y no modifica ninguna estimación de encendido. La API mantiene `encendido_estimado: null` por compatibilidad con clientes anteriores.

La API requiere `pulso_ms: 200` o `pulso_ms: 2000` junto a `codigo: 9` en `/vehiculos/{id}/control/orden`. Otros códigos rechazan ese campo. Se comprueba que el firmware anuncie `pulsos_encendido_explicitos: true` y que el ACK devuelva exactamente la duración solicitada; no se reintenta automáticamente una activación. Los clientes anteriores que no envían duración deben actualizarse para usar el código 9.

Los dos botones usan el comando 9 existente del catálogo; no hay que agregar comandos ni cambiar MySQL. El identificador 14 es únicamente una acción interna del panel para el botón de apagado: se traduce a código 9 y 2000 ms antes de enviar la orden. No representa una salida nueva.

Por serial, `ENCENDER` y `APAGAR` envían las pulsaciones respectivas. El número `9` envía siempre 200 ms. Se retiran `ENCENDIDO 0` y `ENCENDIDO 1`, que solo cambiaban una suposición. Se conservan 9600 baudios y el resto de comandos.

Actualizar la carpeta `app` completa de EC2 y cargar ambos archivos del sketch (`ControlCore.h` y `ControlCarroWiFi.ino`), conservando el archivo privado `config_carro.h` y el archivo `.globals.h`. Recargar el panel. El ejecutable de escritorio ya distribuido conserva su interfaz anterior hasta reconstruirlo.

Validación local: 141 pruebas Python, 34 pruebas JavaScript, navegador con API real y placa simulada (200 ms, 2000 ms y nuevo pulso después de liberar), y compilación completa para ESP8266/NodeMCU. Durante el despliegue solo se verifica la conexión y el estado de salidas; no se envían pulsaciones al mando real.

## Estado de la actualización — 27 de octubre de 2026

La API de EC2 y el firmware ya se actualizaron. La revisión posterior del enlace usa la biblioteca local corregida `firmware/libraries/WebSockets`; consulta [ENLACE-ESTABLE.md](ENLACE-ESTABLE.md) antes de una nueva compilación. El usuario confirmó las nuevas demos con la excavadora real; esa confirmación no acredita una prueba nueva específica de cada pulsación de encendido/apagado ni añade sensores de estado.

## Publicación 1.6.5 — 28 de octubre de 2026

La release 1.6.5 incluye el panel revisado en el ejecutable reconstruido, la actualización manual de EC2 y las fuentes del firmware con su biblioteca corregida. Los comentarios anteriores sobre el ejecutable ya distribuido corresponden a 1.6.4. Consulta [RELEASE-1.6.5.md](RELEASE-1.6.5.md).
