"""FastAPI application entry point."""

from fastapi import FastAPI

from server.api.health import router as health_router


def create_app() -> FastAPI:
    # Interactive docs and OpenAPI are disabled: no debug endpoints.
    app = FastAPI(title="VANTA", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(health_router)
    return app


app = create_app()
