from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.api.catalog_routes import router as catalog_router
from app.api.panel_routes import router as panel_router
from app.api.device_routes import router as device_router
from app.core.config import Settings
from app.core.database import Database
from app.core.errors import ServiceError
from app.repositories.vehicle_repository import VehicleRepository
from app.repositories.catalog_repository import CatalogRepository
from app.services.coordinator import VehicleCoordinator
from app.services.demo_service import DemoService
from app.services.vehicle_service import VehicleService
from app.services.catalog_service import CatalogService
from app.services.device_service import DeviceService
from app.websocket.manager import WebSocketManager


def create_app(settings: Settings | None = None, repository=None, catalog_repository=None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings)
    repository = repository if repository is not None else VehicleRepository(database)
    catalog_repository = catalog_repository if catalog_repository is not None else CatalogRepository(database)
    manager = WebSocketManager()
    coordinator = VehicleCoordinator()
    vehicles = VehicleService(repository, manager, coordinator)
    demos = DemoService(repository, manager, coordinator)
    catalog = CatalogService(catalog_repository, coordinator, manager)
    devices = DeviceService(repository, manager, coordinator)

    @asynccontextmanager
    async def lifespan(app):
        devices.start()
        yield
        await devices.close()
        await demos.close()
        await manager.close()

    application = FastAPI(
        title="API Vehículo IoT — Actividad 2.5", version="1.6.4",
        description="Versión 1.6: aplicación de escritorio Windows, panel de conducción con teclado y mando, firmware ESP8266 WiFi/serial y los 21 SP de MySQL. Administración de vehículos, comandos y DEMO; movimiento individual, historial y transmisión WebSocket. Canal autenticado ESP8266 WiFi/serial con confirmación de salidas; no confirma movimiento mediante sensores.",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.manager = manager
    application.state.vehicle_service = vehicles
    application.state.demo_service = demos
    application.state.catalog_service = catalog
    application.state.device_service = devices

    @application.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    application.include_router(router)
    application.include_router(catalog_router)
    application.include_router(panel_router)
    application.include_router(device_router)
    return application


app = create_app()
