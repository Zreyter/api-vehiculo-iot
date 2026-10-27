# Latencia de conducción: 1.6.1 y corrección 1.6.2

La revisión vigente de la API es **1.6.2**. Corrige cancelaciones de sesión por permisos anticipados tardíos y la confirmación de parada; consulta [ESTABILIDAD.md](ESTABILIDAD.md). Usa el paquete `Actualizacion-estabilidad-1.6.2.zip` para EC2. El exe 1.6.1 y el firmware actual siguen siendo compatibles.

Esta revisión mantiene el protocolo del ESP8266 de v1.5/v1.6. **No hace falta volver a cargar la placa**. Se actualizan la API/panel de EC2 y la app Windows.

## Cambios

- Al pulsar Activar conducción se prepara la sesión antes de habilitar los botones. El catálogo y la primera parada dejan de esperar a la primera tecla.
- Durante una sesión válida la API prepara un permiso para la siguiente orden. Si está fresco, la orden necesita un intercambio con la placa en lugar de dos en el recorrido de la pulsación.
- Desde 1.6.2 la caché dura como máximo 150 ms desde el envío de la preparación, incluyendo el recorrido de red. El firmware mantiene su vencimiento local de 500 ms y el permiso sigue siendo de un solo uso y ligado a sesión, controlador y secuencia. Si falta o envejece, se solicita uno nuevo.
- Soltar o parar por WiFi envía la liberación sin esperar el ACK de avance. La API invalida los permisos pendientes y rechaza la activación de una orden que quedó detrás de la parada. Una respuesta antigua no restaura el estado del controlador.
- El adaptador de escritorio reutiliza conexiones HTTP/TLS con un conjunto limitado de sockets; no reintenta automáticamente escrituras fallidas. Los WebSocket utilizan TCP_NODELAY.

Se mantienen prioridad serial, autenticación, watchdog local de 800 ms y caducidad de la sesión de navegador. Preparar permisos no activa salidas ni renueva el watchdog. RDS sigue registrándose en segundo plano.

## Medición de laboratorio

En la revisión 1.6.1 se simuló un tramo API–ESP8266 de 60 ms de ida y vuelta. Se midieron seis órdenes cuando la sesión ya estaba preparada:

| Recorrido hasta confirmar la orden | Mediana |
| --- | ---: |
| Permiso solicitado al pulsar + orden | 138.6 ms |
| Permiso anticipado + orden | 77.35 ms |

La reducción observada fue del 44.2 % en ese tramo. La simulación no incluye la conexión de la computadora a EC2 ni el tiempo mecánico del carro, y no garantiza esos valores en Internet.

Se verificaron además la liberación con una respuesta de avance retenida 700 ms, cancelación al salir durante la preparación, vencimiento de permisos, respuestas antiguas, prioridad serial, renovación y reutilización de conexiones.

## Actualizar EC2 Windows

1. Detén el proceso de Uvicorn que sirve tu API.
2. Guarda una copia de la carpeta `app` que tienes en EC2.
3. Copia la carpeta `app` completa del paquete `Actualizacion-estabilidad-1.6.2` a la raíz de tu proyecto en EC2, sustituyendo los archivos de `app`.
4. Conserva `.env`, `certs`, `.venv` y la base de datos. No cambian las dependencias Python.
5. Desde la raíz del proyecto inicia:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

6. En `/docs` debe aparecer la versión `1.6.2`. En la página pulsa Ctrl+F5 para actualizar sus scripts.
7. Abre `Vehiculo-IoT-1.6.1-Windows-x64.exe` y usa el servidor/token habituales. La placa permanece con el firmware actual y en modo WIFI.

Si se abre el nuevo exe contra la API anterior, conserva compatibilidad HTTP, pero los permisos anticipados requieren actualizar la API de EC2. El recorrido sigue pasando por AWS; no se ha añadido control directo por la red local.
