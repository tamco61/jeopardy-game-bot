"""Use Case: Старт игры (Своя игра)."""

from __future__ import annotations

from src.application.interfaces.game_repository import IGameRepository
from src.application.interfaces.message_publisher import IMessagePublisher
from src.application.interfaces.state_repository import IStateRepository


class StartGameUseCase:
    """Сценарий запуска нового раунда.

    Оркестрация:
    1. Получить случайный вопрос из БД (IGameRepository).
    2. Создать / сбросить комнату (IStateRepository).
    3. Опубликовать событие «раунд начался» (IMessagePublisher).
    """

    def __init__(
        self,
        game_repo: IGameRepository,
        state_repo: IStateRepository,
        publisher: IMessagePublisher,
    ) -> None:
        self._game_repo = game_repo
        self._state_repo = state_repo
        self._publisher = publisher

    async def execute(self, chat_id: int, room_id: str) -> None:
        """Запустить раунд «Своей игры».

        TODO: реализовать бизнес-логику.
        """
        raise NotImplementedError
