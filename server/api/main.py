"""FastAPI application entry point."""

from fastapi import FastAPI

from server.api.devices import router as devices_router
from server.api.health import router as health_router
from server.api.public import router as public_router
from server.api.status import router as status_router


def create_app() -> FastAPI:
    # Interactive docs and OpenAPI are disabled: no debug endpoints.
    app = FastAPI(title="VANTA", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(health_router)
    app.include_router(status_router)
    app.include_router(devices_router)
    app.include_router(public_router)
    return app


app = create_app()
