"""Use Cases для спец-ивентов (Аукцион, Ставки на финал)."""

from src.domain.errors import DomainError
from src.domain.room import Phase, Room
from src.infrastructure.redis_repo import RedisStateRepository


class PlaceStakeUseCase:
    """Игрок делает ставку (в финале или на аукционе)."""

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, room_id: str, player_id: str, stake: int) -> None:
        room = await self._state_repo.get_room(room_id)
        if not room:
            raise DomainError(f"Комната {room_id} не найдена.")

        # MVP: В комнате сейчас реализован place_stake только для финала (FINAL_STAKE).
        # Если нужно поддерживать ставки на аукционе, нужно будет расширить FSM.
        if room.phase != Phase.FINAL_STAKE:
            raise DomainError(
                f"Ставки недоступны в текущей фазе: {room.phase.value}"
            )

        room.place_stake(player_id, stake)
        await self._state_repo.save_room(room)


class StartFinalStakeUseCase:
    """Ведущий объявляет прием ставок в финале."""

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, room_id: str) -> None:
        room = await self._state_repo.get_room(room_id)
        if not room:
            raise DomainError(f"Комната {room_id} не найдена.")

        room.open_stakes()
        await self._state_repo.save_room(room)


class CloseFinalStakeUseCase:
    """Ведущий закрывает ставки и переходит к ответам."""

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, room_id: str) -> None:
        room = await self._state_repo.get_room(room_id)
        if not room:
            raise DomainError(f"Комната {room_id} не найдена.")

        room.close_stakes()
        await self._state_repo.save_room(room)
