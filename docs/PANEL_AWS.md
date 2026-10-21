# Abrir el panel desde EC2 Windows

El panel se sirve desde la misma aplicación FastAPI en **/panel/**. No requiere otro servidor, más dependencias ni un puerto nuevo. Las rutas originales para Postman y `/docs` se conservan. El navegador envía las peticiones al mismo servidor y se conecta al canal autenticado `/panel/ws/vehiculos/{id}`.

## Actualizar la instancia que ya funciona

1. Copia `actualizacion-panel-aws.zip` a **C:\Apps\actualizacion-panel-aws.zip** dentro de Windows Server. Puedes usar la transferencia de archivos de tu cliente de Escritorio remoto. No es necesario subir `.env`, certificados ni la carpeta `.venv`.
2. Detén la API con **Ctrl+C** en la consola donde está funcionando. Si la inicia una tarea programada, detén esa tarea y espera a que libere el puerto 8000.
3. Abre PowerShell y ejecuta lo siguiente. Si tu proyecto se encuentra en otra ruta, sustituye `C:\Apps\api-vehiculo-iot` por su carpeta real.

```powershell
Set-Location C:\Apps\api-vehiculo-iot
Copy-Item -LiteralPath .\app -Destination (".\app-respaldo-panel-" + (Get-Date -Format "yyyyMMdd-HHmmss")) -Recurse
Expand-Archive -LiteralPath C:\Apps\actualizacion-panel-aws.zip -DestinationPath . -Force
```

La copia guarda un respaldo del código previo. El ZIP actualiza únicamente los siete archivos de aplicación indicados más abajo y añade esta guía. No incluye `.env`, credenciales, certificados, bases de datos ni entornos virtuales. No reinstales dependencias ni regeneres el token.

4. Inicia la API como antes:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Si ya utilizabas el Programador de tareas, vuelve a ejecutar esa tarea en lugar de iniciar otro proceso manual; sus argumentos no cambian. Mantén un solo proceso.

5. Comprueba primero dentro de Windows Server:

```text
http://127.0.0.1:8000/panel/
```

6. Desde tu computadora abre:

```text
http://3.233.212.203:8000/panel/
```

Pulsa **Conectar API** e introduce el CONTROL_TOKEN de EC2 que ya usas en Postman. No es la contraseña de RDS. Selecciona el vehículo; deben cargar su catálogo, estado e historial, y el indicador WebSocket debe mostrar conexión.

## Comprobación de la entrega

- Abre `/docs` para confirmar que Postman y la documentación siguen disponibles.
- Prueba un movimiento con un comando del catálogo y verifica el historial.
- Inicia una DEMO y comprueba los eventos y su finalización; el historial debe mantenerse.
- Si ya tienes arranque automático, verifica el panel después de reiniciar la instancia. El panel arranca con el mismo proceso que la API.

Se mantiene la conectividad HTTP/WS que ya usabas en el puerto 8000. No se cambian reglas de red de AWS. Si funciona `/docs` desde tu computadora, el panel utiliza ese mismo acceso. Para acceso cifrado HTTPS/WSS se necesita configurar TLS; esta actualización no lo configura.

## Si algo falla

- **404 en /panel/**: verifica que el ZIP se extrajo en la raíz correcta y que reiniciaste el proceso. Debe existir `C:\Apps\api-vehiculo-iot\app\api\panel_routes.py`.
- **No carga el diseño**: vuelve a extraer el ZIP completo. Deben existir `app\panel\index.html`, `panel.css` y `panel.js`. Recarga con Ctrl+F5.
- **401**: usa el CONTROL_TOKEN de EC2, no el del entorno local si son distintos.
- **503**: revisa RDS y ejecuta el diagnóstico habitual `scripts\diagnosticar_mysql.py` con el Python de `.venv`.
- **No conecta desde fuera, pero sí en Windows**: revisa las reglas que ya permitían tu IP en el puerto 8000 y el firewall de Windows.

## Archivos actualizados

```text
app/main.py
app/api/panel_routes.py
app/services/vehicle_service.py
app/websocket/manager.py
app/panel/index.html
app/panel/panel.css
app/panel/panel.js
```

La autenticación de Postman y su WebSocket original permanecen disponibles. El canal del panel valida el token y exige el mismo origen antes de suscribirse a los mismos eventos.

## Validación local

El 20 de octubre de 2026 aprobaron **54 pruebas automatizadas** con repositorios/base simulados, incluidas cuatro del panel: archivos y rutas, autenticación/origen, eventos compartidos con Postman y fin de DEMO sin historial adicional. También se comprobó la sintaxis del JavaScript. Estas comprobaciones no despliegan archivos en EC2 ni sustituyen la prueba con el token y la base de datos reales del servidor.
