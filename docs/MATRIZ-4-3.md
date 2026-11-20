# Práctica 4.3 · Matriz P01–P17

| ID | Caso | Resultado individual y evidencia |
| --- | --- | --- |
| P01 | Ingreso de Administración | Correcto en ensayo con una cuenta de administrador |
| P02 | Alta de unidad | Correcto en MySQL de ensayo con modelo y baja lógica |
| P03 | Alta de comprador | Correcto en ensayo y en RDS con el comprador de la unidad 1 |
| P04 | Asignación | Correcto. La cuenta de la unidad 1 consultó su historial en AWS |
| P05 | Aislamiento de comprador | Correcto. La transferencia cerró los canales anteriores y el comprador anterior perdió acceso en la API |
| P06 | Control y DETENER | Correcto. El propietario confirmó desde su celular el movimiento físico y la parada |
| P07 | WebSocket | Correcto. Control y Monitoreo recibieron estado desde AWS |
| P08 | Últimos diez movimientos | Correcto. El monitor mostró diez registros en ambas publicaciones |
| P09 | Demo persistente | Correcto en la copia MySQL. Se guardaron y se consultaron los pasos en orden |
| P10 | Ejecución y cancelación de demo | Correcto en modo registro sobre la copia local. Monitoreo recibió inicio y fin. Los diez movimientos individuales conservaron sus identificadores y contenido. La ejecución física de la demo queda por comprobar |
| P11 | Prueba de invitado | No ejecutado en el carro. Exhibición sin disponibilidad pública por decisión del propietario |
| P12 | Rechazo de acceso a Administración | Correcto. La API exige una sesión de administrador |
| P13 | Vehículo ajeno | Correcto. AWS rechazó el acceso de la cuenta de la unidad 1 a la unidad 2 |
| P14 | Exclusividad de exhibición | Correcto en MySQL de ensayo. Un segundo canal WebSocket recibió rechazo y el primero terminó con DETENER y liberó su reserva. Se usó una placa simulada |
| P15 | Reconexión | Correcto en las pruebas automatizadas de desconexión y recuperación. Falta repetir la interrupción con el equipo |
| P16 | Diseño responsivo | Correcto en el recorrido de navegador de 390 px |
| P17 | Auditoría | Correcto en MySQL de ensayo. Alta de unidad y demo registradas con su actor |

## Evaluación colaborativa

Cada integrante registra fecha, URL, caso, rol ejercido, resultado y evidencia. Vercel y GitHub Pages son dos publicaciones de una sola plataforma.

| Ronda | Plataforma | Administración | Usuario | Invitado | Estado |
| --- | --- | --- | --- | --- | --- |
| A | Proyecto propio | A | B | C | No ejecutada con el equipo |
| B | Proyecto de B | B | C | A | Pendiente de URL y evaluación |
| C | Proyecto de C | C | A | B | Pendiente de URL y evaluación |

- [Repositorio original](https://github.com/Zreyter/api-vehiculo-iot)
- [Vercel](https://vehiculo-iot.vercel.app/)
- [GitHub Pages](https://zreyter.github.io/api-vehiculo-iot/)
- [Swagger](https://cape-landside-tidy.ngrok-free.dev/docs)
