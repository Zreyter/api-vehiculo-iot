# Conducción desde el panel

La sección **Conducción** recupera los 13 controles de `ControlCarro.cs` y del ESP8266, con la paleta crema, verde y naranja del panel. Admite teclado personalizable, ratón/tacto y mando estándar como Xbox.

## Dos tipos de control

- **ESP8266 por WiFi**: requiere la API actualizada y el [firmware WiFi/serial](ESP8266_WIFI_SERIAL.md). La placa confirma las salidas y limita movimientos/pulsos con un watchdog local. Esto no constituye una medición de movimiento mecánico mediante sensores.
- **Solo registro en API / RDS**: conserva las rutas HTTP anteriores; registra comandos sin activar salidas del dispositivo.

Para habilitar WiFi, copia la carpeta `app` completa de esta versión a EC2, reinicia la API y recarga con Ctrl + F5. Conserva `.env`, certificados y entorno virtual.

## Comenzar

1. Conecta la API con `CONTROL_TOKEN`, abre **Conducción** y selecciona el vehículo.
2. Elige el tipo de control. En WiFi, espera al ESP8266 en modo WIFI y con salidas liberadas. En registro, hace falta un comando activo con código 0 para liberar el estado.
3. Pulsa **Activar conducción**, con el canal de eventos conectado y esta ventana en primer plano.
4. Mantén una tecla o botón para mover; al soltar se libera. La última entrada mantenida tiene prioridad; al soltarla se recupera la anterior.
5. **Parar / liberar**, **Espacio** (asignación inicial) o **Esc** libera y desactiva. Reactiva para continuar.

Se relacionan acciones por `codigo`, sin suponer que coincide con `id_comando` ni buscar nombres parecidos. Las acciones faltantes quedan deshabilitadas y los códigos activos ambiguos impiden activar la conducción. La liberación WiFi no necesita crear el código 0 en MySQL.

## Asignaciones iniciales

| Código | Acción | Tecla | Mando Xbox estándar | Comportamiento |
| --- | --- | --- | --- | --- |
| 0 | Parar / liberar | Espacio; Esc siempre para | Vista / Back | Libera y desactiva |
| 1 | Pala izquierda | ← | Stick derecho ← | Mantener |
| 2 | Avanzar | W | Stick izquierdo ↑ | Mantener |
| 3 | Retroceder | S | Stick izquierdo ↓ | Mantener |
| 4 | Pala derecha | → | Stick derecho → | Mantener |
| 5 | Mute | Z | X | Pulso de 200 ms |
| 6 | Velocidad | X | A | Pulso de 200 ms |
| 7 | Luces LED | C | Y | Pulso de 200 ms |
| 8 | DEMO del carro | V | B | Pulso de 200 ms |
| 9 | Encender / apagar | P | Menú / Start | 200 ms para encender; 2 s para apagar |
| 10 | Carro izquierda | A | Stick izquierdo ← | Mantener |
| 11 | Agarrar pala | ↑ | Stick derecho ↑ | Mantener |
| 12 | Soltar pala | ↓ | Stick derecho ↓ | Mantener |
| 13 | Carro derecha | D | Stick izquierdo → | Mantener |

El código 4 sigue siendo mantenido. **DEMO del carro (8)** es el botón del control original; las secuencias SQL del panel principal siguen siendo operaciones de software.

Las funciones rápidas se disparan una sola vez por pulsación. En WiFi el firmware decide la duración y el panel respeta su confirmación. Durante un pulso se ignoran otras nuevas entradas no nulas para no cortarlo. Parar y la suspensión pueden interrumpirlo.

## Encendido supuesto

En WiFi se muestra la estimación de la placa. Inicialmente supone apagado y alterna al completar el pulso 9. Si se interrumpe, queda sin determinar: con las salidas liberadas utiliza por serial `ENCENDIDO 0` o `ENCENDIDO 1` y reactiva la conducción.

En modo de registro, selecciona **Suponer apagado** o **Suponer encendido** con los controles desactivados; la temporización depende del navegador/red. Ningún modo usa un sensor para confirmar alimentación.

## Personalizar teclado y mando

Desactiva y despliega **Personaliza tus controles**. Pulsa una tecla de la tabla y luego la nueva tecla física; Esc cancela. × quita la asignación. Los selectores del mando admiten botones, gatillos, cruceta y direcciones de los sticks. Una entrada pertenece a una sola acción: reutilizarla la quita de la anterior. **Restaurar asignaciones** recupera el mapa inicial.

La zona muerta inicial es 25 %, ajustable de 10 % a 80 %. Conecta el mando al equipo del navegador, pulsa un botón para detectarlo y selecciónalo. Debe tener distribución `standard`. Después de activar, centra los sticks y suelta los botones antes de moverlos.

Las preferencias se guardan en `localStorage`, clave `vehiculo-iot.conduccion.v1`, sin incluir el token. Si el almacenamiento está bloqueado solo duran la sesión. Las teclas usan `KeyboardEvent.code` (posición física); no se conduce al escribir en campos, diálogos o con Ctrl/Alt/Windows.

Gamepad API requiere **HTTPS para el panel remoto**, o localhost en uso local. El teclado puede funcionar por IP pública HTTP aunque el navegador bloquee el mando. Referencia: [Gamepad API de MDN](https://developer.mozilla.org/en-US/docs/Web/API/Gamepad_API/Using_the_Gamepad_API).

## Liberación y registro

Cambiar de sección/vehículo, perder el foco, ocultar la pestaña, abrir un campo o diálogo, desconectar el mando, perder eventos o desconectar la API solicita liberar y exige reactivar. Los errores HTTP también desactivan los controles.

En WiFi hay una sesión exclusiva renovada por el navegador y un watchdog de 800 ms en la placa. Cada nueva activación requiere un permiso efímero del ESP8266. Una reconexión no reproduce RDS. El control serial tiene prioridad y no se interrumpe por la limpieza de una sesión antigua del navegador. Consulta sus detalles y límites en la [guía del firmware](ESP8266_WIFI_SERIAL.md).

Las órdenes WiFi confirmadas se registran después en una cola FIFO con origen **Panel WiFi**. Parar no espera a SQL. La línea **ESP8266 · salida 0** muestra el estado reportado; RDS puede conservar el último comando no nulo. Un fallo de registro termina la sesión y se muestra en el panel.

## Pruebas locales

```powershell
python -m unittest discover -s tests -v
node --test tests/test_driving.js
```

Se verificaron API y lógica de conducción con MySQL/dispositivos simulados, el recorrido del navegador y la compilación del sketch. La carga y comprobación en el carro real siguen pendientes.
