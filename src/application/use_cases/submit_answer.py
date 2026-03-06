"""Use Case: Отправка ответа на вопрос."""

from __future__ import annotations

from src.application.interfaces.state_repository import IStateRepository


class SubmitAnswerUseCase:
    """Сценарий проверки ответа игрока.

    Оркестрация:
    1. Загрузить комнату (IStateRepository).
    2. Вызвать room.submit_answer(player, text).
    3. Начислить / списать очки, обновить состояние.
    """

    def __init__(self, state_repo: IStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, room_id: str, telegram_id: int, answer: str) -> bool:
        """Проверить ответ игрока.

        Returns:
            True — ответ правильный.

        TODO: реализовать бизнес-логику.
        """
        raise NotImplementedError
