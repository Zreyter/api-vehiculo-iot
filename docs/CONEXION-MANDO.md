# Revisión local 1.6.3: conexión del exe y conducción con mando

El exe 1.6.3 funciona con la API **1.6.2 que ya está en EC2**. Para probar la corrección en Windows basta con cerrar el exe anterior y abrir el nuevo. No hay que volver a programar el ESP8266. El paquete de actualización de EC2 aplica las mejoras compartidas también a la página web y muestra 1.6.3 en `/docs`.

Esta revisión se entrega localmente. La release de GitHub v1.6.2 conserva sus archivos originales.

## Hallazgos y cambios

Se reprodujeron defectos del cliente que podían contribuir a los errores reportados:

- Las consultas generales y los controles compartían ocho conexiones. Ocho consultas lentas dejaban una renovación esperando y podían vencer los 900 ms de sesión. El exe reserva grupos separados para consultas, órdenes y renovaciones.
- Un socket HTTP reutilizado que el servidor cierre puede producir `ECONNRESET` y HTTP 502; este caso está descrito en la [documentación de Node.js](https://nodejs.org/api/http.html#requestreusedsocket). Las conexiones inactivas se retiran después de un segundo. Si una lectura o una renovación falla específicamente al reutilizar un socket cerrado, se permite un único intento con una conexión nueva. La renovación usa la misma sesión; el servidor conserva su validación de propiedad y vencimiento. No se reenvían automáticamente activaciones, pulsos, adquisiciones ni otras escrituras.
- El cliente esperaba la respuesta de cada renovación antes de enviar otra. Ahora admite como máximo dos renovaciones pendientes, cada una con plazo de 600 ms, y exige confirmaciones recientes. Una respuesta tardía de una sesión ya terminada no puede suspender una sesión nueva.
- Cada evento de movimiento podía iniciar otra consulta de historial. Ahora se mantiene una sola consulta por contexto y se agrupan los eventos recibidos mientras termina, conservando una actualización posterior.
- Las oscilaciones analógicas junto al umbral podían generar cambios repetidos de entrada. La zona muerta configurada siempre libera el movimiento; entrar requiere un pequeño margen adicional, del 20 % de la zona hasta un máximo de 0,05. Así, con zona 0,25 se activa al superar 0,30 y se libera al volver a 0,25. Una inversión completa de dirección sigue procesándose inmediatamente.

El watchdog del ESP8266 continúa en **800 ms** y la sesión de la API en **900 ms**. No se reanuda la conducción sola después de perder la comunicación. Un fallo real al enviar una activación conserva el error y solicita liberar. Los errores 502 incluyen `codigo_red` en la respuesta registrada en Actividad para distinguir conexión reiniciada, puerto rechazado y tiempo agotado.

La configuración del mando no se cambia ni se restablece. El exe conserva su dirección de servidor y sus asignaciones habituales; solicita de nuevo el token al abrirse.

## Validación

- **140 pruebas automatizadas:** 102 Python, 18 del controlador de entradas, 5 de renovación y 15 del adaptador de escritorio.
- Pruebas con la lectura real de Gamepad API y un mando simulado, tanto en el navegador como en el exe empaquetado: giro izquierdo sin ráfagas, 20 eventos con historial lento y renovaciones retrasadas, liberación dentro de la zona muerta y toma serial.
- Recorrido del exe con autenticación, catálogo, administración, conducción, pulsos, preferencias, cierre seguro y reapertura. El paquete ASAR contiene solo recursos públicos de la aplicación, sin configuración privada ni herramientas de desarrollo.

Se consultó EC2 únicamente para confirmar la versión y el catálogo/estado: la API devolvía 1.6.2; el giro izquierdo era el código 10, activo y sin duplicados; la placa aparecía en WiFi sin error de registro RDS en esa consulta. No se enviaron órdenes al carro real. Las pruebas reproducen defectos del software; no demuestran que todos los cortes reales tengan ese origen.

## Probar en Windows

1. Cierra las versiones anteriores del programa.
2. Abre `Vehiculo-IoT-1.6.3-Windows-x64.exe`, usa tu servidor/token habituales y conecta el mando.
3. Selecciona WiFi, deja el mando en neutro y activa la conducción. Comprueba el giro izquierdo y la liberación.

La API 1.6.2 actual es compatible. Para aplicar también las mejoras del panel web, sustituye en EC2 la carpeta `app` con la del ZIP `Actualizacion-conexion-1.6.3.zip`, conservando `.env`, certificados, entorno virtual y base de datos. Reinicia Uvicorn con un proceso:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Comprueba 1.6.3 en `/docs` y recarga con Ctrl+F5. No cambian las dependencias Python ni el firmware.

Si vuelve a fallar, anota el `codigo_red` de la respuesta 502 en Actividad y ejecuta `ESTADO` en Termite: indica si perdió WiFi, API o solo la sesión del panel. Ese dato permite distinguir el tramo PC–EC2 del tramo EC2–ESP8266.
