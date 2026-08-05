from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    app_secret_key: SecretStr = SecretStr("change-me-in-production")
    database_url: str = "postgresql+asyncpg://tg_bot:tg_bot@localhost:5432/tg_bot"
    redis_url: str = "redis://localhost:6379/0"
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    telegram_bot_token: SecretStr | None = None
    telegram_webhook_url: str | None = None
    telegram_webhook_secret: SecretStr | None = None

    ai_provider: Literal["fake", "openai"] = "fake"
    ai_api_key: SecretStr | None = None
    ai_model: str = "gpt-5.6-luna"
    ai_embedding_model: str | None = None

    storage_driver: Literal["local", "s3"] = "local"
    local_storage_path: Path = Path("storage")
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None

    remotive_api_url: str = "https://remotive.com/api/remote-jobs"
    greenhouse_boards: str = ""
    lever_sites: str = ""
    max_resume_size_mb: int = Field(default=10, ge=1, le=50)
    default_match_threshold: int = Field(default=70, ge=0, le=100)

    log_level: str = "INFO"
    admin_username: str = "admin"
    admin_password_hash: SecretStr | None = None
    beta_mode: bool = True
    beta_telegram_ids: str = ""
    metrics_enabled: bool = True

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def beta_user_ids(self) -> frozenset[int]:
        if not self.beta_telegram_ids.strip():
            return frozenset()
        return frozenset(int(item.strip()) for item in self.beta_telegram_ids.split(","))

    @model_validator(mode="after")
    def validate_provider_and_production_settings(self) -> Self:
        if self.ai_provider == "openai" and not _has_secret(self.ai_api_key):
            raise ValueError("AI_API_KEY is required when AI_PROVIDER=openai")

        if not self.is_production:
            return self

        if self.app_debug:
            raise ValueError("APP_DEBUG must be false in production")
        if self.app_secret_key.get_secret_value() == "change-me-in-production":
            raise ValueError("APP_SECRET_KEY must be replaced in production")
        if not _has_secret(self.telegram_bot_token):
            raise ValueError("TELEGRAM_BOT_TOKEN is required in production")
        if not self.telegram_webhook_url or not self.telegram_webhook_url.startswith("https://"):
            raise ValueError("TELEGRAM_WEBHOOK_URL must use HTTPS in production")
        if not _has_secret(self.telegram_webhook_secret, minimum_length=32):
            raise ValueError("TELEGRAM_WEBHOOK_SECRET must contain at least 32 characters")
        if self.storage_driver != "s3":
            raise ValueError("STORAGE_DRIVER must be s3 in production")
        if not all(
            (
                self.s3_endpoint,
                self.s3_bucket,
                _has_secret(self.s3_access_key),
                _has_secret(self.s3_secret_key),
            )
        ):
            raise ValueError("S3 configuration is incomplete")
        if not _has_secret(self.admin_password_hash):
            raise ValueError("ADMIN_PASSWORD_HASH is required in production")
        return self


def _has_secret(value: SecretStr | None, *, minimum_length: int = 1) -> bool:
    return value is not None and len(value.get_secret_value()) >= minimum_length


@lru_cache
def get_settings() -> Settings:
    return Settings()
