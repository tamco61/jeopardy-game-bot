"""Порт для публикации сообщений в очередь (RabbitMQ)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IMessagePublisher(ABC):
    """Абстракция публикации сообщений в брокер."""

    @abstractmethod
    async def publish(self, routing_key: str, message: dict[str, Any]) -> None:
        """Опубликовать сообщение.

        Args:
            routing_key: ключ маршрутизации (например ``"telegram.send"``).
            message: тело сообщения (будет сериализовано в JSON).
        """
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Установить соединение с брокером."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Закрыть соединение."""
        ...
