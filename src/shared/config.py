"""Конфигурация приложения — «Своя игра»."""

from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    """Настройки, загружаемые из переменных окружения / .env файла."""

    # Postgres
    database_url: str = (
        "postgresql+asyncpg://jeopardy:secret@localhost:5432/jeopardy_db"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Telegram
    telegram_bot_token: str = ""

    # App
    debug: bool = False
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"
