from src.application.lobby_management import (
    BaseLobbyDTO,
    CreateLobbyUseCase,
    JoinLobbyUseCase,
    LeaveLobbyUseCase,
    ReadyUseCase,
)
from src.infrastructure.telegram import TelegramHttpClient
from src.infrastructure.redis_repo import RedisStateRepository


class LobbyHandler:
    """Обработчик команд лобби (создание, вход, готовность)."""

    def __init__(
        self,
        tg_client: TelegramHttpClient,
        create_lobby_uc: CreateLobbyUseCase,
        join_lobby_uc: JoinLobbyUseCase,
        ready_uc: ReadyUseCase,
        leave_lobby_uc: LeaveLobbyUseCase,
        state_repo: RedisStateRepository,
    ) -> None:
        self._tg = tg_client
        self._create_lobby = create_lobby_uc
        self._join_lobby = join_lobby_uc
        self._ready = ready_uc
        self._leave_lobby = leave_lobby_uc
        self._state_repo = state_repo

    async def handle_create_lobby(self, chat_id: int, dto: BaseLobbyDTO) -> None:
        try:
            await self._create_lobby.execute(dto)
            await self._tg.send_message(
                chat_id,
                "Лобби создано! Вы ведущий (HOST). Игроки могут писать /join.",
            )
        except Exception as e:
            await self._tg.send_message(chat_id, f"Ошибка: {e}")

    async def handle_join(self, chat_id: int, dto: BaseLobbyDTO) -> None:
        try:
            await self._join_lobby.execute(dto)
            await self._tg.send_message(
                chat_id, f"Игрок @{dto.username} присоединился к лобби!"
            )
        except Exception as e:
            await self._tg.send_message(chat_id, f"Ошибка: {e}")

    async def handle_ready(self, chat_id: int, room_id: str, player_id: str, username: str, is_ready: bool) -> None:
        try:
            await self._ready.execute(room_id, player_id, is_ready=is_ready)
            status = "готов" if is_ready else "не готов"
            await self._tg.send_message(chat_id, f"Игрок @{username} {status}!")
        except Exception as e:
            await self._tg.send_message(chat_id, f"Ошибка: {e}")

    async def handle_leave(self, chat_id: int, room_id: str, player_id: str, username: str) -> None:
        try:
            await self._leave_lobby.execute(room_id, player_id)
            await self._tg.send_message(
                chat_id, f"Игрок @{username} покинул лобби."
            )
        except Exception as e:
            await self._tg.send_message(chat_id, f"Ошибка: {e}")

    async def handle_show_results(self, chat_id: int) -> None:
        """Показать результаты последней игры в этом чате."""
        results = await self._state_repo.get_last_results(chat_id)
        if results:
            await self._tg.send_message(chat_id, f"📝 **Последние результаты:**\n\n{results}")
        else:
            await self._tg.send_message(chat_id, "🤷♂️ Результаты прошлых игр в этом чате не найдены.")
