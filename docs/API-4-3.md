# Contrato HTTP y WebSocket · Práctica 4.3

**Referencia verificada el 20 de noviembre de 2026.** La revisión anterior a 4.3 (`83c3df1`) expone 29 operaciones HTTP. La revisión publicada (`3feafb3`) conserva esas 29 y añade 22, para un total de 51. El número 21 corresponde a los procedimientos almacenados de MySQL. Algunas operaciones usan varios procedimientos y otras, como el latido WebSocket, funcionan sin ellos. [Firmas y definiciones de los 21 procedimientos](PROCEDIMIENTOS.md) · [Swagger publicado](https://cape-landside-tidy.ngrok-free.dev/docs) · [OpenAPI JSON](https://cape-landside-tidy.ngrok-free.dev/openapi.json)

Se cotejó el inventario método por método con el OpenAPI de la revisión histórica, el código actual y el OpenAPI publicado en AWS. El JSON de los ejemplos usa datos ficticios y los campos implementados. Los ejemplos de `POST`, `PUT` y `DELETE` son para una base de ensayo. [Migraciones, recuperación y pruebas](PRACTICA-4-3.md)

## Cómo leer las fichas

- **A** es una sesión comercial `admin`. **U** es una sesión `usuario` con propiedad vigente de la unidad de la ruta. **U general** requiere comprador activo y sesión válida, sin comprobar una unidad. **A/U editor** administra demos de fábrica con A y demos propias con U. La lectura de pasos sigue la visibilidad de la demo.
- **Público** permite la petición sin sesión. En 4.1/4.2 las rutas protegidas usaban `CONTROL_TOKEN` y el historial era público. Las tablas muestran los permisos de **4.3 publicada**.
- Para **A** y **U** enviar `Authorization: Bearer <token_de_sesión>`. La sesión se obtiene en `/comercial/acceso` y vence al cabo de una hora. Enviar `Content-Type: application/json` cuando haya cuerpo. Desde ngrok se puede usar `ngrok-skip-browser-warning: 1`.
- Los parámetros abreviados en las tablas son `{v}` = `id_vehiculo`, `{c}` = `id_comando`, `{d}` = `id_demo`, `{p}` = `id_demo_movimiento`, `{m}` = `id_modelo` y `{u}` = `id_usuario`. En el editor comercial y en exhibición, OpenAPI usa `{unidad}` y `{demo}`. Cada ID es un entero positivo. Los ID creados para el modelo comercial y para el vehículo físico son independientes.
- En las tablas, `—` indica ausencia de cuerpo o validación adicional. `[]` significa lista vacía y `204` indica una respuesta sin cuerpo. `RDS` identifica una operación que consulta o escribe MySQL.

| Código | Cuándo puede aparecer |
| --- | --- |
| `401` | Credencial ausente, inválida o vencida. Se aplica a las rutas protegidas |
| `403` | Rol insuficiente, unidad ajena o demo privada fuera de alcance. Las tablas indican el permiso por ruta |
| `404` | Recurso inexistente o no incluido bajo el padre indicado. En el editor, también puede ocultar los pasos privados de otra cuenta |
| `409` | Conflicto de estado, de unicidad, de propiedad, de referencia o de control ocupado, según la ruta |
| `422` | Cuerpo, ID o parámetro inválido. También se usa en algunas validaciones de negocio |
| `503` | RDS o una dependencia requerida no está disponible. En `/salud`, un fallo de MySQL se informa dentro del JSON |

Los errores de negocio devuelven, por ejemplo, `{"detail":"Vehículo inexistente."}`. FastAPI suele devolver un arreglo en `detail` para errores de validación. Las rutas `/comercial/` usan un mensaje genérico para el `422` de esquema y así evitan devolver contraseñas del cuerpo.

## 29 operaciones HTTP anteriores a 4.3

### Vehículos, comandos y estado bajo `/admin`

Las lecturas operativas de ficha, estado, comandos, demos y pasos bajo `/admin` **requieren el permiso U**. Las mutaciones de catálogos y el listado global requieren A.

| Nº | Método y ruta | Entrada | Permiso | Éxito | Validaciones específicas | Uso |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `GET /admin/vehiculos` | — | A | 200 · [Vehículo] | Incluye activos e inactivos | Catálogo técnico. El inventario de Administración usa `/comercial/unidades` |
| 2 | `GET /admin/vehiculos/{v}` | v | U | 200 · Vehículo | 404 si no existe | Nombre y datos de la unidad en Control |
| 3 | `POST /admin/vehiculos` | Vehículo alta | A | 201 · Vehículo | 422 para campos inválidos | Catálogo técnico. El alta comercial usa `/comercial/unidades` |
| 4 | `PUT /admin/vehiculos/{v}` | v + Vehículo edición | A | 200 · Vehículo | 404 inexistente. 409 si intenta desactivar una unidad asignada o está en operación | Mantenimiento técnico |
| 5 | `DELETE /admin/vehiculos/{v}` | v | A | 204 en modo legado | 409 en modo comercial. Utilizar baja lógica desde Administración | Operación heredada |
| 6 | `GET /admin/vehiculos/{v}/estado` | v | U | 200 · Estado o null | 404 inexistente. null si no hay estado persistido | Monitoreo al consultar o reconectar |
| 7 | `GET /admin/vehiculos/{v}/comandos` | v | U | 200 · [Comando] | 404 inexistente. La lista incluye activos e inactivos | Control habilita comandos vigentes |
| 8 | `POST /admin/vehiculos/{v}/comandos` | v + Comando alta | A | 201 · Comando | 404 unidad inexistente. 409 por código o nombre duplicado o control ocupado | Mantenimiento técnico |
| 9 | `PUT /admin/vehiculos/{v}/comandos/{c}` | v, c + Comando edición | A | 200 · Comando | 404 comando fuera de la unidad. 409 por duplicado o control ocupado | Mantenimiento técnico |
| 10 | `DELETE /admin/vehiculos/{v}/comandos/{c}` | v, c | A | 204 | 404 relación inexistente. 409 por referencias o control ocupado | Mantenimiento de catálogo |
| 11 | `GET /admin/vehiculos/{v}/demos` | v | U | 200 · [Demo] | 404 unidad inexistente. Filtra demos privadas ajenas | Selector de demos de Control |
| 12 | `POST /admin/vehiculos/{v}/demos` | v + Demo alta | A | 201 · Demo | 404 unidad inexistente. 409 si está en operación | Catálogo técnico de fábrica. Crea la ficha |
| 13 | `PUT /admin/vehiculos/{v}/demos/{d}` | v, d + Demo edición | A | 200 · Demo | 403 demo privada. 404 demo fuera de unidad. 409 si está en operación | Mantenimiento de fábrica |
| 14 | `DELETE /admin/vehiculos/{v}/demos/{d}` | v, d | A | 204 | 403 demo privada. 404 demo fuera de unidad. 409 si está en operación o tiene referencias | Elimina la definición de fábrica en el catálogo técnico |
| 15 | `GET /admin/vehiculos/{v}/demos/{d}/movimientos` | v, d | U | 200 · [Paso legado] | 403 demo privada ajena. 404 demo fuera de la unidad | Consulta técnica de pasos |
| 16 | `POST /admin/vehiculos/{v}/demos/{d}/movimientos` | v, d + Paso legado entrada | A | 201 · Paso legado | 403 demo privada. 404 demo o comando fuera de unidad. 409 orden duplicado u operación activa | Agrega un paso de fábrica |
| 17 | `PUT /admin/vehiculos/{v}/demos/{d}/movimientos/{p}` | v, d, p + Paso legado entrada | A | 200 · Paso legado | 403 demo privada. 404 paso, demo o comando fuera de su padre. 409 orden duplicado u operación activa | Edita un paso de fábrica |
| 18 | `DELETE /admin/vehiculos/{v}/demos/{d}/movimientos/{p}` | v, d, p | A | 204 | 403 demo privada. 404 paso ajeno a demo. 409 si está en operación | Elimina un paso de fábrica |

Estas rutas técnicas validan `activo` como entero `0` o `1`. Sus altas dejan el valor inicial de `activo` a MySQL. `codigo` e `id_comando` representan conceptos distintos. Los pasos legados reciben `orden` entero positivo y tiempos enteros no negativos. El ejecutor físico aplica límites adicionales.

### Control, movimientos, conexión de la placa y voz

| Nº | Método y ruta | Entrada | Permiso | Éxito | Validaciones específicas | Uso |
| --- | --- | --- | --- | --- | --- | --- |
| 19 | `POST /vehiculos/{v}/movimientos` | v + Movimiento individual | U | 200 · Evento `movimiento_individual` | 404 unidad inexistente. 409 ocupada o inactiva. 422 comando inválido, inactivo o ajeno | Registro individual desde Control. Confirma estado e historial en RDS |
| 20 | `GET /vehiculos/{v}/historial` | v + `limite` de 1 a 10, por defecto 10 | U | 200 · [Historial] | 404 unidad inexistente. 409 inactiva | Monitoreo reconcilia registros ordenados por `fecha_hora` e ID en orden descendente |
| 21 | `POST /vehiculos/{v}/demos` | v + Iniciar demo | U | 202 · Evento `demo_iniciada` | 403 privada ajena. 404 inexistente. 409 ocupada, inactiva o placa no preparada en modo físico. 422 secuencia no válida | Acepta ejecutar la secuencia. El progreso llega por WSS |
| 22 | `DELETE /vehiculos/{v}/demos/activa` | v | U | 200 · Evento `demo_cancelada` | 409 sin ejecución activa. 503 si finaliza con error de ejecución | Interrumpe la duración o pausa y solicita liberar las salidas en modo físico |
| 23 | `POST /vehiculos/{v}/demos/activa/latido` | v + Latido demo | U | 200 · Vencimiento | 409 ejecución física inexistente, vencida o con identificador distinto | Renueva la demo física iniciada por HTTP |
| 24 | `GET /vehiculos/{v}/dispositivo` | v | U | 200 · Dispositivo | — | Estado de conexión del ESP8266 en memoria. `listo` exige modo WiFi |
| 25 | `POST /vehiculos/{v}/control` | v | U | 200 · Permiso temporal de control | 409 ocupada, placa sin WiFi o permiso bloqueado. 503 error al preparar la placa o RDS | Adquiere la sesión física por HTTP |
| 26 | `PUT /vehiculos/{v}/control` | v + Permiso temporal entrada | U | 200 · Vencimiento | 409 vencimiento, permiso ajeno o placa no lista. 503 fallo de comunicación | Renueva el permiso temporal |
| 27 | `POST /vehiculos/{v}/control/orden` | v + Orden física | U | 200 · Resultado de orden | 409 permiso inválido o placa rechaza. 422 código o pulso inválido. 503 fallo de comunicación | Envía una orden mediante el permiso HTTP |
| 28 | `DELETE /vehiculos/{v}/control` | v + Permiso temporal entrada opcional | U | 200 · Resultado de parada | 409 si el permiso indicado pertenece a otro controlador activo | Solicita parada y libera el permiso. Sin cuerpo, actúa como parada de emergencia de esa unidad |
| 29 | `POST /ia/plan` | Frase de voz | U general | 200 · Plan de voz | 422 frase o plan inviable. 502 proveedor. 503 sin configuración o cuota. 504 tiempo de espera | Kiwi propone pasos. El mando decide cómo enviarlos |

El movimiento de registro confirma la escritura y publica el evento. `ejecucion_fisica_confirmada` permanece en `false`. Una DEMO actualiza el estado y transmite los pasos con sus tiempos, sin insertar esos pasos en el historial individual. La ejecución REST física usa un latido de 900 ms. Para comprobar la integración sin activar la placa, la prueba de laboratorio usa `modo: "registro"`.

## 22 operaciones incorporadas en 4.3

Los listados administrativos de unidades, modelos, clientes y auditoría aceptan `buscar` (máximo 80 caracteres), `inicio` (desplazamiento con valor inicial 0) y `limite` (1 a 100 con valor inicial 50). `buscar` filtra nombre/modelo de unidad, nombre de modelo, nombre/correo de cliente o acción/recurso de auditoría, según corresponda.

| Nº | Método y ruta | Entrada | Permiso | Éxito | Validaciones específicas | Vista o uso |
| --- | --- | --- | --- | --- | --- | --- |
| 30 | `POST /comercial/acceso` | Acceso | Público | 200 · Sesión | 401 credenciales incorrectas. 429 cuenta temporalmente bloqueada | Ingreso de administrador o comprador |
| 31 | `DELETE /comercial/sesion` | — | Bearer | 204 | 401 sin Bearer. Es idempotente frente a un token ya revocado | Cierra la sesión y sus canales |
| 32 | `GET /comercial/resumen` | — | A | 200 · Inventario | — | Métricas del panel administrativo |
| 33 | `GET /comercial/unidades` | Paginación | A | 200 · [Unidad administrada] | — | Inventario con propietario y conexión física |
| 34 | `GET /comercial/modelos` | Paginación | A | 200 · [Modelo] | — | Catálogo y selector de modelo |
| 35 | `POST /comercial/modelos` | Modelo entrada | A | 201 · Modelo | 409 por nombre duplicado | Alta de modelo |
| 36 | `PUT /comercial/modelos/{m}` | m + Modelo entrada | A | 200 · Modelo | 404 inexistente. 409 duplicado | Edición o baja lógica con `activo:false` |
| 37 | `GET /comercial/clientes` | Paginación | A | 200 · [Cliente] | — | Compradores y selección de titular |
| 38 | `POST /comercial/clientes` | Cliente alta | A | 201 · Cliente | 409 por correo duplicado | Alta de cuenta con rol `usuario` |
| 39 | `PUT /comercial/clientes/{u}` | u + Cliente edición | A | 200 · Cliente | 404 comprador inexistente. 409 correo duplicado | Edición o baja lógica. La baja revoca sesiones |
| 40 | `GET /comercial/mis-vehiculos` | — | U general | 200 · [Unidad propia] | — | Vehículos activos con asignación vigente a la cuenta |
| 41 | `PUT /comercial/unidades/{v}/propietario` | v + Asignación | A | 204 | 404 unidad inexistente. 409 titular distinto al esperado, unidad inactiva u operación en curso. 422 comprador inválido | Asignar, reasignar o retirar titular |
| 42 | `GET /salud` | — | Público | 200 · Salud | `rds:no_disponible` si falla la consulta a RDS | Indicadores de API y RDS. Comparte resultado durante cinco segundos |
| 43 | `GET /comercial/auditoria` | Paginación | A | 200 · [Auditoría] | — | Consulta actor, recurso, fecha, acción y resultado |
| 44 | `POST /comercial/unidades` | Ficha de unidad | A | 201 · ID de unidad | 422 modelo inactivo/inexistente o estado asignado sin titular | Alta comercial |
| 45 | `PUT /comercial/unidades/{unidad}` | unidad + Ficha de unidad | A | 200 · ID de unidad | 404 inexistente. 409 asignación incompatible u operación activa. 422 modelo/estado inválido | Edición o baja lógica con `estado:inactivo` |
| 46 | `GET /comercial/unidades/{unidad}/secuencias` | unidad | A/U editor | 200 · Catálogo del editor | 404 unidad inexistente o inactiva. 403 unidad ajena | El editor muestra demos visibles y comandos admitidos de la unidad |
| 47 | `GET /comercial/unidades/{unidad}/secuencias/{demo}` | unidad, demo | A/U editor | 200 · [Paso comercial] | 404 si no hay pasos accesibles. 403 unidad ajena | Carga de pasos para consultar y editar |
| 48 | `POST /comercial/unidades/{unidad}/secuencias` | unidad + Secuencia | A/U editor | 201 · ID de demo | 404 unidad inexistente o inactiva. 409 operación en curso. 422 comando o duración inválidos | Guarda ficha y pasos en una transacción |
| 49 | `PUT /comercial/unidades/{unidad}/secuencias/{demo}` | unidad, demo + Secuencia | A/U editor | 200 · ID de demo | 403 sin permiso de edición. 404 unidad inexistente o inactiva. 409 operación en curso. 422 comando o duración inválidos | Reemplaza ficha y pasos en orden |
| 50 | `DELETE /comercial/unidades/{unidad}/secuencias/{demo}` | unidad, demo | A/U editor | 200 · ID de demo | 403 sin permiso de baja. 404 unidad inexistente o inactiva. 409 operación en curso | Baja lógica de una demo |
| 51 | `GET /exhibicion/catalogo` | — | Público | 200 · Exhibición | 503 si falla RDS | Catálogo de modelos activos. Con exhibición deshabilitada, las listas de unidades vienen vacías |

`anterior` indica el titular observado al consultar el inventario. Usar `null` si no había titular. Enviar `id_usuario:null` para retirar la asignación. El cambio cierra las suscripciones anteriores antes de habilitar al nuevo titular. El editor comercial guarda de 1 a 32 pasos en el orden del arreglo y admite hasta 120.000 ms sumando duración y pausas. Cada comando debe estar activo y pertenecer a la unidad. Los resultados de las mutaciones comerciales se auditan.

## Ejemplos JSON

Los nombres de ejemplo corresponden a las columnas **Entrada** y **Éxito**. Cuando la respuesta es una lista, cada elemento tiene la forma del ejemplo. Los marcadores de credencial son ficticios.

### Catálogos y estado

**Vehículo alta**

```json
{"nombre":"Unidad de ensayo","modelo":"Excavadora","descripcion":"Registro de laboratorio","microcontrolador":"ESP8266"}
```

**Vehículo edición**

```json
{"nombre":"Unidad de ensayo","modelo":"Excavadora","descripcion":"Registro de laboratorio","microcontrolador":"ESP8266","activo":1}
```

**Vehículo**

```json
{"id_vehiculo":47,"nombre":"Unidad de ensayo","modelo":"Excavadora","descripcion":"Registro de laboratorio","microcontrolador":"ESP8266","fecha_registro":"2026-11-20T14:00:00","activo":1}
```

**Comando alta**

```json
{"nombre":"Avanzar","codigo":2,"descripcion":"Movimiento de ensayo"}
```

**Comando edición**

```json
{"nombre":"Avanzar","codigo":2,"descripcion":"Movimiento de ensayo","activo":1}
```

**Comando**

```json
{"id_comando":12,"id_vehiculo":47,"nombre":"Avanzar","codigo":2,"descripcion":"Movimiento de ensayo","activo":1}
```

**Demo alta**

```json
{"nombre":"Demo de ensayo","descripcion":"Secuencia de laboratorio"}
```

**Demo edición**

```json
{"nombre":"Demo de ensayo","descripcion":"Secuencia de laboratorio","activo":1}
```

**Demo**

```json
{"id_demo":8,"id_vehiculo":47,"nombre":"Demo de ensayo","descripcion":"Secuencia de laboratorio","activo":1}
```

**Paso legado entrada**

```json
{"id_comando":12,"orden":1,"duracion_ms":400,"pausa_ms":100}
```

**Paso legado**

```json
{"id_demo_movimiento":23,"id_demo":8,"id_comando":12,"orden":1,"duracion_ms":400,"pausa_ms":100,"comando":"Avanzar","codigo":2}
```

**Estado**

```json
{
  "id_vehiculo": 47,
  "vehiculo": "Unidad de ensayo",
  "id_comando": 12,
  "comando": "Avanzar",
  "codigo": 2,
  "conectado": 0,
  "fecha_actualizacion": "2026-11-20T15:13:00"
}
```

### Operación y monitoreo

**Movimiento individual**

```json
{"id_comando":12,"origen":"Postman"}
```

**Evento**

```json
{
  "tipo": "movimiento_individual",
  "id_vehiculo": 47,
  "id_comando": 12,
  "comando": "Avanzar",
  "codigo": 2,
  "marca_temporal": "2026-11-20T15:13:00Z",
  "estado": {
    "id_vehiculo": 47,
    "vehiculo": "Unidad de ensayo",
    "id_comando": 12,
    "comando": "Avanzar",
    "codigo": 2,
    "conectado": 0,
    "fecha_actualizacion": "2026-11-20T15:13:00"
  },
  "id_demo": null,
  "orden": null,
  "duracion_ms": null,
  "pausa_ms": null,
  "mensaje": null,
  "ejecucion_fisica_confirmada": false,
  "salidas_aplicadas_confirmadas": false,
  "orden_enviada": false,
  "modo_demo": null,
  "id_ejecucion": null,
  "pasos_enviados": null,
  "pasos_sin_envio": null,
  "origen": "Postman"
}
```

**Historial**

```json
{"id_historial":305,"id_vehiculo":47,"comando":"Avanzar","codigo":2,"fecha_hora":"2026-11-20T15:13:00","origen":"Postman"}
```

**Iniciar demo**

```json
{"id_demo":8,"modo":"registro"}
```

**Latido demo**

```json
{"id_ejecucion":"0123456789abcdef0123456789abcdef"}
```

**Vencimiento**

```json
{"vence_en_ms":900}
```

**Dispositivo**

```json
{
  "conectado": false,
  "listo": false,
  "modo": "sin_conexion",
  "codigo_activo": null,
  "encendido_estimado": null,
  "control_ocupado": false,
  "registro_error": null,
  "registros_pendientes": 0,
  "ultima_interrupcion": null,
  "confirmacion": "salidas del microcontrolador; sin sensores de movimiento",
  "demo_temporizada": false,
  "pulsos_encendido_explicitos": false,
  "diagnostico_enlace": {
    "saludo_confirmado": false,
    "saludos_enviados": 0,
    "segundos_sin_reporte": null
  }
}
```

**Permiso temporal de control**

```json
{
  "lease_id": "0123456789abcdef0123456789abcdef",
  "vence_en_ms": 900,
  "protocolo_control": 2,
  "dispositivo": {
    "conectado": false,
    "listo": false,
    "modo": "sin_conexion",
    "codigo_activo": null,
    "encendido_estimado": null,
    "control_ocupado": false,
    "registro_error": null,
    "registros_pendientes": 0,
    "ultima_interrupcion": null,
    "confirmacion": "salidas del microcontrolador; sin sensores de movimiento",
    "demo_temporizada": false,
    "pulsos_encendido_explicitos": false,
    "diagnostico_enlace": {
      "saludo_confirmado": false,
      "saludos_enviados": 0,
      "segundos_sin_reporte": null
    }
  }
}
```

**Permiso temporal entrada**

```json
{"lease_id":"0123456789abcdef0123456789abcdef"}
```

**Orden física**

```json
{"lease_id":"0123456789abcdef0123456789abcdef","codigo":2,"intencion":1}
```

**Resultado de orden con firmware directo**

```json
{"codigo":2,"duracion_ms":0,"orden_enviada":true,"salidas_confirmadas":false,"registro":"pendiente"}
```

**Resultado de parada al estar la placa desconectada**

```json
{"salidas_confirmadas":false,"mensaje":"Sin dispositivo; actúa su watchdog local."}
```

**Frase de voz**

```json
{"frase":"Avanza un momento","codigos_anteriores":[]}
```

**Plan de voz**

```json
{"pasos":[{"codigo":2,"duracion_ms":400,"pausa_ms":100}]}
```

En una orden HTTP normal, `codigo` va de 0 a 13 y el código 0 solicita detener. El código 9 exige `pulso_ms` de 200 o 2000. Los demás códigos omiten `pulso_ms`. `intencion` es opcional y sirve para ordenar entradas. `lease_id` e `id_ejecucion` son identificadores distintos de 32 caracteres hexadecimales. Una orden desplazada puede devolver `{"cancelado":true}`. Los campos de confirmación dependen del protocolo de la placa. La respuesta de parada indica si la API obtuvo confirmación de salidas, según el protocolo. El plan de voz admite hasta 8 pasos y 30 segundos totales.

### Administración, sesiones y exhibición

**Acceso**

```json
{"correo":"persona@example.invalid","clave":"<contraseña de ensayo>"}
```

**Sesión**

```json
{"token":"<token temporal>","nombre":"Persona de ensayo","rol":"usuario"}
```

**Modelo entrada**

```json
{"nombre":"Excavadora","descripcion":"Modelo de laboratorio","activo":true}
```

**Modelo**

```json
{"id_modelo":9,"nombre":"Excavadora","descripcion":"Modelo de laboratorio","activo":true}
```

**Cliente alta**

```json
{"nombre":"Persona de ensayo","correo":"persona@example.invalid","clave":"<contraseña de ensayo>"}
```

**Cliente edición**

```json
{"nombre":"Persona de ensayo","correo":"persona@example.invalid","activo":false}
```

**Cliente**

```json
{"id_usuario":27,"nombre":"Persona de ensayo","correo":"persona@example.invalid","activo":true}
```

**Ficha de unidad**

```json
{"nombre":"Unidad de ensayo","id_modelo":9,"estado":"disponible"}
```

**ID de unidad**

```json
{"id_vehiculo":47}
```

**Asignación**

```json
{"id_usuario":27,"anterior":null}
```

**Unidad propia**

```json
{"id_vehiculo":47,"nombre":"Unidad de ensayo","modelo":"Excavadora","estado":"asignado"}
```

**Unidad administrada**

```json
{
  "id_vehiculo": 47,
  "nombre": "Unidad de ensayo",
  "modelo": "Excavadora",
  "estado": "asignado",
  "id_modelo": 9,
  "conectado": false,
  "id_usuario": 27,
  "propietario": "Persona de ensayo"
}
```

**Inventario**

```json
{"total_modelos":1,"total_unidades":1,"asignadas":1,"exhibicion":0,"sin_clasificar":0,"clientes":1,"demos":2}
```

**Auditoría**

```json
{"id_evento":52,"fecha":"2026-11-20T14:15:00","actor":6,"accion":"alta_unidad","recurso":"unidad","id_recurso":47,"resultado":"correcto"}
```

**Catálogo del editor**

```json
{
  "demos": [
    {
      "id_demo": 8,
      "nombre": "Demo de ensayo",
      "descripcion": "Secuencia de laboratorio",
      "fabrica": 1
    }
  ],
  "comandos": [
    {
      "id_comando": 12,
      "nombre": "Avanzar",
      "codigo": 2
    }
  ]
}
```

**Paso comercial**

```json
{"id_comando":12,"duracion_ms":400,"pausa_ms":100}
```

**Secuencia**

```json
{
  "nombre": "Demo de ensayo",
  "descripcion": "Secuencia de laboratorio",
  "pasos": [
    {
      "id_comando": 12,
      "duracion_ms": 400,
      "pausa_ms": 100
    }
  ]
}
```

**ID de demo**

```json
{"id_demo":8}
```

**Salud**

```json
{"api":"disponible","rds":"disponible"}
```

**Exhibición**

```json
{
  "habilitada": false,
  "modelos": [
    {
      "id_modelo": 9,
      "nombre": "Excavadora",
      "descripcion": "Modelo de laboratorio",
      "unidades": []
    }
  ]
}
```

## Contrato WebSocket

Los canales WSS se documentan aparte del conteo HTTP. En el navegador, el cliente ofrece dos subprotocolos: el rol (`iot-control` o `iot-monitor`) y `token.<token codificado en base64url sin relleno>`. El servidor valida `Origin`, sesión y propiedad antes de aceptar. Con un cliente independiente sin subprotocolo, se puede usar `Authorization: Bearer <token>` para observación. El canal de la placa usa su credencial de dispositivo, distinta de una sesión comercial.

| Canal | Identidad | Mensajes y efecto |
| --- | --- | --- |
| `/ws/vehiculos/{v}` con `iot-control` | Comprador del vehículo | Entrega `estado` al conectar. Acepta solicitudes con `id`, `accion` y `datos`. Devuelve `respuesta` con `ok` y `datos`, o `error` y `estado_http` cuando corresponde |
| `/ws/vehiculos/{v}` con `iot-monitor` | Comprador del vehículo | Entrega `estado` e `historial` inicial de hasta 10 movimientos. Publica movimientos individuales, eventos de DEMO y tramas de diagnóstico. Oculta `id_ejecucion` |
| `/ws/vehiculos/{v}` con `iot-device` o `iot-device-direct` | Placa con credencial autorizada para ese ID | Canal de órdenes y estado del dispositivo según el firmware. En 4.3 se vincula cada credencial a una unidad |
| `/panel/ws/vehiculos/{v}` y `/dispositivo/ws/vehiculos/{v}` | Alias del panel y de la placa sujetos a permisos | Compatibilidad con clientes anteriores. Para integraciones nuevas se usa `/ws/vehiculos/{v}` |
| `/exhibicion/ws/{unidad}` | Invitado con origen autorizado y exhibición habilitada | Requiere unidad de exhibición libre, sin comprador y placa lista. Devuelve `inicio` con `segundos` y mapa de `comandos`. Acepta `latido`, un `codigo` permitido o `detener`. Vencimiento de 45 s y registro de cierre |

Ejemplo de consulta inocua desde `iot-control`.

```json
{"id":1,"accion":"estado","datos":{}}
```

Las acciones del mando incluyen `entrada`, `estado`, `activar`, `orden`, `latido`, `liberar`, `demo_iniciar`, `demo_latido` y `demo_cancelar`. `entrada` usa código e intención, admite duración de 100 a 5.000 ms para movimientos compatibles y devuelve el resultado de esa entrada. El monitor resincroniza estado e historial con REST al recuperar la conexión. La revocación o cambio de titular retira la suscripción anterior.

## Comprobación reproducible

1. En la copia de ensayo, abre [Swagger](https://cape-landside-tidy.ngrok-free.dev/docs) para consultar los contratos y usa el mismo `/docs` local para ejecutar mutaciones. Crea una sesión con `/comercial/acceso`. La documentación de rutas protegidas puede requerir autorizar ambos esquemas Bearer en Swagger (`SesionComercial` y `HTTPBearer`).
2. Verifica `/salud`. Con una cuenta de comprador, consulta `/comercial/mis-vehiculos` y luego estado e historial para una unidad propia. Repite con otra unidad del entorno de ensayo y comprueba `403`.
3. En un cliente WebSocket independiente, suscríbete al mismo vehículo autorizado. Emite un movimiento individual en el entorno de ensayo y verifica el evento, su ID de unidad y la entrada REST en el historial. Ejecuta una DEMO de registro y comprueba `demo_iniciada` y `demo_finalizada`. Compara el historial individual anterior y posterior a la DEMO.
4. Para documentar una alta o edición, incluye método, ruta, entorno, código de respuesta y los campos relevantes. Oculta Bearer, claves, correos reales, direcciones internas y datos de clientes. [Matriz P01–P17](MATRIZ-4-3.md)
