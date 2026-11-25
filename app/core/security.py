import asyncio
from secrets import compare_digest

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False, description="Sesión de comprador o administrador en modo comercial. Código compartido en 4.1/4.2.")


def check_token(settings, supplied: str) -> None:
    expected = settings.control_token.get_secret_value()
    if not expected:
        raise HTTPException(503, "Configura CONTROL_TOKEN en .env y reinicia la API.")
    if not compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(401, "Token de control inválido o ausente.", headers={"WWW-Authenticate": "Bearer"})


def unidad_de_ruta(request):
    valor = request.path_params.get("id_vehiculo")
    if valor is None:
        return None
    if not str(valor).isascii() or not str(valor).isdecimal() or len(str(valor)) > 16:
        raise HTTPException(422, "Identificador de vehículo inválido.")
    return int(valor)


async def permiso_operativo(app, token, unidad):
    if not token:
        raise HTTPException(401, "Inicia sesión para acceder a esta unidad.")
    return await asyncio.to_thread(app.comercial.permiso_unidad, token, unidad)


async def require_control_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
) -> None:
    app = request.app.state
    token = credentials.credentials if credentials else ""
    if not app.settings.comercial_habilitado:
        check_token(app.settings, token)
        yield
        return
    unidad = unidad_de_ruta(request)
    async with app.permisos.operacion(unidad):
        # Los catálogos operativos se leen por unidad. El CRUD global es administrativo.
        ruta = request.scope["route"].path
        if ruta.startswith("/admin/") and (request.method != "GET" or unidad is None):
            await asyncio.to_thread(app.comercial.verificar_admin, token)
        elif ruta == "/admin/vehiculos/{id_vehiculo}/comandos":
            # El administrador necesita leer el catálogo que puede modificar.
            await asyncio.to_thread(app.comercial.permiso_unidad, token, unidad, permitir_admin=True)
        else:
            await permiso_operativo(app, token, unidad)
        yield


async def acceso_historial(request: Request, credentials: HTTPAuthorizationCredentials | None = Security(bearer)):
    if not request.app.state.settings.comercial_habilitado:
        yield
        return
    unidad = unidad_de_ruta(request)
    async with request.app.state.permisos.operacion(unidad):
        await permiso_operativo(request.app.state, credentials.credentials if credentials else "", unidad)
        yield
