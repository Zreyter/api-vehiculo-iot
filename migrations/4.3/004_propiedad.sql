CREATE TABLE IF NOT EXISTS comercial_propiedad (
    id_vehiculo INT PRIMARY KEY,
    id_usuario INT NOT NULL,
    FOREIGN KEY (id_vehiculo) REFERENCES comercial_unidades(id_vehiculo),
    FOREIGN KEY (id_usuario) REFERENCES comercial_usuarios(id_usuario),
    INDEX (id_usuario, id_vehiculo)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comercial_cambios_propietario (
    id_evento BIGINT PRIMARY KEY,
    anterior INT NULL,
    nuevo INT NULL,
    FOREIGN KEY (id_evento) REFERENCES comercial_auditoria(id_evento),
    FOREIGN KEY (anterior) REFERENCES comercial_usuarios(id_usuario),
    FOREIGN KEY (nuevo) REFERENCES comercial_usuarios(id_usuario)
) ENGINE=InnoDB;
