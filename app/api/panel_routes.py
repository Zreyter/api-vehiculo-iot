"""Interfaz integrada en EC2; reutiliza los servicios y la autenticación existentes."""
import base64
import binascii
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse

from app.core.errors import ServiceError
from app.core.security import check_token

router = APIRouter()
PANEL = Path(__file__).resolve().parents[1] / "panel"
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
        "frame-ancestors 'self'; form-action 'self'"
    ),
}


@router.get("/panel", include_in_schema=False)
async def panel_redirect():
    return RedirectResponse("/panel/")


@router.get("/panel/", include_in_schema=False)
async def panel():
    return FileResponse(PANEL / "index.html", headers=HEADERS)


@router.get("/panel/{asset}", include_in_schema=False)
async def panel_asset(asset: str):
    if asset not in {"panel.css", "panel.js", "drive-controller.js", "driving.js", "remote-drive.js"}:
        raise HTTPException(404, "Archivo no encontrado.")
    return FileResponse(PANEL / asset, headers=HEADERS)


@router.websocket("/panel/ws/vehiculos/{id_vehiculo}")
async def panel_socket(socket: WebSocket, id_vehiculo: int):
    """El navegador envía el token en un subprotocolo, nunca en la URL."""
    client = None
    try:
        origin_scheme = "https" if socket.url.scheme == "wss" else "http"
        expected_origin = f"{origin_scheme}://{socket.headers.get('host', '')}"
        if socket.headers.get("origin") != expected_origin:
            raise HTTPException(403, "Origen no permitido.")
        protocols = socket.scope.get("subprotocols", [])
        encoded_tokens = [p[6:] for p in protocols if p.startswith("token.")]
        if "iot" not in protocols or len(encoded_tokens) != 1:
            raise HTTPException(401, "Token requerido.")
        encoded = encoded_tokens[0]
        if not encoded or len(encoded) > 4096:
            raise HTTPException(401, "Token inválido.")
        try:
            supplied = base64.b64decode(
                encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
            ).decode("ascii")
        except (ValueError, binascii.Error, UnicodeError) as exc:
            raise HTTPException(401, "Token inválido.") from exc
        check_token(socket.app.state.settings, supplied)
        if id_vehiculo <= 0:
            raise HTTPException(422, "Identificador inválido.")
        client = await socket.app.state.vehicle_service.connect(
            id_vehiculo, socket, subprotocol="iot"
        )
        while True:
            message = await socket.receive()
            if message["type"] == "websocket.disconnect":
                break
    except (HTTPException, ServiceError):
        await socket.close(code=1008)
    except WebSocketDisconnect:
        pass
    finally:
        if client is not None:
            await socket.app.state.manager.disconnect(id_vehiculo, client)
