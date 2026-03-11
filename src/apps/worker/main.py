import asyncio
import json
import logging
from typing import Any

import aio_pika
from pydantic import ValidationError

from src.infrastructure.telegram import TelegramHttpClient
from src.shared.config import AppSettings
from src.shared.logger import get_logger
from src.shared.messages import OutgoingTelegramCommand

logger = get_logger(__name__)

async def main():
    settings = AppSettings()
    
    telegram_client = TelegramHttpClient(settings.telegram_bot_token)
    await telegram_client.start()

    connection = None
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()
        
        # Очередь команд (вызов методов Telegram API)
        queue = await channel.declare_queue("tg_commands", auto_delete=False)
        
        logger.info("👷 Telegram Worker запущен. Ожидание команд...")

        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    cmd = OutgoingTelegramCommand.model_validate_json(message.body)
                    
                    method = getattr(telegram_client, cmd.method, None)
                    if not method:
                        logger.error("❌ Метод %s не найден в TelegramHttpClient", cmd.method)
                        return
                        
                    # Выполняем HTTP запрос к Telegram
                    logger.debug("Обрабатываю: %s", cmd.method)
                    result = await method(**cmd.kwargs)
                    
                    # Если нужен ответ (RPC)
                    if cmd.reply_to and cmd.correlation_id:
                        await channel.default_exchange.publish(
                            aio_pika.Message(
                                body=json.dumps(result).encode(),
                                correlation_id=cmd.correlation_id,
                            ),
                            routing_key=cmd.reply_to,
                        )
                except ValidationError as e:
                    logger.error("❌ Неверный формат команды: %s", e)
                except Exception as e:
                    logger.exception("❌ Ошибка при выполнении команды: %s", e)
                    # Если был RPC вызов, отправим ошибку, на клиенте будет Exception
                    err_msg = {"ok": False, "error": str(e)}
                    # Обработка ошибки
                    try:
                        # pylint: disable=used-before-assignment
                        if cmd.reply_to and cmd.correlation_id:
                            await channel.default_exchange.publish(
                                aio_pika.Message(
                                    body=json.dumps(err_msg).encode(),
                                    correlation_id=cmd.correlation_id,
                                ),
                                routing_key=cmd.reply_to,
                            )
                    except Exception as fallback_e:
                        logger.error("Не удалось отправить сообщение об ошибке: %s", fallback_e)

        await queue.consume(process_message)
        
        # Ждём бесконечно
        await asyncio.Future()
        
    finally:
        await telegram_client.close()
        if connection:
            await connection.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Worker остановлен.")
