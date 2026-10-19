from decimal import Decimal
from functools import lru_cache
import logging
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
    # Web Push (optional): when unset, keys are generated once and stored
    # encrypted in system_settings. Subject must be a mailto: or https: URL.
    vapid_private_key: SecretStr | None = None
    smokepay_api_key: SecretStr | None = None
    smokepay_webhook_secret: SecretStr | None = None
    # Key with the "Saques" scope; falls back to SMOKEPAY_API_KEY when unset.
    smokepay_withdraw_api_key: SecretStr | None = None
    # SmokePay takes its withdrawal fee from the balance on top of the amount.
    smokepay_withdraw_fee: Decimal = Decimal("3.00")
    smokepay_base_url: str = "https://smokepay.com.br"
    # SnakePay (second PIX gateway): the platform owner's key and webhook secret.
    snakepay_api_key: SecretStr | None = None
    snakepay_webhook_secret: SecretStr | None = None
    snakepay_base_url: str = "https://snakepay.com.br/api/public/v1"
    vapid_subject: str | None = None
    daily_views_goal_check_minutes: Annotated[int, Field(ge=5, le=240)] = 15
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
        "vapid_private_key",
        "snakepay_api_key",
        "snakepay_webhook_secret",
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
    def vapid_subject_value(self) -> str:
        subject = (self.vapid_subject or "").strip()
        if subject.startswith(("mailto:", "https://")):
            return subject
        return self.public_base_url.rstrip("/")

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
        if self.is_production and self.master_encryption_key is None:
            # Not fatal (existing deploys keep booting), but Instagram tokens,
            # Meta app secrets and e-mail credentials cannot be stored or read.
            logging.getLogger(__name__).error(
                "MASTER_ENCRYPTION_KEY is not configured; encrypted credentials are unavailable."
            )
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
