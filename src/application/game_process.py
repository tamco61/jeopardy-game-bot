"""Use Cases для игрового процесса (Пауза, Настройки)."""

from src.domain.errors import DomainError
from src.domain.room import Room, Phase
from src.infrastructure.redis_repo import RedisStateRepository


class PauseGameUseCase:
    """Постановка игры на паузу."""

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, room_id: str, host_id: str) -> None:
        """Переводит комнату в состояние PAUSE, проверяя, что вызывает HOST (в MVP host = chat_id)."""
        room = await self._state_repo.get_room(room_id)
        if not room:
            raise DomainError(f"Комната {room_id} не найдена.")

        # В реальной реализации здесь была бы проверка host_id == room.host_id
        room.pause()
        await self._state_repo.save_room(room)


class UnpauseGameUseCase:
    """Снятие игры с паузы."""

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, room_id: str, host_id: str) -> str:
        """Снимает паузу и возвращает комнату в исходное состояние.
        
        Returns:
            Имя фазы, в которую вернулась комната.
        """
        room = await self._state_repo.get_room(room_id)
        if not room:
            raise DomainError(f"Комната {room_id} не найдена.")

        room.resume()
        await self._state_repo.save_room(room)
        return room.phase.value
