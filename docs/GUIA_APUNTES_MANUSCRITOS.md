# Guía de apoyo para elaborar los apuntes manuscritos

Esta guía debe utilizarse como referencia para escribir con tus propias palabras. Los apuntes manuscritos finales se guardan en `/handwrittennotes` dentro de este repositorio.

Base de las rutas: http://3.233.212.203:8000. Consulta de operaciones: http://3.233.212.203:8000/docs. Utiliza el token de control del documento de evidencias; no lo copies en el repositorio.

Notación: v = vehículo, c = comando, d = DEMO, m = paso. Los IDs de prueba 3, 17, 3 y 12 ya se eliminaron durante la limpieza; para nuevas operaciones usa IDs vigentes.

La numeración cubre los 21 procedimientos almacenados. La API expone 22 operaciones HTTP, porque combina algunos SP en una petición y añade acciones de ejecución y cancelación de DEMO.

## 1 Crear un vehículo

- **Procedimiento:** `sp_crear_vehiculo`.
- **Método y ruta:** `POST /admin/vehiculos`.
- **Entrada:** nombre, modelo, descripcion y microcontrolador. No enviar activo en el alta.
- **Funcionamiento y respuesta:** 201 Created y el vehículo creado con su id_vehiculo.
- **Resultado de referencia:** La figura 5 muestra el vehículo auxiliar ID 3, ESP8266 y activo=1.
- **Explicación personal:** Explica cómo obtuviste el ID y para qué sirve en las peticiones siguientes.

## 2 Listar los vehículos

- **Procedimiento:** `sp_obtener_vehiculos`.
- **Método y ruta:** `GET /admin/vehiculos`.
- **Entrada:** Sin cuerpo JSON ni ID en la ruta. Enviar autorización.
- **Funcionamiento y respuesta:** 200 OK con una lista; incluye registros activos e inactivos.
- **Resultado de referencia:** La figura 9 muestra el vehículo auxiliar ID 3 dentro del listado.
- **Explicación personal:** Describe cómo identificaste el registro creado entre los demás vehículos.

## 3 Consultar un vehículo

- **Procedimiento:** `sp_obtener_vehiculo`.
- **Método y ruta:** `GET /admin/vehiculos/{v}`.
- **Entrada:** v es el ID del vehículo. No lleva cuerpo JSON.
- **Funcionamiento y respuesta:** 200 OK con un objeto; 404 si el recurso no existe.
- **Resultado de referencia:** La figura 10 muestra la consulta del vehículo 3 con sus datos.
- **Explicación personal:** Distingue esta consulta del listado de todos los vehículos.

## 4 Actualizar un vehículo

- **Procedimiento:** `sp_actualizar_vehiculo`.
- **Método y ruta:** `PUT /admin/vehiculos/{v}`.
- **Entrada:** nombre, modelo, descripcion, microcontrolador y activo.
- **Funcionamiento y respuesta:** 200 OK con el vehículo actualizado; activo=0 permite desactivarlo.
- **Resultado de referencia:** La figura 15 muestra 200 OK y la descripción Vehículo auxiliar actualizado.
- **Explicación personal:** Anota qué campo cambiaste y qué identificador se conservó.

## 5 Eliminar un vehículo

- **Procedimiento:** `sp_eliminar_vehiculo`.
- **Método y ruta:** `DELETE /admin/vehiculos/{v}`.
- **Entrada:** ID del vehículo en la ruta; sin cuerpo. Usar solo registros auxiliares para la limpieza.
- **Funcionamiento y respuesta:** 204 No Content tras el borrado físico. Las relaciones de MySQL pueden impedirlo o aplicar cascadas.
- **Resultado de referencia:** La figura 22 muestra 204 para el vehículo auxiliar 3, después de limpiar sus dependencias.
- **Explicación personal:** Explica por qué se elimina al final y en qué se diferencia de desactivar.

## 6 Crear un comando

- **Procedimiento:** `sp_crear_comando`.
- **Método y ruta:** `POST /admin/vehiculos/{v}/comandos`.
- **Entrada:** nombre, codigo y descripcion; el vehículo se indica en la ruta.
- **Funcionamiento y respuesta:** 201 Created con el id_comando. El código es independiente del ID y debe ser único en el vehículo.
- **Resultado de referencia:** La figura 6 muestra el comando ID 17 del vehículo 3, con código 9001.
- **Explicación personal:** Aclara la diferencia entre crear un comando y ejecutar un movimiento.

## 7 Consultar los comandos de un vehículo

- **Procedimiento:** `sp_obtener_comandos_vehiculo`.
- **Método y ruta:** `GET /admin/vehiculos/{v}/comandos`.
- **Entrada:** ID del vehículo y autorización; sin cuerpo JSON.
- **Funcionamiento y respuesta:** 200 OK con los comandos asociados, incluidos los inactivos.
- **Resultado de referencia:** La figura 12 muestra el comando 17, código 9001 y activo=1.
- **Explicación personal:** Explica cómo comprobaste a qué vehículo pertenece el comando.

## 8 Actualizar un comando

- **Procedimiento:** `sp_actualizar_comando`.
- **Método y ruta:** `PUT /admin/vehiculos/{v}/comandos/{c}`.
- **Entrada:** nombre, codigo, descripcion y activo; v y c en la ruta.
- **Funcionamiento y respuesta:** 200 OK con el comando actualizado. No debe duplicarse el código de otro comando del vehículo.
- **Resultado de referencia:** La figura 16 muestra que el comando 17 cambió su código de 9001 a 9002.
- **Explicación personal:** Anota qué valor cambió y por qué el ID no cambió.

## 9 Eliminar un comando

- **Procedimiento:** `sp_eliminar_comando`.
- **Método y ruta:** `DELETE /admin/vehiculos/{v}/comandos/{c}`.
- **Entrada:** IDs del vehículo y del comando; sin cuerpo JSON.
- **Funcionamiento y respuesta:** 204 No Content. Las dependencias de la base pueden producir un conflicto.
- **Resultado de referencia:** La figura 21 muestra 204 al eliminar el comando auxiliar 17.
- **Explicación personal:** Describe el orden de limpieza respecto de los pasos de DEMO.

## 10 Actualizar el estado mediante un movimiento

- **Procedimiento:** `sp_actualizar_estado`.
- **Método y ruta:** `POST /vehiculos/{v}/movimientos`.
- **Entrada:** Ejemplo: {"id_comando":9,"origen":"Postman"}. El servicio también lo usa durante una DEMO.
- **Funcionamiento y respuesta:** 200 OK con evento movimiento_individual. Se valida actividad y pertenencia; se conserva conectado.
- **Resultado de referencia:** La figura 1 muestra movimiento_individual, vehículo 1, comando 9 y ENCENDER_APAGAR.
- **Explicación personal:** Explica por qué este SP y el registro de historial comparten una petición y una transacción.

## 11 Consultar el último estado

- **Procedimiento:** `sp_obtener_estado`.
- **Método y ruta:** `GET /admin/vehiculos/{v}/estado`.
- **Entrada:** ID del vehículo; también se consulta el estado al abrir el WebSocket.
- **Funcionamiento y respuesta:** 200 OK con el estado o null si el vehículo existe pero aún no tiene estado.
- **Resultado de referencia:** La figura 11 muestra 200 OK y null para el vehículo auxiliar 3.
- **Explicación personal:** Explica por qué null con 200 no significa que el vehículo sea inexistente.

## 12 Registrar el historial individual

- **Procedimiento:** `sp_registrar_historial`.
- **Método y ruta:** `POST /vehiculos/{v}/movimientos`.
- **Entrada:** El mismo id_comando y origen de la operación anterior; no hay una ruta independiente para este SP.
- **Funcionamiento y respuesta:** El movimiento confirma estado e historial antes de emitir su evento. No se usa para los pasos de DEMO.
- **Resultado de referencia:** Las figuras 1 y 2 muestran el comando 9 y su registro de historial 19, con origen Postman.
- **Explicación personal:** Relaciona la respuesta POST con el registro que encontraste en el GET de historial.

## 13 Consultar el historial reciente

- **Procedimiento:** `sp_obtener_historial`.
- **Método y ruta:** `GET /vehiculos/{v}/historial?limite=10`.
- **Entrada:** ID del vehículo y limite entre 1 y 10. Esta consulta no exige token en la implementación actual.
- **Funcionamiento y respuesta:** 200 OK con hasta diez movimientos recientes. Con menos registros devuelve los disponibles y conserva el resto en RDS.
- **Resultado de referencia:** La figura 2 muestra limite=10, respuesta 200 y el registro 19 como primero visible; el JSON completo no se ve.
- **Explicación personal:** Anota el número real de elementos si lo contaste. No deduzcas que hay diez solo por el parámetro.

## 14 Crear una definición DEMO

- **Procedimiento:** `sp_crear_demo`.
- **Método y ruta:** `POST /admin/vehiculos/{v}/demos`.
- **Entrada:** nombre y descripcion; el vehículo se indica en la ruta.
- **Funcionamiento y respuesta:** 201 Created con id_demo. Guarda una definición; no inicia su ejecución.
- **Resultado de referencia:** La figura 7 muestra DEMO_LAB_API_2_5 con ID 3 y vehículo 3.
- **Explicación personal:** Distingue crear una DEMO de iniciarla mediante POST /vehiculos/{v}/demos.

## 15 Listar las DEMO de un vehículo

- **Procedimiento:** `sp_obtener_demos`.
- **Método y ruta:** `GET /admin/vehiculos/{v}/demos`.
- **Entrada:** ID del vehículo y autorización; sin cuerpo.
- **Funcionamiento y respuesta:** 200 OK con las definiciones del vehículo, incluidas las inactivas.
- **Resultado de referencia:** La figura 13 muestra la definición DEMO 3 asociada al vehículo 3.
- **Explicación personal:** Explica cómo elegiste una definición perteneciente al vehículo correcto.

## 16 Actualizar una definición DEMO

- **Procedimiento:** `sp_actualizar_demo`.
- **Método y ruta:** `PUT /admin/vehiculos/{v}/demos/{d}`.
- **Entrada:** nombre, descripcion y activo; IDs de vehículo y DEMO.
- **Funcionamiento y respuesta:** 200 OK con la definición actualizada. Durante una ejecución del vehículo se rechazan cambios con 409.
- **Resultado de referencia:** La figura 17 muestra la descripción DEMO auxiliar actualizada con respuesta 200.
- **Explicación personal:** Anota qué cambió y explica por qué editar la definición no ejecuta sus pasos.

## 17 Eliminar una definición DEMO

- **Procedimiento:** `sp_eliminar_demo`.
- **Método y ruta:** `DELETE /admin/vehiculos/{v}/demos/{d}`.
- **Entrada:** IDs del vehículo y de la DEMO; sin cuerpo.
- **Funcionamiento y respuesta:** 204 No Content. Elimina la definición; no equivale a cancelar una DEMO activa.
- **Resultado de referencia:** La figura 20 muestra 204 al eliminar la DEMO auxiliar 3 después de su paso.
- **Explicación personal:** Explica la diferencia entre eliminar la definición y cancelar la ejecución.

## 18 Agregar un paso a una DEMO

- **Procedimiento:** `sp_agregar_movimiento_demo`.
- **Método y ruta:** `POST /admin/vehiculos/{v}/demos/{d}/movimientos`.
- **Entrada:** id_comando, orden, duracion_ms y pausa_ms. Orden positivo y tiempos no negativos.
- **Funcionamiento y respuesta:** 201 Created con id_demo_movimiento. El comando y la DEMO deben pertenecer al vehículo.
- **Resultado de referencia:** La figura 8 muestra paso 12, comando 17, orden 1, duración 200 ms y pausa 100 ms.
- **Explicación personal:** Explica qué representan duración y pausa y por qué el orden no debe repetirse.

## 19 Consultar los pasos de una DEMO

- **Procedimiento:** `sp_obtener_movimientos_demo`.
- **Método y ruta:** `GET /admin/vehiculos/{v}/demos/{d}/movimientos`.
- **Entrada:** IDs de vehículo y DEMO; sin cuerpo. El servicio lo consulta al iniciar la secuencia.
- **Funcionamiento y respuesta:** 200 OK con los pasos; la ejecución los procesa por orden, sin una secuencia fija en el código.
- **Resultado de referencia:** La figura 14 muestra el paso 12 con orden 1, comando 17 y tiempos 200 y 100 ms.
- **Explicación personal:** Describe cómo relacionaste el comando, el orden y los tiempos del paso.

## 20 Actualizar un paso de DEMO

- **Procedimiento:** `sp_actualizar_movimiento_demo`.
- **Método y ruta:** `PUT /admin/vehiculos/{v}/demos/{d}/movimientos/{m}`.
- **Entrada:** id_comando, orden, duracion_ms y pausa_ms. En el ejemplo: comando 17, orden 2, duración 400 y pausa 0.
- **Funcionamiento y respuesta:** 200 OK con el paso actualizado si la petición es válida; 409 ante orden duplicado o DEMO activa.
- **Resultado de referencia:** La figura 18 solo muestra el cuerpo preparado. No muestra una respuesta de actualización.
- **Explicación personal:** Registra el código y el cambio que observaste al ejecutarla; si no la ejecutaste, indícalo.

## 21 Eliminar un paso de DEMO

- **Procedimiento:** `sp_eliminar_movimiento_demo`.
- **Método y ruta:** `DELETE /admin/vehiculos/{v}/demos/{d}/movimientos/{m}`.
- **Entrada:** IDs de vehículo, DEMO y paso; sin cuerpo JSON.
- **Funcionamiento y respuesta:** 204 No Content y cuerpo vacío después de confirmar el borrado.
- **Resultado de referencia:** La figura 19 muestra 204 al eliminar el paso auxiliar 12 de la DEMO 3.
- **Explicación personal:** Explica por qué el paso se elimina antes que la DEMO, el comando y el vehículo.

## Acciones que también debes explicar

**Iniciar DEMO:** `POST /vehiculos/{v}/demos` con `{"id_demo":1}`. Si se acepta, devuelve 202 y emite eventos `demo_iniciada`, `demo_movimiento` y `demo_finalizada`. Lee los pasos en RDS, respeta orden, duración y pausa, y actualiza el estado sin registrar historial. La captura de inicio recibida solo muestra la preparación de la solicitud.

**Cancelar DEMO:** `DELETE /vehiculos/{v}/demos/activa`. Cancela la secuencia de software y evita nuevos pasos; no envía una parada física al motor. La implementación espera la finalización de una operación SQL que ya estuviera en curso.

**WebSocket:** `ws://3.233.212.203:8000/ws/vehiculos/1`, con el encabezado `Authorization: Bearer TU_TOKEN`. Al conectar consulta el estado y entrega eventos del vehículo. Las órdenes se envían por HTTP. La captura recibida muestra conexión activa y eventos `movimiento_individual`.

Para explicar la DEMO a partir de una prueba real, anota el ID, la cantidad de pasos, los tiempos y los eventos que recibiste. Compara el historial completo antes y después sin enviar movimientos individuales entre ambas consultas.
