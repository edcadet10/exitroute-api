"""Environment-backed configuration with production safety checks."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRETS = {
    "dev-bootstrap-token-change-me",
    "dev-cursor-secret-change-me-32-bytes",
    "dev-key-pepper-change-me-32-bytes",
    "dev-webhook-secret-change-me-32-bytes",
}


class Settings(BaseSettings):
    """Runtime settings. All secrets are environment-owned, never committed."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="EXITROUTE_",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://exitroute:exitroute@localhost:5432/exitroute"
    )
    public_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    bootstrap_admin_enabled: bool = True
    bootstrap_admin_token: SecretStr = SecretStr("dev-bootstrap-token-change-me")
    api_key_pepper: SecretStr = SecretStr("dev-key-pepper-change-me-32-bytes")
    cursor_secret: SecretStr = SecretStr("dev-cursor-secret-change-me-32-bytes")
    webhook_master_secret: SecretStr = SecretStr("dev-webhook-secret-change-me-32-bytes")
    rate_limit_per_minute: int = Field(default=120, ge=1, le=100_000)
    cursor_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)
    webhook_timeout_seconds: float = Field(default=8.0, ge=1.0, le=30.0)
    webhook_max_attempts: int = Field(default=8, ge=1, le=20)
    webhook_lease_seconds: int = Field(default=60, ge=10, le=600)
    review_window_days: int = Field(default=30, ge=1, le=365)
    cors_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_unsafe_production_defaults(self) -> Settings:
        if self.environment != "production":
            return self
        if self.bootstrap_admin_enabled:
            raise ValueError(
                "production requires bootstrap admin HTTP authentication to be disabled"
            )
        secret_fields = (self.api_key_pepper, self.cursor_secret, self.webhook_master_secret)
        revealed = [value.get_secret_value() for value in secret_fields]
        if any(value in _DEV_SECRETS or len(value) < 32 for value in revealed):
            raise ValueError("production secrets must be unique and at least 32 characters")
        if len(set(revealed)) != len(revealed):
            raise ValueError("production secrets must not be reused")
        if self.public_base_url.scheme != "https":
            raise ValueError("production public base URL must use HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one immutable settings snapshot per process."""

    return Settings()
