"""Исключение: не найден игрок."""

from src.domain.exception.base import DomainError


class PlayerNotFoundError(DomainError):
    """Игрок не найден в комнате."""

    def __init__(self, player_id: str) -> None:
        super().__init__(f"Игрок {player_id} не найден в комнате")
        self.player_id = player_id
