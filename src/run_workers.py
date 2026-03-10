"""Точка входа для запуска фоновых воркеров."""

import asyncio

# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.database.base import build_engine, build_session_factory
from src.infrastructure.database.repositories.package import PackageRepository
from src.infrastructure.telegram import TelegramHttpClient
from src.shared.config import AppSettings
from src.shared.logger import get_logger
from src.workers.siq_parser_worker import SiqParserWorker
from src.workers.telegram_sender_worker import TelegramSenderWorker

logger = get_logger(__name__)


async def main() -> None:
    settings = AppSettings()

    logger.info("🚀 Запуск фоновых воркеров...")

    # 1. Запуск БД
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    package_repo = PackageRepository(session_factory)
    logger.info("✅ Подключено к PostgreSQL (для парсера)")

    # 2. Запуск Telegram клиента
    telegram_client = TelegramHttpClient(settings.telegram_bot_token)
    await telegram_client.start()

    # 3. Инициализация воркеров
    parser_worker = SiqParserWorker(
        rabbitmq_url=settings.rabbitmq_url,
        package_repo=package_repo,
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
