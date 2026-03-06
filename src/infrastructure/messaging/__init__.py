"""Адаптер очередей сообщений (RabbitMQ).

- ``rabbit_publisher.py`` — RabbitMQPublisher (реализует IMessagePublisher)
"""

from src.infrastructure.messaging.rabbit_publisher import RabbitMQPublisher

__all__: list[str] = ["RabbitMQPublisher"]
