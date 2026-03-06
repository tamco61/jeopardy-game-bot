"""Базовое исключение доменного слоя."""


class DomainError(Exception):
    """Все бизнес-ошибки наследуются от этого класса."""

    def __init__(self, message: str = "Ошибка доменной логики") -> None:
        self.message = message
        super().__init__(self.message)
