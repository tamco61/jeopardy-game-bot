"""Исключение: игрок заблокирован на текущий вопрос."""

from src.domain.exception.base import DomainError


class PlayerBlockedError(DomainError):
    """Заблокированный игрок пытается нажать кнопку."""

    def __init__(self, player_name: str) -> None:
        super().__init__(f"Игрок {player_name} заблокирован на этот вопрос")
        self.player_name = player_name
