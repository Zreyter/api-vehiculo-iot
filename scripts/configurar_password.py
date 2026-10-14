"""Ejecutar personalmente desde la raíz: python scripts/configurar_password.py."""
from getpass import getpass
from pathlib import Path

from dotenv import set_key


def main():
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        raise SystemExit("Primero crea .env a partir de .env.example.")
    password = getpass("Contraseña MySQL (no se mostrará): ")
    if not password:
        raise SystemExit("No se guardó una contraseña vacía.")
    if password != getpass("Repite la contraseña: "):
        raise SystemExit("No coinciden; no se hicieron cambios.")
    set_key(str(path), "MYSQL_PASSWORD", password, quote_mode="always")
    path.chmod(0o600)
    print("Contraseña guardada localmente. Reinicia la API si estaba ejecutándose.")


if __name__ == "__main__":
    main()
