from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title="FlashPost",
    summary="Operations platform for Instagram publishing and analytics.",
    version="0.1.0",
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_hosts,
)
app.include_router(health_router)

static_dir = Path(__file__).parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
