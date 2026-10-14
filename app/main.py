from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import Settings
from app.core.database import Database
from app.core.errors import ServiceError
from app.repositories.vehicle_repository import VehicleRepository
from app.services.coordinator import VehicleCoordinator
from app.services.demo_service import DemoService
from app.services.vehicle_service import VehicleService
from app.websocket.manager import WebSocketManager


def create_app(settings: Settings | None = None, repository=None) -> FastAPI:
    settings = settings or Settings()
    repository = repository if repository is not None else VehicleRepository(Database(settings))
    manager = WebSocketManager()
    coordinator = VehicleCoordinator()
    vehicles = VehicleService(repository, manager, coordinator)
    demos = DemoService(repository, manager, coordinator)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await demos.close()
        await manager.close()

    application = FastAPI(
        title="API Vehículo IoT — Actividad 2.5", version="0.1.0",
        description="Laboratorio local: movimiento individual, historial y transmisión DEMO. Eventos lógicos; ESP8266 todavía no integrado.",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.manager = manager
    application.state.vehicle_service = vehicles
    application.state.demo_service = demos

    @application.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    application.include_router(router)
    return application


app = create_app()
