"""Ejecutar en la raíz con python -m scripts.crear_admin_comercial."""
from getpass import getpass

from app.core.claves_comerciales import proteger
from app.core.config import Settings
from app.core.database import Database


def main():
    settings = Settings()
    correo = input("Correo del administrador: ").strip().lower()
    nombre = input("Nombre: ").strip()
    if not 3 <= len(correo) <= 254 or "@" not in correo or not 1 <= len(nombre) <= 120:
        raise SystemExit("Revisa el correo y el nombre.")
    clave = getpass("Contraseña (12–256 caracteres): ")
    if not 12 <= len(clave) <= 256 or clave != getpass("Confirma la contraseña: "):
        raise SystemExit("Revisa la longitud y confirmación de la contraseña.")
    with Database(settings).transaction(write=True) as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO comercial_usuarios(correo,nombre,clave_hash,rol)
                       VALUES (%s,%s,%s,'admin')""", (correo, nombre, proteger(clave)))
    print("Cuenta administrativa creada.")


if __name__ == "__main__":
    main()
