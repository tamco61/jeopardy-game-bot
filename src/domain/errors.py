"""Базовое исключение доменного слоя."""


class DomainError(Exception):
    """Все бизнес-ошибки наследуются от этого класса."""

    def __init__(self, message: str = "Ошибка доменной логики") -> None:
        self.message = message
        super().__init__(self.message)


"""Исключение: недопустимый переход FSM."""

from src.domain.errors import DomainError


class InvalidTransitionError(DomainError):
    """Попытка перехода в невалидное состояние FSM."""

    def __init__(self, current_phase: str, attempted_action: str) -> None:
        super().__init__(
            f"Нельзя выполнить '{attempted_action}' в фазе '{current_phase}'"
        )
        self.current_phase = current_phase
        self.attempted_action = attempted_action


"""Исключение: игрок заблокирован на текущий вопрос."""

from src.domain.errors import DomainError


class PlayerBlockedError(DomainError):
    """Заблокированный игрок пытается нажать кнопку."""

    def __init__(self, player_name: str) -> None:
        super().__init__(f"Игрок {player_name} заблокирован на этот вопрос")
        self.player_name = player_name


"""Исключение: не найден игрок."""

from src.domain.errors import DomainError


class PlayerNotFoundError(DomainError):
    """Игрок не найден в комнате."""

    def __init__(self, player_id: str) -> None:
        super().__init__(f"Игрок {player_id} не найден в комнате")
        self.player_id = player_id
