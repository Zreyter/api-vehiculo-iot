import hashlib
import secrets


def huella(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def derivar(clave: str, sal: bytes) -> bytes:
    return hashlib.scrypt(clave.encode("utf-8"), salt=sal, n=32768, r=8, p=1,
                          maxmem=64 * 1024 * 1024, dklen=32)


def proteger(clave: str) -> str:
    sal = secrets.token_bytes(16)
    return "scrypt1$" + sal.hex() + "$" + derivar(clave, sal).hex()


def coincide(clave: str, guardada: str) -> bool:
    version, sal, valor = guardada.split("$")
    return version == "scrypt1" and secrets.compare_digest(derivar(clave, bytes.fromhex(sal)), bytes.fromhex(valor))
