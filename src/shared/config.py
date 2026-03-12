"""Конфигурация приложения — «Своя игра»."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Настройки, загружаемые из переменных окружения / .env файла."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres
    database_url: str = (
        "postgresql+asyncpg://user:password@localhost:5432/jeopardy_db"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Telegram
    telegram_bot_token: str = ""
    storage_chat_id: int | str = -5165779152  # ID чата для хранения медиафайлов

    # App
    debug: bool = False
    log_level: str = "INFO"

    @field_validator("telegram_bot_token")
    @classmethod
    def token_must_not_be_empty(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN не задан. Укажите токен в .env или переменной окружения."
            )
        return v
