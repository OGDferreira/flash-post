from functools import lru_cache
from pathlib import Path
import secrets
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    environment: str = "development"
    public_base_url: str = "https://flashpost.onrender.com"
    allowed_hosts: str = "flashpost.onrender.com,localhost,127.0.0.1,testserver"
    instagram_webhook_verify_token: SecretStr | None = None
    database_url: SecretStr | None = None
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    instagram_publishing_enabled: bool = False
    session_secret: SecretStr | None = None
    master_encryption_key: SecretStr | None = None
    session_max_age_seconds: Annotated[int, Field(ge=900, le=2592000)] = 2592000
    login_max_attempts: Annotated[int, Field(ge=3, le=20)] = 5
    login_window_seconds: Annotated[int, Field(ge=60, le=3600)] = 900
    registration_max_attempts: Annotated[int, Field(ge=3, le=20)] = 5
    registration_window_seconds: Annotated[int, Field(ge=60, le=86400)] = 3600
    nickname_check_max_attempts: Annotated[int, Field(ge=10, le=200)] = 60
    nickname_check_window_seconds: Annotated[int, Field(ge=60, le=3600)] = 900

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=Path(__file__).resolve().parents[3] / ".env",
        extra="ignore",
    )

    @field_validator(
        "database_url",
        "instagram_webhook_verify_token",
        "supabase_service_role_key",
        "session_secret",
        "master_encryption_key",
        mode="before",
    )
    @classmethod
    def empty_secrets_are_missing(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @field_validator("supabase_url", mode="before")
    @classmethod
    def normalize_supabase_url(cls, value):
        if isinstance(value, str):
            value = value.strip().rstrip("/")
            if not value:
                return None
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def session_signing_key(self) -> str:
        if self.session_secret is not None:
            return self.session_secret.get_secret_value()
        if self.is_production:
            raise RuntimeError("SESSION_SECRET must be configured in production.")
        return _development_session_secret

    def validate_runtime(self) -> None:
        if self.is_production and self.session_secret is None:
            raise RuntimeError("SESSION_SECRET must be configured in production.")
        if self.instagram_publishing_enabled and (
            self.supabase_url is None or self.supabase_service_role_key is None
        ):
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required when "
                "INSTAGRAM_PUBLISHING_ENABLED is true."
            )

    def database_url_value(self) -> str:
        if self.database_url is None:
            raise RuntimeError("DATABASE_URL is required for database operations.")
        raw_url = self.database_url.get_secret_value().strip()
        parsed_url = make_url(raw_url)
        if parsed_url.get_backend_name() != "postgresql":
            return raw_url

        driver_name = parsed_url.drivername
        if driver_name in {"postgres", "postgresql"}:
            driver_name = "postgresql+asyncpg"
        query = {
            key: value
            for key, value in parsed_url.query.items()
            if key.casefold() not in {"ssl", "sslmode"}
        }
        return parsed_url.set(drivername=driver_name, query=query).render_as_string(
            hide_password=False
        )


_development_session_secret = secrets.token_urlsafe(48)

@lru_cache
def get_settings() -> Settings:
    return Settings()
