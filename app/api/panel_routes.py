"""Interfaz integrada en EC2; reutiliza los servicios y la autenticación existentes."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse


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
    if asset not in {"panel.css", "panel.js", "demo-control.js", "drive-controller.js", "driving.js", "remote-drive.js"}:
        raise HTTPException(404, "Archivo no encontrado.")
    return FileResponse(PANEL / asset, headers=HEADERS)
