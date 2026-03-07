"""Базовый класс для фоновых воркеров-потребителей очередей."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from src.logger import get_logger


class BaseWorker(ABC):
    """Абстракция воркера, потребляющего сообщения из очереди."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._running = False
        self._log = get_logger(f"worker.{name}")

    async def start(self) -> None:
        """Запустить цикл обработки."""
        self._running = True
        self._log.info("Воркер %s запущен", self.name)
        try:
            await self._consume()
        except asyncio.CancelledError:
            self._log.info("Воркер %s остановлен (CancelledError)", self.name)
        finally:
            self._running = False

    async def stop(self) -> None:
        """Остановить воркер."""
        self._running = False
        self._log.info("Воркер %s: запрошена остановка", self.name)

    @abstractmethod
    async def _consume(self) -> None:
        """Основной цикл потребления сообщений из очереди.

        Реализация должна проверять ``self._running`` и завершаться,
        когда флаг сброшен.
        """
        ...

    @abstractmethod
    async def _process_message(self, message: dict[str, Any]) -> None:
        """Обработать одно сообщение из очереди."""
        ...

"""Воркер отправки сообщений в Telegram."""

from __future__ import annotations

from typing import Any

from src.bot.worker import BaseWorker
from src.infrastructure import TelegramHttpClient


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
