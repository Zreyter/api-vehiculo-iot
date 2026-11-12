"""Genera el código de acceso del panel y Swagger."""

import secrets
import string

if __name__ == "__main__":
    alphabet = string.ascii_letters + string.digits
    print("".join(secrets.choice(alphabet) for _ in range(8)))
