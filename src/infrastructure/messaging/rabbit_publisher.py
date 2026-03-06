"""Реализация IMessagePublisher поверх RabbitMQ.

Требует установки пакета ``aio-pika``: pip install aio-pika.
"""

from __future__ import annotations

import json
from typing import Any

from src.application.interfaces.message_publisher import IMessagePublisher


class RabbitMQPublisher(IMessagePublisher):
    """Публикация сообщений в RabbitMQ через aio-pika."""

    def __init__(self, rabbitmq_url: str) -> None:
        self._url = rabbitmq_url
        self._connection: Any = None
        self._channel: Any = None

    async def connect(self) -> None:
        """Установить соединение и открыть канал."""
        import aio_pika  # noqa: PLC0415 — ленивый импорт

        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()

    async def disconnect(self) -> None:
        """Закрыть канал и соединение."""
        if self._channel:
            await self._channel.close()
        if self._connection:
            await self._connection.close()

    async def publish(self, routing_key: str, message: dict[str, Any]) -> None:
        """Опубликовать JSON-сообщение в exchange по умолчанию."""
        if self._channel is None:
            msg = "Publisher не подключён. Вызовите connect() перед publish()."
            raise RuntimeError(msg)

        import aio_pika  # noqa: PLC0415

        body = json.dumps(message, ensure_ascii=False).encode()
        await self._channel.default_exchange.publish(
            aio_pika.Message(body=body),
            routing_key=routing_key,
        )
