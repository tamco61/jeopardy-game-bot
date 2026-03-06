"""Порты приложения (абстрактные классы / интерфейсы).

- ``IStateRepository``    — интерфейс для Redis (state_repository.py)
- ``IGameRepository``     — интерфейс для Postgres (game_repository.py)
- ``IMessagePublisher``   — интерфейс для RabbitMQ (message_publisher.py)
"""

from src.application.interfaces.game_repository import IGameRepository
from src.application.interfaces.message_publisher import IMessagePublisher
from src.application.interfaces.state_repository import IStateRepository

__all__: list[str] = [
    "IGameRepository",
    "IMessagePublisher",
    "IStateRepository",
]
