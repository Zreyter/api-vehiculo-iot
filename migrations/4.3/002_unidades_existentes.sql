-- Primera clasificación. Los dueños y la disponibilidad de prueba requieren verificación humana.
START TRANSACTION;
INSERT INTO comercial_modelos (nombre)
SELECT DISTINCT TRIM(v.modelo)
FROM vehiculos v
LEFT JOIN comercial_unidades u ON u.id_vehiculo = v.id_vehiculo
LEFT JOIN comercial_modelos m ON m.nombre = TRIM(v.modelo)
WHERE u.id_vehiculo IS NULL AND m.id_modelo IS NULL AND TRIM(v.modelo) <> '';

INSERT INTO comercial_unidades (id_vehiculo, id_modelo, estado)
SELECT v.id_vehiculo, m.id_modelo, IF(v.activo = 1, 'sin_clasificar', 'inactivo')
FROM vehiculos v
JOIN comercial_modelos m ON m.nombre = TRIM(v.modelo)
LEFT JOIN comercial_unidades u ON u.id_vehiculo = v.id_vehiculo
WHERE u.id_vehiculo IS NULL;
COMMIT;
