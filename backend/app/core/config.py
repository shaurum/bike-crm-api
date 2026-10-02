from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn, RedisDsn
from typing import List, Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "Bike CRM API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = Field(..., min_length=32)

    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    BACKEND_WORKERS: int = 1

    POSTGRES_SERVER: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "bike_crm"
    POSTGRES_PASSWORD: str = "bike_crm_dev_password"
    POSTGRES_DB: str = "bike_crm"

    @property
    def DATABASE_URL(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=f"/{self.POSTGRES_DB}",
        )

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> RedisDsn:
        return RedisDsn.build(
            scheme="redis",
            username=None,
            password=self.REDIS_PASSWORD or None,
            host=self.REDIS_HOST,
            port=self.REDIS_PORT,
            path=f"/{self.REDIS_DB}",
        )

    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"
    CELERY_WORKER_CONCURRENCY: int = 2

    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    PUBLIC_API_KEY: str = "dev-public-api-key-change-in-production"
    WIDGET_CORS_ORIGINS: List[str] = ["*"]

    AVITO_CLIENT_ID: Optional[str] = None
    AVITO_CLIENT_SECRET: Optional[str] = None
    AVITO_REDIRECT_URI: Optional[str] = None
    AVITO_WEBHOOK_SECRET: Optional[str] = None

    VK_GROUP_ID: Optional[str] = None
    VK_CLIENT_ID: Optional[str] = None
    VK_CLIENT_SECRET: Optional[str] = None
    VK_CALLBACK_SECRET: Optional[str] = None
    VK_CONFIRMATION_TOKEN: Optional[str] = None

    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None
    TELEGRAM_ADMIN_CHAT_IDS: List[int] = []

    EMAIL_PROVIDER: str = "resend"
    RESEND_API_KEY: Optional[str] = None
    SENDGRID_API_KEY: Optional[str] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: str = "noreply@localhost"

    S3_ENDPOINT: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_BUCKET: str = "bike-crm-backups"
    S3_REGION: str = "ru-1"

    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_ENABLED: bool = False

    CONTRACT_TEMPLATE_PATH: str = "/app/templates/contract.html"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()