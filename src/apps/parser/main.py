import asyncio

from src.application.media_uploader import TelegramMediaUploader
from src.infrastructure.database.base import build_engine, build_session_factory
from src.infrastructure.database.repositories.package import PackageRepository
from src.infrastructure.telegram import TelegramHttpClient
from src.shared.config import AppSettings
from src.shared.logger import get_logger
from src.workers.siq_parser_worker import SiqParserWorker

logger = get_logger(__name__)


async def main() -> None:
    settings = AppSettings()

    logger.info("🚀 Запуск SIQ Parser Worker...")

    # 1. Подключение к БД
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    package_repo = PackageRepository(session_factory)

    # 2. Telegram клиент для взаимодействия с API
    telegram_client = TelegramHttpClient(settings.telegram_bot_token)
    await telegram_client.start()

    try:
        # 3. Сервис загрузки медиа
        storage_chat_id = getattr(settings, "storage_chat_id", None)

        # ⚠️ Fail-Fast: Если чата нет, воркер не должен работать
        if not storage_chat_id:
            logger.error("❌ STORAGE_CHAT_ID не настроен в конфигурации! Загрузка медиа невозможна.")
            raise ValueError("Missing STORAGE_CHAT_ID in environment variables")

        media_uploader = TelegramMediaUploader(
            tg_client=telegram_client,
            storage_chat_id=storage_chat_id,
        )

        # 4. Инициализация воркера
        parser_worker = SiqParserWorker(
            rabbitmq_url=settings.rabbitmq_url,
            package_repo=package_repo,
            media_uploader=media_uploader,
        )

        # 5. Запуск
        logger.info("✅ Воркер успешно инициализирован и слушает очередь RabbitMQ...")
        await parser_worker.start()

    except asyncio.CancelledError:
        logger.info("🛑 Остановка воркера (получен сигнал отмены)...")
    except Exception:
        logger.exception("💥 Критическая ошибка в работе воркера")
    finally:
        logger.info("🧹 Очистка ресурсов...")

        # Безопасно останавливаем воркер, если он был создан
        if 'parser_worker' in locals():
            await parser_worker.stop()

        # Закрываем сессию aiohttp
        await telegram_client.close()

        # ВАЖНО: Закрываем пулы соединений базы данных (защита от connection leaks)
        await engine.dispose()

        logger.info("💤 Ресурсы освобождены. Работа завершена.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Parser Worker остановлен пользователем (Ctrl+C).")