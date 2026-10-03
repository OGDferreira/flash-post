import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.core.database import dispose_engine, get_session_factory
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.rate_limit import LoginRateLimiter
from app.legal import router as legal_router
from app.instagram.router import router as instagram_router

settings = get_settings()
logger = logging.getLogger(__name__)


class _OAuthCallbackAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if (
            isinstance(args, tuple)
            and len(args) >= 3
            and isinstance(args[2], str)
            and args[2].split("?", 1)[0] == "/api/instagram/callback"
        ):
            sanitized_args = list(args)
            sanitized_args[2] = "/api/instagram/callback"
            record.args = tuple(sanitized_args)
        return True


logging.getLogger("uvicorn.access").addFilter(_OAuthCallbackAccessLogFilter())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.validate_runtime()
    yield
    await dispose_engine()


async def check_database_readiness() -> bool:
    try:
        async with get_session_factory()() as db:
            await db.execute(text("SELECT 1"))
    except (SQLAlchemyError, RuntimeError) as exc:
        logger.error("Readiness database check failed (%s).", type(exc).__name__)
        return False
    return True


def create_app(static_assets_dir: Path | None = None) -> FastAPI:
    application = FastAPI(
        title="FlashPost",
        summary="Operations platform for Instagram publishing and analytics.",
        version="0.2.0",
        lifespan=lifespan,
    )
    application.state.login_rate_limiter = LoginRateLimiter(
        get_settings().login_max_attempts,
        get_settings().login_window_seconds,
    )
    application.state.registration_rate_limiter = LoginRateLimiter(
        get_settings().registration_max_attempts,
        get_settings().registration_window_seconds,
    )
    application.state.nickname_check_rate_limiter = LoginRateLimiter(
        get_settings().nickname_check_max_attempts,
        get_settings().nickname_check_window_seconds,
    )
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_signing_key,
        session_cookie="flashpost_session",
        max_age=settings.session_max_age_seconds,
        same_site="lax",
        https_only=settings.is_production or settings.public_base_url.startswith("https://"),
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts,
    )
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(instagram_router)
    application.include_router(legal_router)

    @application.get("/readiness", tags=["health"])
    async def readiness(
        database_ready: bool = Depends(check_database_readiness),
    ) -> JSONResponse:
        if not database_ready:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "database": "unavailable"},
            )
        return JSONResponse(content={"status": "ready", "database": "ok"})

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "Request validation failed."},
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled request error (%s).", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred."},
        )

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    frontend_dir = static_assets_dir or Path(__file__).parent / "static"
    index_file = frontend_dir / "index.html"
    if index_file.is_file():
        resolved_frontend_dir = frontend_dir.resolve()

        @application.get("/{asset_path:path}", include_in_schema=False)
        async def frontend_fallback(asset_path: str) -> FileResponse:
            if asset_path == "api" or asset_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found.")
            candidate = (frontend_dir / asset_path).resolve()
            if not candidate.is_relative_to(resolved_frontend_dir):
                raise HTTPException(status_code=404, detail="Not found.")
            if candidate.is_file():
                return FileResponse(candidate)
            if Path(asset_path).suffix:
                raise HTTPException(status_code=404, detail="Not found.")
            return FileResponse(index_file)

    return application


app = create_app()
