from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_name: str = "IncidentPilot"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    secret_key: str = "change-me-in-env-please-set-a-strong-32-byte-secret"
    encryption_key: str = ""
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    database_url: str = (
        "postgresql+asyncpg://incidentpilot:incidentpilot@localhost:5432/incidentpilot"
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://incidentpilot:incidentpilot@localhost:5672/"
    rabbitmq_exchange: str = "incidentpilot"
    rabbitmq_investigation_queue: str = "incidentpilot.investigation"
    rabbitmq_dlq: str = "incidentpilot.dlq"

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    refresh_cookie_name: str = "incidentpilot_refresh"

    webhook_token: str = "change-me"
    internal_token: str = "change-me"

    bootstrap_admin_email: str = "admin@incidentpilot.io"
    bootstrap_admin_password: str = "ChangeMe123456!"
    bootstrap_sre_email: str = "sre@incidentpilot.io"
    bootstrap_sre_password: str = "ChangeMe123456!"
    bootstrap_viewer_email: str = "viewer@incidentpilot.io"
    bootstrap_viewer_password: str = "ChangeMe123456!"

    alert_aggregation_window_minutes: int = 15
    alert_max_incidents_per_service_per_minute: int = 3

    rate_limit_enabled: bool = True
    login_rate_limit_per_minute: int = 5
    webhook_rate_limit_per_second: int = 50

    demo_mode: bool = False
    remediation_enabled: bool = False
    auto_approve_low_risk: bool = False
    agent_enabled: bool = False

    @field_validator("app_env")
    @classmethod
    def _normalize_env(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("secret_key", "webhook_token", "internal_token")
    @classmethod
    def _strip_secret(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _guard_production_defaults(self) -> Settings:
        if self.app_env == "production":
            if self.secret_key in {"", "change-me-in-env-please-set-a-strong-32-byte-secret"}:
                raise ValueError("SECRET_KEY must be set in production")
            if self.webhook_token in {"", "change-me"}:
                raise ValueError("WEBHOOK_TOKEN must be set in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
