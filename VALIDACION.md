# Verificación — 14 de octubre de 2026

Se implementó la primera etapa de la actividad 2.5 directamente en `api_vehiculo_iot`. El entorno original `.venv` se conservó; su intérprete disponible es Python 3.12.3 y sus paquetes existentes están en una carpeta de Python 3.13, por lo que no son importables desde ese ejecutable. Se preparó `.venv-lab` separado para el laboratorio.

## Resultado automatizado

**29 pruebas aprobadas**, con `python -m unittest discover -v`, usando dobles de la base de datos. Se ejecutaron primero en un entorno temporal Python 3.12.14 y después en el entorno persistente `.venv-lab` con Python 3.12.3: ambos aprobaron las 29. En `.venv-lab`, `python -m pip check` no encontró dependencias incompatibles y la aplicación se importó correctamente. Se comprobaron:

- HTTP: autenticación de controles, validación Pydantic, máximo de diez registros, Swagger/OpenAPI y respuesta segura cuando falta la contraseña.
- WebSocket: estado inicial, dos clientes en una sala, aislamiento entre vehículos y limpieza de desconexiones.
- Repositorio: argumentos enlazados, cierre de cursores/conexión, conservación de `conectado`, escritura de ambos SP en la misma transacción, rollback al fallar historial o commit y rechazo de vehículo/comando inactivo o ajeno.
- DEMO: lectura de una secuencia variable desde el repositorio de SP, ordenación, código independiente del ID, rechazo de duración negativa/orden repetido/DEMO inactiva o ajena, exclusión por vehículo y dos vehículos independientes.
- Cancelación: interrupción de una espera larga; señal prioritaria mientras SQL simulado sigue en otro hilo; espera de su conclusión sin emitir el paso pendiente ni iniciar otro.
- Historial: ninguna llamada de registro durante DEMO; comparación del historial antes/después al finalizar; errores sin eventos de éxito.

La versión instalada de Starlette emite un aviso de futura sustitución de `httpx` en su cliente de pruebas. No impidió la ejecución de las pruebas.

## Servidor real local

Se inició temporalmente Uvicorn con la aplicación real en **127.0.0.1:8000**, con un proceso, y se comprobó:

| Petición | Resultado observado |
| --- | --- |
| `GET /docs` | `200` |
| `GET /openapi.json` | `200`; cuatro rutas HTTP |
| `GET /vehiculos/1/historial` sin contraseña MySQL configurada | `503` controlado |
| POST de movimiento sin token | `401` |
| POST de DEMO sin token | `401` |
| DELETE de DEMO sin token | `401` |
| Conexión WebSocket sin token | Handshake rechazado, HTTP `403` |

El servidor temporal se detuvo al terminar. No quedó una instancia escuchando como parte de esta verificación.

También se comprobó compilación de los módulos, sintaxis JSON de la colección Postman, sustitución de IDs como números y token exportado vacío. Git ignora `.env`, ambos entornos virtuales y cachés. `.env` tiene permisos `600`; se generó el token sin imprimirlo y se dejó la contraseña vacía.

## Pendiente de MySQL y evidencia real

**No se verificaron los SP ni sus transacciones contra tu MySQL.** No se usaron credenciales de otros archivos. El diagnóstico detectó la contraseña pendiente y terminó antes de abrir una conexión. No se modificaron esquema ni datos existentes.

Introduce personalmente la contraseña y ejecuta:

```bash
source .venv-lab/bin/activate
python scripts/configurar_password.py
python scripts/diagnosticar_mysql.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

El diagnóstico verifica las ocho firmas, motores InnoDB, clave única del estado, ausencia de control transaccional interno en los dos SP de escritura y lectura del vehículo/DEMO. Sus resultados reales y las capturas de los tres escenarios del README quedan pendientes. Las pruebas con dobles no sustituyen esa evidencia.

Postman contiene tres escenarios, con sesión WebSocket manual y comprobación de historial antes/después. La guía pide Thunder Client; sigue pendiente que el profesor autorice sustituirlo por Postman.

No se publicó la API ni se subió el proyecto a GitHub. Los trece SP restantes no se implementaron sin conocer sus parámetros reales.
