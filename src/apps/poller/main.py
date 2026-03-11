import asyncio
import aio_pika
import aiohttp
from pydantic import ValidationError

from src.infrastructure.telegram import TelegramHttpClient
from src.shared.config import AppSettings
from src.shared.logger import get_logger
from src.shared.messages import IncomingTelegramEvent

logger = get_logger(__name__)

async def main():
    settings = AppSettings()
    
    # Инициализация RabbitMQ
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()
        logger.info("✅ Poller подключен к RabbitMQ")
    except aio_pika.AMQPException:
        logger.error("❌ Критическая ошибка подключения к RabbitMQ")
        raise

    telegram_client = TelegramHttpClient(settings.telegram_bot_token)
    await telegram_client.start()

    try:
        await telegram_client.delete_webhook()
        offset = None
        logger.info("📡 Telegram Poller запущен. Начинаю long polling...")

        while True:
            try:
                data = await telegram_client.get_updates(offset=offset)
                
                if not data or not data.get("ok"):
                    logger.error("❌ Ошибка от Telegram: %s", data)
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    
                    try:
                        event = IncomingTelegramEvent(
                            update_id=update["update_id"],
                            data=update
                        )
                        await channel.default_exchange.publish(
                            aio_pika.Message(body=event.model_dump_json().encode()),
                            routing_key="tg_updates",
                        )
                        logger.debug("📥 Отправлен update_id: %s", update["update_id"])
                    except ValidationError as e:
                        logger.error("❌ Ошибка парсинга события Telegram: %s", e)
                        
            except aiohttp.ClientError as e:
                logger.error("❌ Сетевая ошибка при получении обновлений: %s", e)
                await asyncio.sleep(5)
                continue
            except asyncio.CancelledError:
                logger.info("🛑 Остановка Poller...")
                break
            except Exception as e:
                logger.exception("❌ Неожиданная ошибка Poller: %s", e)
                await asyncio.sleep(5)
    finally:
        await telegram_client.close()
        await connection.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Poller остановлен.")
