"""Бизнес-ошибки доменного слоя.

- ``DomainError``            — базовое исключение (base.py)
- ``PlayerBlockedError``     — заблокирован на вопрос (player_blocked.py)
- ``InvalidTransitionError`` — невалидный переход FSM (invalid_transition.py)
- ``PlayerNotFoundError``    — игрок не найден (player_not_found.py)
"""

from src.domain.exception.base import DomainError
from src.domain.exception.invalid_transition import InvalidTransitionError
from src.domain.exception.player_blocked import PlayerBlockedError
from src.domain.exception.player_not_found import PlayerNotFoundError

__all__: list[str] = [
    "DomainError",
    "InvalidTransitionError",
    "PlayerBlockedError",
    "PlayerNotFoundError",
]
