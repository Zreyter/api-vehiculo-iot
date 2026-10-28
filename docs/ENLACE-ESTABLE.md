# Enlace ESP8266 y pausas de conducción

Revisión local del 27 de octubre de 2026, posterior a las demos físicas y los botones de encendido/apagado separados.

## Hallazgos

Se observó un corte breve del canal de la placa mientras el WebSocket del navegador permanecía conectado. El registro anterior no identificaba la causa del cierre. Las capturas posteriores, sin activar salidas, mostraron 45 segundos de reposo y una sesión de 45 segundos con 121 renovaciones correctas, señal WiFi fuerte y memoria estable. Esto no permite atribuir todos los cortes a una única causa física.

Sí se reprodujo un fallo concreto del panel: si una renovación fallaba tarde después de haberse confirmado otra posterior de la misma sesión, el panel desactivaba Conducción innecesariamente. También una respuesta antigua podía sobrescribir el instante de la confirmación más reciente. Las regresiones reproducen ambos problemas antes de corregirlos.

## Cambios

- Cada renovación tiene un orden local. Solo una confirmación vigente puede actualizar la referencia de comunicación; fallos de solicitudes anteriores a una confirmación posterior no revocan esa sesión.
- Al detectar una pérdida real, se bloquean las renovaciones de esa ejecución. Las respuestas tardías no reactivan el controlador.
- La API puede repetir el saludo inicial dentro del plazo existente de tres segundos si aún no recibió un estado válido. Nunca repite saludos en una sesión establecida ni extiende el plazo de un dispositivo silencioso.
- El firmware trata un saludo repetido de la misma sesión de forma idempotente: confirma sin reiniciar salidas, permisos o secuencias.
- Se utiliza WiFi sin ahorro de energía para reducir latencia de radio. El firmware detecta también cierres TCP que el transporte asíncrono no notifica mediante su evento habitual y libera las salidas.
- El monitor serial muestra tiempo desde el arranque, motivo de desconexión, RSSI y memoria. `ESTADO` consulta esos datos sin mover el vehículo.
- `/vehiculos/{id}/dispositivo` añade `diagnostico_enlace`: conexiones, cierres, motivo del último cierre, silencio medido y confirmación del saludo. Los contadores se reinician al reiniciar la API.

La prueba posterior al primer despliegue reprodujo un ciclo de cortes tras reiniciar EC2: el WiFi seguía conectado, los reportes vencían y aparecían rechazos HTTP 403 durante la reconexión. Se localizaron reintentos recursivos desde error y cierre en WebSockets 2.7.2. La copia local incluida serializa los intentos, identifica el objeto TCP al cerrar y despacha reintentos desde el bucle sin bloquear. Ver firmware/libraries/WebSockets/LOCAL-CHANGES.md. Los contadores TX/RX permiten observar el intercambio.

## Seguridad conservada

No se amplían los tiempos: watchdog local hasta 800 ms, sesión de control 900 ms, confirmaciones del navegador con límite de 650 ms y detección de silencio del dispositivo a los tres segundos. La pérdida de foco del panel sigue deteniendo Conducción. No se repiten activaciones ni se reanudan pasos de demos tras una reconexión. Encendido y apagado conservan sus pulsaciones explícitas de 200 y 2000 ms.

## Actualización y pruebas

Actualizar `app` completa en EC2 con la API detenida, conservando `.env`, certificados y entorno virtual. Cargar el sketch revisado conservando `config_carro.h` y el archivo `.globals.h`; usar la biblioteca WebSockets corregida incluida en firmware/libraries; no cambian procedimientos MySQL. Recargar el panel.

Validación: suite Python completa, 37 pruebas JavaScript, tres recorridos del navegador con fallos de red simulados y compilación ESP8266. Las comprobaciones técnicas del enlace descritas en esta revisión se realizaron con las salidas en cero; la prueba manual posterior de las demos con movimiento real se registra en el apartado final. Ninguna de estas pruebas garantiza la ausencia de cortes de red futuros. Los diagnósticos permiten identificar un corte posterior sin suprimir su parada de seguridad.

## Resultado de la comprobación real

EC2 sirve los seis archivos del panel verificados contra las fuentes y publica el diagnóstico de enlace. ESP8266EX en COM3: carga y hash del firmware verificados. La biblioteca corregida se seleccionó explícitamente al compilar.

- Antes del reinicio manual de EC2: 320 renovaciones correctas en 120,6 segundos, máximo 187 ms; 307 consultas de estado durante 130 segundos, ninguna sin disponibilidad y ningún cierre adicional.
- Al detener la tarea de EC2, la placa notificó la desconexión y dejó las salidas en cero. Al volver a ejecutarla, reconectó y confirmó el saludo sin reiniciar la ESP8266; no se reanudaron movimientos.
- Después del reinicio: otras 320 renovaciones correctas en 121,1 segundos, máximo 189 ms, con liberación final confirmada. EC2 mantuvo una sola conexión y ningún cierre adicional durante la comprobación.
- Al dejar de renovar una sesión en cero durante dos segundos, la API rechazó la renovación tardía con 409, informó `sesion_vencida` y confirmó el control libre y el código activo cero.
- 145 pruebas Python y 37 JavaScript correctas; tres recorridos del navegador con pérdida de confirmaciones, respuestas fuera de orden y desconexión del dispositivo. No se enviaron movimientos ni pulsaciones de encendido/apagado en estas comprobaciones reales.

Por preferencia del usuario, las siguientes actualizaciones de la app de EC2 se entregan como ZIP para carga manual. `EC2-enlace-estable.zip` contiene la carpeta `app` y las instrucciones; `Firmware-enlace-estable.zip` contiene las fuentes y la biblioteca local corregida, sin credenciales.

## Prueba con la excavadora real — 27 de octubre de 2026

Después de actualizar la API de EC2 y cargar el firmware corregido en la ESP8266, el usuario creó y ejecutó nuevas demos desde la página con la excavadora real. Confirmó en este chat: «ya probe nuevas demos y funcionan perfectamente» y que nota que «responde hasta mas rapido».

**Resultado registrado: las demos creadas en la página fueron probadas con la excavadora real y funcionan correctamente, según la comprobación manual del usuario.** La respuesta más rápida es una observación cualitativa del operador; no se midió una nueva latencia mecánica ni se asigna un porcentaje de mejora.

Esta confirmación corresponde a las nuevas demos ejecutadas. No detalla una prueba manual de cada caso de cancelación, desconexión o duración; esos casos tienen la cobertura automatizada y de enlace descrita más adelante. La API y el firmware confirman salidas del microcontrolador, sin sensores de movimiento o encendido: se conserva `ejecucion_fisica_confirmada=false` y `encendido_estimado=null`.

La confirmación manual posterior complementa las pruebas técnicas anteriores; no modifica los temporizadores de parada ni habilita reanudación automática.
