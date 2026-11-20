-- Ampliación aditiva para MySQL 8. Aplicar sobre el esquema restaurado.
CREATE TABLE IF NOT EXISTS comercial_usuarios (
    id_usuario INT PRIMARY KEY AUTO_INCREMENT,
    correo VARCHAR(254) NOT NULL UNIQUE,
    nombre VARCHAR(120) NOT NULL,
    clave_hash VARCHAR(160) CHARACTER SET ascii NOT NULL,
    rol ENUM('admin','usuario') NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fallos TINYINT UNSIGNED NOT NULL DEFAULT 0,
    bloqueo_hasta DATETIME NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comercial_sesiones (
    token_hash BINARY(32) PRIMARY KEY,
    id_usuario INT NOT NULL,
    vence DATETIME NOT NULL,
    FOREIGN KEY (id_usuario) REFERENCES comercial_usuarios(id_usuario),
    INDEX (vence)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comercial_modelos (
    id_modelo INT PRIMARY KEY AUTO_INCREMENT,
    nombre VARCHAR(80) NOT NULL UNIQUE,
    descripcion VARCHAR(255) NOT NULL DEFAULT '',
    activo BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comercial_unidades (
    id_vehiculo INT PRIMARY KEY,
    id_modelo INT NOT NULL,
    estado ENUM('sin_clasificar','disponible','asignado','exhibicion','inactivo') NOT NULL DEFAULT 'sin_clasificar',
    FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo) ON DELETE RESTRICT,
    FOREIGN KEY (id_modelo) REFERENCES comercial_modelos(id_modelo) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comercial_auditoria (
    id_evento BIGINT PRIMARY KEY AUTO_INCREMENT,
    fecha TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    actor INT NOT NULL,
    accion VARCHAR(48) NOT NULL,
    recurso VARCHAR(32) NOT NULL,
    id_recurso INT NOT NULL,
    resultado VARCHAR(20) NOT NULL,
    FOREIGN KEY (actor) REFERENCES comercial_usuarios(id_usuario),
    INDEX (recurso, id_recurso, id_evento)
) ENGINE=InnoDB;
