"""Use Case: Отправка ответа на вопрос."""

from __future__ import annotations

from pydantic import BaseModel
from src.domain.errors import DomainError
from src.domain.room import Phase
from src.infrastructure.redis_repo import RedisStateRepository


class SubmitAnswerDTO(BaseModel):
    """Данные для отправки ответа."""
    room_id: str
    player_id: str
    answer: str


class SubmitAnswerUseCase:
    """Сценарий отправки ответа игрока.

    Оркестрация:
    1. Загрузить комнату (RedisStateRepository).
    2. Проверить фазу и сохранить ответ (room.provide_answer или room.submit_final_answer).
    3. Сохранить обновлённое состояние.
    """

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, dto: SubmitAnswerDTO) -> None:
        """Сохранить ответ игрока (ожидая вердикта HOST)."""
        room = await self._state_repo.get_room(dto.room_id)
        if room is None:
            raise DomainError(f"Комната {dto.room_id} не найдена")

        if room.phase == Phase.ANSWERING:
            room.provide_answer(dto.player_id, dto.answer)
        elif room.phase == Phase.FINAL_ANSWER:
            room.submit_final_answer(dto.player_id, dto.answer)
        else:
            raise DomainError(f"Нельзя дать ответ в фазе {room.phase.value}")

        await self._state_repo.save_room(room)
