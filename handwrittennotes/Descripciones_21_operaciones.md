# Descripciones de las 21 operaciones

Texto de apoyo para los apuntes sobre el funcionamiento de las APIs.

## 1 Crear un vehículo

`POST /admin/vehiculos`  
`sp_crear_vehiculo`

Esta API la usé para registrar el vehículo de prueba. Mandé su nombre, modelo, descripción y microcontrolador. Me respondió 201 Created y me dio el ID 3. Ese número lo utilicé después para consultar el vehículo y agregarle comandos y una DEMO.

## 2 Ver todos los vehículos

`GET /admin/vehiculos`  
`sp_obtener_vehiculos`

Con esta petición revisé los vehículos que estaban guardados en la base. No tuve que mandar un JSON, solamente hice el GET con la autorización. Me respondió 200 OK y en la lista apareció el vehículo de prueba que acababa de crear.

## 3 Consultar un vehículo por su ID

`GET /admin/vehiculos/{v}`  
`sp_obtener_vehiculo`

Aquí puse el ID 3 en la ruta para consultar solamente el vehículo de prueba. La respuesta fue 200 OK y mostró su nombre, modelo, descripción y microcontrolador. La diferencia con la consulta anterior es que aquí obtuve un solo vehículo y no toda la lista.

## 4 Cambiar los datos de un vehículo

`PUT /admin/vehiculos/{v}`  
`sp_actualizar_vehiculo`

Esta operación la usé para cambiar la descripción del vehículo 3. Mandé los datos del vehículo y su estado activo. Me respondió 200 OK y apareció la descripción Vehículo auxiliar actualizado. El ID se mantuvo igual porque estaba modificando el mismo registro.

## 5 Eliminar un vehículo

`DELETE /admin/vehiculos/{v}`  
`sp_eliminar_vehiculo`

Esta petición la hice al terminar la limpieza de los datos de prueba. Puse el ID 3 y me respondió 204 No Content. No regresó un JSON porque el vehículo ya se había eliminado. Antes borré su paso de DEMO, la DEMO y el comando para quitar primero los registros relacionados.

## 6 Crear un comando

`POST /admin/vehiculos/{v}/comandos`  
`sp_crear_comando`

Esta API me sirvió para agregar un comando al vehículo de prueba. Mandé el nombre, el código 9001 y la descripción. Me respondió 201 Created y me dio el ID 17. Aquí solo quedó registrado el comando; crearlo no significa enviarlo al carro ni ejecutar un movimiento.

## 7 Ver los comandos de un vehículo

`GET /admin/vehiculos/{v}/comandos`  
`sp_obtener_comandos_vehiculo`

Con esta consulta revisé qué comandos tenía el vehículo 3. La respuesta fue 200 OK y apareció el comando 17 con el código 9001. Así pude revisar que estaba relacionado con el vehículo correcto y que seguía activo antes de continuar con las demás peticiones.

## 8 Cambiar un comando

`PUT /admin/vehiculos/{v}/comandos/{c}`  
`sp_actualizar_comando`

Aquí actualicé el comando 17 del vehículo 3. Cambié su código de 9001 a 9002 y mandé también el nombre, la descripción y el estado activo. La API respondió 200 OK. El ID del comando siguió siendo 17; lo que cambió fue el código que tenía guardado.

## 9 Eliminar un comando

`DELETE /admin/vehiculos/{v}/comandos/{c}`  
`sp_eliminar_comando`

Esta petición la usé para borrar el comando auxiliar 17. Mandé los IDs del vehículo y del comando en la ruta, sin un cuerpo JSON. Me respondió 204 No Content. Lo eliminé después del paso y de la DEMO, porque esos registros usaban el comando de prueba.

## 10 Actualizar el estado al mandar un movimiento

`POST /vehiculos/{v}/movimientos`  
`sp_actualizar_estado`

Para esta prueba mandé un movimiento al vehículo 1 con el comando 9. La respuesta fue 200 OK y mostró movimiento_individual con el comando ENCENDER_APAGAR. Esta parte actualiza el último comando del vehículo. Recibir la petición no hace que el campo conectado cambie automáticamente a verdadero.

## 11 Consultar el estado del vehículo

`GET /admin/vehiculos/{v}/estado`  
`sp_obtener_estado`

Aquí consulté el estado del vehículo de prueba con ID 3. La respuesta fue 200 OK, pero el contenido salió como null. Esto tiene sentido porque ese vehículo acababa de crearse y todavía no tenía un estado registrado. No quiere decir que el vehículo no exista.

## 12 Guardar el movimiento en el historial

`POST /vehiculos/{v}/movimientos`  
`sp_registrar_historial`

Esta parte se ejecuta dentro del mismo POST que actualiza el estado, así que no mandé otra petición para guardar el historial. Después consulté el historial y apareció el registro 19 con el comando ENCENDER_APAGAR y el origen Postman. El estado y el historial se confirman juntos antes de avisar por WebSocket.

## 13 Consultar los últimos movimientos

`GET /vehiculos/{v}/historial?limite=10`  
`sp_obtener_historial`

Esta consulta la hice con el vehículo 1 y el parámetro limite=10. Me respondió 200 OK y el primer registro visible fue el 19. La API puede mostrar como máximo diez movimientos recientes; no borra los anteriores de la base. Si hay menos de diez, solo devuelve los que encuentre.

## 14 Crear una DEMO

`POST /admin/vehiculos/{v}/demos`  
`sp_crear_demo`

Con esta petición creé la definición de una DEMO para el vehículo 3. Mandé el nombre y la descripción. Me respondió 201 Created y me dio el ID 3 para la DEMO. En este paso solo se guarda la definición; todavía falta agregar sus pasos y mandar la petición para ejecutarla.

## 15 Consultar las DEMO de un vehículo

`GET /admin/vehiculos/{v}/demos`  
`sp_obtener_demos`

Esta API la usé para ver las DEMO que estaban relacionadas con el vehículo de prueba. Me respondió 200 OK y apareció la DEMO 3 que había creado. Esta consulta permite revisar el nombre, la descripción y si la definición está activa antes de trabajar con sus pasos.

## 16 Cambiar los datos de una DEMO

`PUT /admin/vehiculos/{v}/demos/{d}`  
`sp_actualizar_demo`

Aquí actualicé la descripción de la DEMO 3 del vehículo 3. Mandé su nombre, la nueva descripción y el estado activo. La respuesta fue 200 OK y mostró DEMO auxiliar actualizada. Esta petición cambia la definición guardada; no inicia la secuencia ni manda sus movimientos.

## 17 Eliminar una DEMO

`DELETE /admin/vehiculos/{v}/demos/{d}`  
`sp_eliminar_demo`

Esta operación la hice para borrar la DEMO auxiliar 3 después de eliminar su paso. La respuesta fue 204 No Content. Eliminar una DEMO borra su definición de la base. Es diferente de cancelar una ejecución, porque cancelar detiene la secuencia de software sin borrar la definición.

## 18 Agregar un paso a una DEMO

`POST /admin/vehiculos/{v}/demos/{d}/movimientos`  
`sp_agregar_movimiento_demo`

Con esta petición agregué un paso a la DEMO 3. Usé el comando 17, el orden 1, una duración de 200 ms y una pausa de 100 ms. Me respondió 201 Created y me dio el ID 12 para el paso. La duración indica el tiempo del movimiento y la pausa es la espera antes de seguir.

## 19 Consultar los pasos de una DEMO

`GET /admin/vehiculos/{v}/demos/{d}/movimientos`  
`sp_obtener_movimientos_demo`

Aquí revisé los pasos guardados en la DEMO del vehículo de prueba. La API respondió 200 OK y mostró el paso 12 con el comando 17 y los tiempos que había registrado. Cuando se inicia una DEMO, el servicio consulta estos pasos en la base y los procesa según su orden.

## 20 Cambiar un paso de DEMO

`PUT /admin/vehiculos/{v}/demos/{d}/movimientos/{m}`  
`sp_actualizar_movimiento_demo`

Para esta operación dejé preparado el JSON del paso 12 con el comando 17, el orden 2, una duración de 400 ms y una pausa de 0 ms. Sirve para cambiar cómo está configurado ese paso. En la captura aparece la petición preparada, pero todavía no se muestra una respuesta de actualización.

## 21 Eliminar un paso de DEMO

`DELETE /admin/vehiculos/{v}/demos/{d}/movimientos/{m}`  
`sp_eliminar_movimiento_demo`

Esta petición la usé para borrar el paso auxiliar 12 de la DEMO 3. La respuesta fue 204 No Content y no regresó un JSON. Fue el primer registro que eliminé en la limpieza, antes de borrar la DEMO, el comando y el vehículo de prueba.
