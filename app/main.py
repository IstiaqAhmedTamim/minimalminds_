from fastapi import FastAPI

from .config import get_settings
from .errors import register_error_handlers
from .routes import router


def create_app() -> FastAPI:
    """Application factory for GridWise."""

    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    register_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
