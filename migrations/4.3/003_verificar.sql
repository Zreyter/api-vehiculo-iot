SELECT COUNT(*) AS vehiculos FROM vehiculos;
SELECT COUNT(*) AS unidades_vinculadas FROM comercial_unidades;
SELECT COUNT(*) AS unidades_por_revisar FROM vehiculos v
LEFT JOIN comercial_unidades u USING (id_vehiculo) WHERE u.id_vehiculo IS NULL;
SELECT COUNT(*) AS movimientos_individuales FROM historial_comandos;
SELECT COUNT(*) AS pasos_demo FROM demo_movimientos;
SELECT COUNT(*) AS procedimientos FROM information_schema.routines
WHERE routine_schema = DATABASE() AND routine_type = 'PROCEDURE';
