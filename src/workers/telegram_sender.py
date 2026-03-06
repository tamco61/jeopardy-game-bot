"""Воркер отправки сообщений в Telegram."""

from __future__ import annotations

from typing import Any

from src.infrastructure.telegram.http_client import TelegramHttpClient
from src.workers.base_worker import BaseWorker


class TelegramSenderWorker(BaseWorker):
    """Потребляет задачи из очереди и отправляет сообщения через Telegram API.

    TODO: реализовать _consume (подключение к RabbitMQ)
    и _process_message (отправка через TelegramHttpClient).
    """

    def __init__(self, telegram_client: TelegramHttpClient) -> None:
        super().__init__(name="telegram_sender")
        self._tg = telegram_client

    async def _consume(self) -> None:
        """Подключиться к очереди и начать потреблять.

        TODO: реализовать.
        """
        raise NotImplementedError

    async def _process_message(self, message: dict[str, Any]) -> None:
        """Отправить сообщение в Telegram.

        TODO: реализовать.
        """
        raise NotImplementedError
