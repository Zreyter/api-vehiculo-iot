from secrets import compare_digest

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False, description="Token local CONTROL_TOKEN de .env")


def check_token(settings, supplied: str) -> None:
    expected = settings.control_token.get_secret_value()
    if not expected:
        raise HTTPException(503, "Configura CONTROL_TOKEN en .env y reinicia la API.")
    if not compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(401, "Token de control inválido o ausente.", headers={"WWW-Authenticate": "Bearer"})


def require_control_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
) -> None:
    check_token(request.app.state.settings, credentials.credentials if credentials else "")
