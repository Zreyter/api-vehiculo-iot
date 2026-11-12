from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse

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
from app.websocket.gateway import router as socket_router


def create_app(settings: Settings | None = None, repository=None, catalog_repository=None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings)
    repository = repository if repository is not None else VehicleRepository(database)
    catalog_repository = catalog_repository if catalog_repository is not None else CatalogRepository(database)
    manager = WebSocketManager()
    coordinator = VehicleCoordinator()
    vehicles = VehicleService(repository, manager, coordinator)
    catalog = CatalogService(catalog_repository, coordinator, manager)
    devices = DeviceService(repository, manager, coordinator)
    demos = DemoService(repository, manager, coordinator, devices)

    @asynccontextmanager
    async def lifespan(app):
        devices.start()
        yield
        await demos.close()
        await devices.close()
        await manager.close()

    application = FastAPI(
        title="API Vehículo IoT - Actividad 2.5", version="2.0.2",
        description=(
            "Catálogo de vehículos, comandos y demos sobre 21 procedimientos de MySQL. "
            "Control web, monitor y ESP8266 comparten /ws/vehiculos/{id_vehiculo}. "
            "La confirmación de la placa corresponde a las salidas eléctricas."
        ),
        lifespan=lifespan, docs_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.browser_origins,
        allow_methods=["GET"],
        allow_headers=["Authorization"],
    )

    @application.get("/docs", include_in_schema=False)
    async def swagger(request: Request):
        prefix = request.scope.get("root_path", "").rstrip("/")
        return get_swagger_ui_html(
            openapi_url=prefix + "/openapi.json", title="Excavadora IoT | Swagger",
            swagger_favicon_url=prefix + "/favicon.png",
        )

    @application.get("/favicon.png", include_in_schema=False)
    async def favicon():
        icon = Path(__file__).resolve().parents[1] / "control-iot/assets/favicon/excavadora-192.png"
        return FileResponse(icon, media_type="image/png")
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
    application.include_router(socket_router)
    return application


app = create_app()
