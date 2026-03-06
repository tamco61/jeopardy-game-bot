"""Исключение: недопустимый переход FSM."""

from src.domain.exception.base import DomainError


class InvalidTransitionError(DomainError):
    """Попытка перехода в невалидное состояние FSM."""

    def __init__(self, current_phase: str, attempted_action: str) -> None:
        super().__init__(
            f"Нельзя выполнить '{attempted_action}' в фазе '{current_phase}'"
        )
        self.current_phase = current_phase
        self.attempted_action = attempted_action
