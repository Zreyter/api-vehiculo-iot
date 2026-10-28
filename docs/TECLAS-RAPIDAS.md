# Versión 1.6.4: pulsaciones rápidas y sesión de conducción

Este documento conserva la corrección y las pruebas de 1.6.4. Para la versión vigente, incluidas las demos físicas y el firmware revisado, consulta [RELEASE-1.6.5.md](RELEASE-1.6.5.md).

**Actualiza primero la carpeta `app` de EC2 y después usa el exe 1.6.4.** Esta corrección necesita ambos lados: el servidor verifica el orden de las solicitudes. El firmware actual del ESP8266 sigue siendo compatible y no se vuelve a cargar.

## Qué se reprodujo

Cuando las órdenes confirmadas llegaban más rápido de lo que RDS las guardaba, la cola de 32 registros se llenaba. La API detectaba la cola llena después de activar otra orden, detenía las salidas y terminaba la sesión. La liberación posterior recibía HTTP 409 y podía ocultar el error original de registro.

También se comprobó el caso en que el POST de activar llega después de su liberación por usar conexiones HTTP diferentes. El cambio de generación interno de la API no distinguía una solicitud anterior que todavía no había entrado al servidor.

Estos defectos se reprodujeron con simuladores. No demuestra que cada corte del carro real tenga ese origen.

## Cambios

- La capacidad de registro se comprueba **antes de activar**. Si RDS tiene la cola llena, la API libera las salidas con confirmación y conserva la sesión. El panel muestra «Se están guardando los movimientos. Suelta los controles y vuelve a pulsar». Esa pulsación no se aplica ni se presenta como un movimiento registrado. No se amplió la cola ni se descartan movimientos ya aplicados; los registros anteriores siguen guardándose en orden.
- Al recibir ese aviso, el cliente mantiene la salida cero y exige una nueva pulsación. No vuelve a activar por sí solo la tecla o el stick que permanecían mantenidos.
- Cada orden y liberación WiFi lleva un número de intención creciente por sesión. Una solicitud anterior o duplicada se descarta, aunque llegue después por otra conexión. Una orden en preparación vuelve a comprobar que sigue siendo la más reciente antes de activar.
- La liberación del propietario sigue siendo válida cuando acaba de vencer su sesión. Una liberación posterior a una parada terminal confirmada puede consultar esa confirmación durante 30 segundos, sin enviar órdenes adicionales, siempre que siga siendo el mismo dispositivo, en WiFi, sin otro propietario y con salidas cero. No se toma un simple estado cero como prueba de parada ni se reutiliza una parada transitoria anterior.
- La API expone `registros_pendientes` y `ultima_interrupcion` en el estado del dispositivo. Una sesión que realmente termina indica el motivo correspondiente en vez de atribuir todos los casos a otro controlador.

Se conservan el watchdog del ESP8266 de **800 ms**, la sesión de **900 ms**, la autenticación, los permisos efímeros y la prioridad serial. No se reintentan activaciones ni pulsos. No se adquiere otra sesión automáticamente después de una pérdida real de control.

La API mantiene compatibilidad HTTP con clientes anteriores que no envían intención. El panel/exe 1.6.4 exige la capacidad `protocolo_control: 2` para activar la conducción; una API anterior muestra una indicación de actualización antes de habilitar los controles. Los clientes anteriores no ofrecen la protección nueva frente a solicitudes reordenadas.

## Verificación

- **156 pruebas automatizadas:** 114 Python, 20 del controlador de entradas, 7 del adaptador de conducción y 15 del adaptador HTTP de escritorio.
- **330 pulsaciones** en la página y el exe empaquetado: en cada uno se probaron 80 pulsaciones cortas con activaciones retrasadas 120 ms, y otras 85 con registros RDS retrasados 600 ms. Se verificó que no hubiera activaciones posteriores a soltar ni HTTP 409, que se conservara la misma sesión y que otra pulsación funcionara al terminar el guardado.
- Pruebas de duplicados, nuevas intenciones durante una preparación, cola llena antes de activar, conservación de los 33 registros ya aplicados, sesiones vencidas, prueba de parada, prioridad serial y limpieza de un controlador antiguo frente a uno nuevo.

Las pruebas no enviaron órdenes al carro real ni actualizaron EC2.

## Aplicar la corrección

1. Cierra el exe anterior y detén Uvicorn en EC2.
2. Guarda una copia de la carpeta `app` actual.
3. Descomprime `Actualizacion-teclas-1.6.4.zip` y sustituye la carpeta `app` completa de EC2 por la del paquete. Conserva `.env`, certificados, entorno virtual y base de datos. No cambian las dependencias Python.
4. Inicia desde la raíz del proyecto con un proceso:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

5. Comprueba que `/docs` muestre **1.6.4**. Recarga el panel con Ctrl+F5.
6. Abre `Vehiculo-IoT-1.6.4-Windows-x64.exe`, usa tu servidor/token habituales y activa la conducción con las teclas y el mando sueltos.

Descarga el exe, el paquete EC2, las instrucciones y sus checksums en la [release v1.6.4](https://github.com/Zreyter/api-vehiculo-iot/releases/tag/v1.6.4).
