# Validación — Actividad 2.5, integración de los 21 SP

## Versión 1.4 — 21 de octubre de 2026

El estudiante confirmó que la API ya demostró su funcionamiento en Amazon EC2 con Windows Server y MySQL en Amazon RDS. Este resultado actualiza el estado de AWS que aparecía como pendiente en los registros históricos siguientes. No implica confirmación de ejecución física del ESP8266 ni una nueva comprobación del certificado real de RDS durante esta revisión.

La entrega incorpora el panel web en `/panel/`, sus archivos HTML/CSS/JavaScript y el canal autenticado `/panel/ws/vehiculos/{id_vehiculo}`. Comparte servicios y eventos con Postman. OpenAPI identifica la aplicación como `1.4.0` y la versión del repositorio es `v1.4`.

Se ejecutó `python -m unittest discover -v` desde `.venv-lab`, con Python 3.12.3: **54 pruebas aprobadas**. Las cuatro pruebas nuevas del panel verifican archivos/rutas y contrato existente, autenticación/origen/vehículo, eventos compartidos con Postman y finalización de DEMO sin añadir historial. Se mantienen las pruebas de administración, transacciones, coordinación y configuración TLS.

Estas pruebas usan repositorios y SP simulados; no se conectan a AWS ni a MySQL real. La confirmación del funcionamiento en AWS procede de la demostración del estudiante. Starlette sigue emitiendo el aviso de deprecación del cliente de pruebas, sin fallos en la suite.

## Registro histórico de la validación inicial

Fecha: 14 de octubre de 2026. Versión de aplicación: 0.2.0.

## Alcance

Se revisaron las instrucciones disponibles en el chat **Actividad 2.5 APIs IoT Dev Activity**, los 52 parámetros de `esport-parametros.csv` y los 21 cuerpos de `esport-comportamiento-parametros.csv` proporcionados por el estudiante. Se conservaron como contrato en `docs/sp_parametros.csv` y `docs/sp_definiciones.csv`.

Se agregaron las 13 operaciones pendientes y cinco consultas auxiliares bajo `/admin`. Swagger expone 22 operaciones HTTP en total, además del WebSocket. Se conservaron las rutas y la colección original de los tres escenarios de entrega.

## Pruebas automatizadas

**46 pruebas aprobadas** con `python -m unittest discover -v`, ejecutadas desde el entorno de verificación `.venv-lab` con Python 3.12.3. El entorno `.venv` del estudiante ya funciona en su terminal y es el indicado para ejecutar el proyecto; no se sustituyó ni modificó.

- Las 29 pruebas anteriores siguen aprobadas: movimiento, historial, dos clientes WebSocket, aislamiento, desconexiones, transacciones y cancelación DEMO durante espera o SQL.
- Se agregaron 14 pruebas de administración: CRUD completo, pertenencia de recursos, inactivos/reactivación, código y orden duplicados, límites Pydantic, autenticación de las 18 rutas admin, bloqueo durante DEMO, integridad MySQL simulada, fallo de commit y cierre de WebSocket únicamente tras eliminar su vehículo con éxito.
- Se agregaron tres pruebas del diagnóstico: los 21 contratos y seis motores, existencia del procedimiento sin parámetros y detección de cambios de tipos.
- La prueba de integración completa invoca exactamente los **21 nombres de SP** contra un simulador, enlaza las firmas de los CSV y verifica que CRUD/DEMO no escriben historial. Recupera el ID de movimiento en la misma conexión mediante LAST_INSERT_ID().

Las pruebas usan credenciales ficticias y un servidor de SP simulado; no se conectan a MySQL real. La versión de Starlette emite un aviso de deprecación sobre httpx que no impide ejecutar la suite.

## Colecciones Postman

- `actividad_2_5.postman_collection.json` permanece sin cambios: seis solicitudes HTTP que apoyan los tres escenarios originales y la cancelación auxiliar; los WebSocket se conectan manualmente.
- `administracion_2_5.postman_collection.json` contiene 18 solicitudes auxiliares. Se ejecutó su flujo completo contra la aplicación y SP simulados, incluyendo sus scripts JavaScript de variables y pruebas: cuatro respuestas 201, diez respuestas 200 y cuatro respuestas 204.
- Se comprobó que los IDs se capturan al crear registros, que las solicitudes dependientes rechazan IDs vacíos y que la limpieza devuelve los datos simulados a su estado inicial. No hay IDs predeterminados del vehículo real para las escrituras administrativas.
- Ambas colecciones son JSON válido y corresponden a los métodos/rutas de OpenAPI. Los tokens exportados están vacíos.

## Arranque real de Uvicorn

Se inició temporalmente la aplicación real en un puerto efímero de **127.0.0.1**, sin interrumpir una posible instancia del estudiante en 8000. Se impuso contraseña MySQL vacía y un token temporal en el proceso de comprobación para impedir conexiones/escrituras reales:

| Comprobación | Resultado |
| --- | --- |
| Swagger | 200 |
| OpenAPI | 22 operaciones HTTP |
| Las 18 operaciones admin sin token | 401 |
| POST admin con token y datos inválidos | 422 |
| POST admin válido con contraseña MySQL ausente | 503 controlado, sin conexión SQL |

El servidor temporal terminó al finalizar. No quedó un servidor de comprobación en ejecución.

## Lo que requiere MySQL real

El 16 de octubre de 2026, el estudiante confirmó que **todas las pruebas locales funcionaron**, incluidas las de administración en Postman. Esta validación contra MySQL real fue realizada por el estudiante; el agente no ejecutó altas, actualizaciones ni eliminaciones reales durante las comprobaciones automatizadas.

El diagnóstico actualizado consulta las 21 firmas con sus tipos, los motores InnoDB de las seis tablas, la clave única del estado, posibles COMMIT internos y las reglas reales ON DELETE/ON UPDATE. Se probó con metadatos simulados; debe ejecutarse personalmente con la configuración local para confirmar su esquema vigente.

Los cuatro SP de eliminación ejecutan DELETE físico. Los CSV no describen llaves foráneas ni triggers, por lo que no se afirma que la base real use CASCADE o RESTRICT. La API respeta sus reglas existentes y traduce errores de integridad sin exponer mensajes del driver. La colección auxiliar crea registros LAB_API_2_5 y limpia únicamente sus IDs, en orden paso → DEMO → comando → vehículo.

```bash
source .venv/bin/activate
python scripts/diagnosticar_mysql.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Consulta `docs/ADMINISTRACION.md` antes de ejecutar la colección auxiliar. Los tres escenarios originales documentan la validación inicial del control; el CRUD completa la comprobación del conjunto. Según la aclaración del alcance final, estas mismas APIs se ejecutarán en EC2 y se conectarán a RDS después de validar su funcionamiento local. Ese despliegue sigue pendiente. La aceptación de Postman en lugar de Thunder Client sigue pendiente del profesor.

No se cambió el esquema ni se leyeron/imprimieron contraseñas en las salidas. No se modificó `.env`, no se crearon recursos AWS ni se desplegó la API públicamente.

## Preparación para EC2 Windows y RDS — 16 de octubre de 2026

El estudiante confirmó Windows Server y RDS ya preparado. Se añadió `MYSQL_SSL_CA`: cuando tiene valor, exige validar el certificado y la identidad del servidor; una ruta relativa se resuelve desde la raíz del proyecto. La variable vacía conserva las opciones del laboratorio local. No se reintenta sin verificación si el driver rechaza TLS.

Se agregaron cuatro pruebas para compatibilidad local, resolución de la ruta y opciones de verificación, bloqueo por CA inexistente y rechazo TLS sin reintento ni exposición del error privado. **Las 50 pruebas automatizadas pasaron** con MySQL simulado. No se ha validado todavía el certificado real de RDS ni ejecutado la aplicación en Windows.

La guía `docs/AWS_WINDOWS.md` documenta instalación, configuración privada, certificado oficial, conectividad, arranque, pruebas remotas y ejecución persistente. Estos cambios de preparación permanecen locales hasta publicarlos; las etiquetas `v1.1` y `v1.2` se conservan. El despliegue y su validación siguen pendientes.
