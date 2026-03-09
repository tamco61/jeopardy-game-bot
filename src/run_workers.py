"""Точка входа для запуска фоновых воркеров."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.database.base import build_engine, build_session_factory
from src.infrastructure.database.postgres_repo import PostgresGameRepository
from src.infrastructure.telegram import TelegramHttpClient
from src.shared.config import AppSettings
from src.workers.siq_parser_worker import SiqParserWorker
from src.workers.telegram_sender_worker import TelegramSenderWorker
from src.shared.logger import get_logger

logger = get_logger(__name__)


async def main() -> None:
    logger.info("🚀 Запуск фоновых воркеров...")

    settings = AppSettings()

    # 1. Запуск БД
    try:
        engine = build_engine(settings.database_url)
        session_factory = build_session_factory(engine)
        game_repo = PostgresGameRepository(session_factory)
        logger.info("✅ Подключено к PostgreSQL (для парсера)")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка БД: {e}")
        return

    # 2. Запуск Telegram клиента
    telegram_client = TelegramHttpClient(settings.telegram_bot_token)
    await telegram_client.start()

    # 3. Инициализация воркеров
    parser_worker = SiqParserWorker(
        rabbitmq_url=settings.rabbitmq_url,
        game_repo=game_repo,
    )

    sender_worker = TelegramSenderWorker(
        rabbitmq_url=settings.rabbitmq_url,
        telegram_client=telegram_client,
    )

    logger.info("⏳ Воркеры готовы. Ожидание задач из RabbitMQ...")

    # Запускаем все воркеры конкурентно
    try:
        await asyncio.gather(
            parser_worker.start(),
            sender_worker.start(),
        )
    except asyncio.CancelledError:
        logger.info("🛑 Остановка воркеров (Отмена)...")
    finally:
        await parser_worker.stop()
        await sender_worker.stop()
        await telegram_client.close()
        logger.info("💤 Все ресурсы освобождены.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Воркеры остановлены (Ctrl+C).")
