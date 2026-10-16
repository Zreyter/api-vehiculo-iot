# Ejecutar la API en EC2 Windows Server con RDS

Las pruebas locales de control y administración fueron confirmadas por el estudiante el 16 de octubre de 2026. Esta guía usa la instancia Windows Server y el RDS existentes. No crea recursos ni modifica automáticamente AWS.

## 1. Llevar el código actualizado a la instancia

La preparación de TLS está en los cambios locales posteriores a `v1.2`. Publicar esos cambios antes de clonar o actualizar en EC2; conservar las etiquetas existentes. No copiar `.venv` ni el `.env` de Linux a Windows.

Acceder a EC2 mediante Escritorio remoto. Instalar Python 3.13 y Git si todavía no están disponibles. Abrir PowerShell y comprobar:

```powershell
py -3.13 --version
git --version
```

Para una instalación nueva:

```powershell
New-Item -ItemType Directory -Force C:\Apps
Set-Location C:\Apps
git clone https://github.com/Zreyter/api-vehiculo-iot.git
Set-Location C:\Apps\api-vehiculo-iot
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Si el repositorio privado solicita acceso, autenticar Git personalmente. Si ya existe la carpeta, entrar en ella y usar `git pull --ff-only` después de revisar posibles cambios propios. Ejecutar los comandos restantes desde `C:\Apps\api-vehiculo-iot`; adaptar las rutas si se eligió otra ubicación.

Se invoca directamente el Python del entorno, por lo que no hace falta cambiar la política de ejecución de PowerShell para activarlo. Véase [entornos virtuales de Python](https://docs.python.org/3.13/library/venv.html).

## 2. Configurar RDS y el token en Windows

Descargar el paquete CA desde la fuente oficial de AWS:

```powershell
New-Item -ItemType Directory -Force certs
Invoke-WebRequest -Uri "https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem" -OutFile "certs\global-bundle.pem"
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

La configuración de la instancia debe tener estos valores, reemplazando los ejemplos:

```dotenv
MYSQL_HOST=ENDPOINT_DNS_DE_TU_RDS
MYSQL_PORT=3306
MYSQL_USER=USUARIO_DE_TU_RDS
MYSQL_PASSWORD=
MYSQL_DATABASE=vehiculo_iot
MYSQL_SSL_CA=certs/global-bundle.pem
CONTROL_TOKEN=
```

`MYSQL_HOST` lleva solamente el endpoint DNS mostrado en RDS, sin protocolo, puerto ni ruta. La base debe contener las seis tablas y los 21 SP de la versión probada. No reemplazar la configuración local de tu computadora.

Configurar personalmente la contraseña y generar un token nuevo sin mostrarlo:

```powershell
.\.venv\Scripts\python.exe scripts\configurar_password.py
.\.venv\Scripts\python.exe -c "import secrets; from dotenv import set_key; set_key('.env', 'CONTROL_TOKEN', secrets.token_urlsafe(32))"
```

El segundo comando cambia el token; usar el nuevo valor en Postman. Restringir los permisos del archivo `.env` a la cuenta que ejecutará la API y a los administradores autorizados.

Con `MYSQL_SSL_CA`, la aplicación exige verificar el certificado y el nombre del servidor. Un certificado rechazado impide conectar; no hay reintento sin verificación. Referencias: [certificados de RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html) y [opciones TLS de Connector/Python](https://dev.mysql.com/doc/connector-python/en/connector-python-connectargs.html).

## 3. Revisar la red

- EC2 y RDS: comprobar que están en la VPC prevista y que existe conectividad entre sus subredes.
- Grupo de seguridad de RDS: permitir TCP 3306 desde el **grupo de seguridad de EC2**. Usar el puerto real si se cambió el predeterminado.
- EC2: permitir salida hacia RDS en ese puerto.
- Para la prueba directa de la API: permitir TCP 8000 en el grupo de seguridad de EC2 únicamente desde la IP pública actual del cliente de pruebas.
- Firewall de Windows: permitir también TCP 8000 desde esa misma IP. Se puede crear una regla de entrada personalizada desde “Firewall de Windows Defender con seguridad avanzada”.

Mantener RDS accesible para EC2; Postman se conecta a la API y no necesita acceso directo al puerto MySQL. Referencia: [EC2 y RDS en una VPC](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_VPC.Scenarios.html).

## 4. Comprobar la conexión y arrancar

Desde PowerShell en EC2:

```powershell
Test-NetConnection -ComputerName "ENDPOINT_DNS_DE_TU_RDS" -Port 3306
.\.venv\Scripts\python.exe scripts\diagnosticar_mysql.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

La primera comprobación valida alcance TCP; el diagnóstico valida acceso MySQL, contratos y esquema. Si falta un SP, tabla o permiso, corregir RDS antes de probar escrituras. Una respuesta de Swagger por sí sola no demuestra conexión a RDS.

En el navegador de la propia instancia: `http://127.0.0.1:8000/docs`. Mantener esta consola abierta durante la primera prueba. No usar `--reload` ni más de un worker.

## 5. Probar desde Postman

Duplicar el entorno local con un nombre como `AWS EC2` y configurar:

- `base_url`: `http://IP_PUBLICA_ACTUAL_DE_EC2:8000` para la prueba restringida a tu IP.
- `control_token`: el token generado en el `.env` de EC2.
- WebSocket manual: `ws://IP_PUBLICA_ACTUAL_DE_EC2:8000/ws/vehiculos/1`, con encabezado `Authorization: Bearer TU_TOKEN` y un ID de vehículo existente en RDS.

Ejecutar los escenarios de movimiento, historial y DEMO; comprobar ambos clientes WebSocket, cancelación e historial sin cambios en DEMO. Después ejecutar administración A → B → C → D para crear y limpiar datos de prueba en RDS. Guardar evidencias sin secretos.

HTTP/WS es la comprobación inicial con acceso limitado. Antes de ampliar el acceso, configurar un punto de entrada HTTPS/WSS con certificado válido y soporte WebSocket, mantener el backend restringido y actualizar las URLs de Postman. La consulta de historial actualmente no exige token: su acceso también depende de esas restricciones de red.

## 6. Dejar la API funcionando después de cerrar RDP

Una consola abierta no es la instalación persistente. Tras validar la conexión y las pruebas, crear una tarea en el **Programador de tareas de Windows**:

- General: ejecutar con una cuenta dedicada que pueda leer el proyecto, el entorno, `.env` y el certificado. Seleccionar ejecutar tanto si el usuario inició sesión como si no. Introducir personalmente las credenciales de Windows cuando el sistema las solicite; no ponerlas en scripts.
- Desencadenador: al iniciar el sistema, con un retraso para permitir que esté disponible la red.
- Acción / programa: `C:\Apps\api-vehiculo-iot\.venv\Scripts\python.exe`.
- Acción / argumentos: `-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`.
- Acción / iniciar en: `C:\Apps\api-vehiculo-iot`.
- Configuración: reiniciar ante fallo, no detener por límite de duración y no iniciar otra instancia si ya está ejecutándose.

Detener el arranque manual con Ctrl+C antes de iniciar la tarea, para evitar conflicto por el puerto. Validar que la tarea arranca, cerrar la sesión RDP y repetir una consulta desde Postman; comprobar también el arranque tras reiniciar EC2. El usuario de ejecución debe tener acceso al Python base con el que se creó `.venv`. Referencia: [tareas programadas en Windows Server](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/schtasks-create).

## Estado de la entrega

El despliegue se considera comprobado cuando funcionan HTTP y WebSocket desde el cliente, las lecturas/escrituras corresponden a RDS, la ejecución persiste sin RDP y está configurado el acceso HTTPS/WSS previsto. Documentar el endpoint, la versión desplegada y las evidencias; no publicar `.env`, claves privadas ni credenciales.
