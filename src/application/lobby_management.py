"""Use Cases для стадии лобби (LOBBY)."""

from pydantic import BaseModel

from src.domain.errors import DomainError
from src.domain.player import Player
from src.domain.room import Phase, Room
from src.infrastructure.redis_repo import RedisStateRepository


class BaseLobbyDTO(BaseModel):
    """Базовые атрибуты для лобби."""

    room_id: str
    player_id: str
    telegram_id: int
    group_chat_id: int = 0
    username: str
    first_name: str = ""


class CreateLobbyUseCase:
    """Создание лобби ведущим (HOST)."""

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, dto: BaseLobbyDTO) -> None:
        """Создает комнату и делает инициатора HOST-ом (в MVP пока просто создает пустую комнату)."""
        existing_room = await self._state_repo.get_room(dto.room_id)
        if existing_room:
            # Для простоты, если комната есть, удаляем ее и создаем заново
            await self._state_repo.delete_room(dto.room_id)

        room = Room(
            room_id=dto.room_id,
            # chat_id = групповой чат, где проходит игра
            chat_id=dto.group_chat_id or dto.telegram_id,
            phase=Phase.LOBBY,
            host_id=dto.player_id,
            # host_telegram_id = личный ID ведущего для отправки ЛС
            host_telegram_id=dto.telegram_id,
        )

        await self._state_repo.save_room(room)


class JoinLobbyUseCase:
    """Присоединение игрока к лобби."""

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, dto: BaseLobbyDTO) -> None:
        room = await self._state_repo.get_room(dto.room_id)
        if not room:
            raise DomainError(f"Лобби {dto.room_id} не найдено.")

        if room.phase != Phase.LOBBY:
            raise DomainError("Нельзя присоединиться к уже начатой игре.")

        # Игрок уже в лобби — не сбрасываем его ready-статус и очки
        if dto.player_id in room.players:
            return

        # Проверка на дубликат ника (display_name)
        new_nickname = dto.username or dto.first_name
        if dto.telegram_id == 0:
            # Для веба ник чистый, без @
            display_to_check = new_nickname
        else:
            display_to_check = f"@{new_nickname}"

        existing_names = {p.display_name.lower() for p in room.players.values()}
        if display_to_check.lower() in existing_names:
            raise DomainError(f"Никнейм {display_to_check} уже занят в этой комнате.")

        player = Player(
            player_id=dto.player_id,
            telegram_id=dto.telegram_id,
            username=dto.username,
            first_name=dto.first_name,
            score=0,
        )
        room.add_player(player)

        await self._state_repo.save_room(room)


class ReadyUseCase:
    """Пометка игрока как готового (ready/notready)."""

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(
        self, room_id: str, player_id: str, is_ready: bool = True
    ) -> None:
        room = await self._state_repo.get_room(room_id)
        if not room:
            raise DomainError(f"Лобби {room_id} не найдено.")

        player = room.get_player(player_id)

        if is_ready:
            room.mark_player_ready(player_id)
        else:
            if room.phase != Phase.LOBBY:
                raise DomainError("Нельзя снять готовность вне лобби")
            player.mark_not_ready()

        await self._state_repo.save_room(room)


class LeaveLobbyUseCase:
    """Выход игрока из лобби."""

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, room_id: str, player_id: str) -> None:
        room = await self._state_repo.get_room(room_id)
        if not room:
            raise DomainError(f"Лобби {room_id} не найдено.")

        if player_id in room.players:
            del room.players[player_id]
            await self._state_repo.save_room(room)
        else:
            raise DomainError(f"Игрок {player_id} не в лобби.")


class SetLobbyPrivacyUseCase:
    """Установка приватности лобби (только для хоста)."""

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, room_id: str, player_id: str, is_private: bool) -> None:
        room = await self._state_repo.get_room(room_id)
        if not room:
            raise DomainError(f"Лобби {room_id} не найдено.")

        if room.host_id != player_id:
            raise DomainError("Только ведущий может изменить настройки приватности.")

        if room.phase != Phase.LOBBY:
            raise DomainError("Нельзя изменить настройки лобби после начала игры.")

        room.is_private = is_private
        await self._state_repo.save_room(room)


class SetGameModeUseCase:
    """Установка режима проверки ответов (auto/manual, только для хоста)."""

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, room_id: str, player_id: str, game_mode: str) -> None:
        from src.domain.room import GameMode
        
        room = await self._state_repo.get_room(room_id)
        if not room:
            raise DomainError(f"Лобби {room_id} не найдено.")

        if room.host_id != player_id:
            raise DomainError("Только ведущий может изменить настройки режима игры.")

        if room.phase != Phase.LOBBY:
            raise DomainError("Нельзя изменить настройки лобби после начала игры.")

        room.game_mode = GameMode(game_mode)
        await self._state_repo.save_room(room)
