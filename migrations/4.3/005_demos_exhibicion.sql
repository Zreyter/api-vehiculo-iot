CREATE TABLE IF NOT EXISTS comercial_demos_privadas (
    id_demo INT PRIMARY KEY,
    id_usuario INT NOT NULL,
    FOREIGN KEY (id_demo) REFERENCES demos(id_demo),
    FOREIGN KEY (id_usuario) REFERENCES comercial_usuarios(id_usuario)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comercial_exhibiciones (
    id_sesion BIGINT PRIMARY KEY AUTO_INCREMENT,
    id_vehiculo INT NOT NULL,
    inicio DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    vence DATETIME(6) NOT NULL,
    cierre DATETIME(6),
    motivo VARCHAR(32),
    unidad_reservada INT GENERATED ALWAYS AS (IF(cierre IS NULL,id_vehiculo,NULL)) STORED UNIQUE,
    FOREIGN KEY (id_vehiculo) REFERENCES comercial_unidades(id_vehiculo),
    INDEX (id_vehiculo,vence)
) ENGINE=InnoDB;
