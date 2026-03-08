"""Воркер отправки сообщений в Telegram."""

from __future__ import annotations

from typing import Any

from src.infrastructure.telegram import TelegramHttpClient
from src.workers.base import BaseWorker


class TelegramSenderWorker(BaseWorker):
    """Потребляет задачи из очереди и отправляет сообщения через Telegram API."""

    def __init__(self, rabbitmq_url: str, telegram_client: TelegramHttpClient) -> None:
        super().__init__(
            rabbitmq_url=rabbitmq_url,
            queue_name="telegram_sender_tasks",
            name="telegram_sender",
        )
        self._tg = telegram_client

    async def _process_message(self, message: dict[str, Any]) -> None:
        """Отправить сообщение в Telegram.
        
        Ожидает message формата:
        {
            "chat_id": 123456,
            "text": "Hello world"
        }
        """
        chat_id = message.get("chat_id")
        text = message.get("text")
        
        if not chat_id or not text:
            self._log.warning("Получено некорректное сообщение: %s", message)
            return

        self._log.info("Отправка сообщения в %s", chat_id)
        await self._tg.send_message(chat_id=chat_id, text=text)
