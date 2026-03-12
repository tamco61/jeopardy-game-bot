from src.application.lobby_management import (
    BaseLobbyDTO,
    CreateLobbyUseCase,
    JoinLobbyUseCase,
    LeaveLobbyUseCase,
    ReadyUseCase,
)
from src.bot.callback import (
    LobbyLeaveCallback,
    LobbyNotReadyCallback,
    LobbyReadyCallback,
)
from src.bot.router import callback, command
from src.bot.ui import JeopardyUI
from src.infrastructure.redis_repo import RedisStateRepository


class LobbyHandler:
    """Обработчик команд лобби (создание, вход, готовность)."""

    def __init__(
        self,
        ui: JeopardyUI,
        create_lobby_uc: CreateLobbyUseCase,
        join_lobby_uc: JoinLobbyUseCase,
        ready_uc: ReadyUseCase,
        leave_lobby_uc: LeaveLobbyUseCase,
        state_repo: RedisStateRepository,
    ) -> None:
        self._ui = ui
        self._create_lobby = create_lobby_uc
        self._join_lobby = join_lobby_uc
        self._ready = ready_uc
        self._leave_lobby = leave_lobby_uc
        self._state_repo = state_repo

    @command("/start")
    async def handle_start(self, chat_id: int) -> None:
        await self._ui.send_message(
            chat_id,
            "👋 **Добро пожаловать в Свою Игру!**\n\n"
            "Как начать игру:\n"
            "1️⃣ Ведущий пишет /create_lobby в групповом чате\n"
            "2️⃣ Игроки пишут /join\n"
            "3️⃣ Все нажимают **✅ Готов** в сообщении лобби\n"
            "4️⃣ Ведущий нажимает **🚀 Начать игру**\n\n"
            "📝 /results — посмотреть результаты последней игры",
        )

    @command("/create_lobby")
    async def handle_create_lobby(self, chat_id: int, lobby_dto: BaseLobbyDTO) -> None:
        try:
            await self._create_lobby.execute(lobby_dto)
            await self._ui.send_message(
                chat_id,
                "✅ Лобби создано! Вы ведущий. Игроки пишут /join.",
            )
        except Exception as e:
            await self._ui.send_message(chat_id, f"Ошибка: {e}")

    @command("/join")
    async def handle_join(self, chat_id: int, lobby_dto: BaseLobbyDTO) -> None:
        try:
            await self._join_lobby.execute(lobby_dto)
            room = await self._state_repo.get_room(lobby_dto.room_id)
            if room:
                await self._update_lobby(chat_id, room)
        except Exception as e:
            await self._ui.send_message(chat_id, f"Ошибка: {e}")

    @command("/ready")
    async def handle_ready(self, chat_id: int, room_id: str, player_id: str) -> None:
        try:
            await self._ready.execute(room_id, player_id, is_ready=True)
            room = await self._state_repo.get_room(room_id)
            if room:
                await self._update_lobby(chat_id, room)
        except Exception as e:
            await self._ui.send_message(chat_id, f"Ошибка: {e}")

    @command("/notready")
    async def handle_notready(self, chat_id: int, room_id: str, player_id: str) -> None:
        try:
            await self._ready.execute(room_id, player_id, is_ready=False)
            room = await self._state_repo.get_room(room_id)
            if room:
                await self._update_lobby(chat_id, room)
        except Exception as e:
            await self._ui.send_message(chat_id, f"Ошибка: {e}")

    @command("/leave")
    async def handle_leave(self, chat_id: int, room_id: str, player_id: str, username: str) -> None:
        try:
            await self._leave_lobby.execute(room_id, player_id)
            room = await self._state_repo.get_room(room_id)
            if room:
                await self._update_lobby(chat_id, room)
            else:
                await self._ui.send_message(chat_id, f"Игрок @{username} покинул лобби.")
        except Exception as e:
            await self._ui.send_message(chat_id, f"Ошибка: {e}")

    # ── Inline-кнопки лобби ──────────────────────────

    @callback(LobbyReadyCallback)
    async def handle_lobby_ready(
        self, chat_id: int, room_id: str, player_id: str, cb_id: str
    ) -> None:
        try:
            await self._ready.execute(room_id, player_id, is_ready=True)
            room = await self._state_repo.get_room(room_id)
            if room:
                await self._update_lobby(chat_id, room)
        except Exception as e:
            await self._ui.answer_callback_query(cb_id, text=f"Ошибка: {e}", show_alert=True)
            return
        await self._ui.answer_callback_query(cb_id, text="Ты готов!")

    @callback(LobbyNotReadyCallback)
    async def handle_lobby_notready(
        self, chat_id: int, room_id: str, player_id: str, cb_id: str
    ) -> None:
        try:
            await self._ready.execute(room_id, player_id, is_ready=False)
            room = await self._state_repo.get_room(room_id)
            if room:
                await self._update_lobby(chat_id, room)
        except Exception as e:
            await self._ui.answer_callback_query(cb_id, text=f"Ошибка: {e}", show_alert=True)
            return
        await self._ui.answer_callback_query(cb_id, text="Отмечен как не готов")

    @callback(LobbyLeaveCallback)
    async def handle_lobby_leave(
        self, chat_id: int, room_id: str, player_id: str, username: str, cb_id: str
    ) -> None:
        try:
            await self._leave_lobby.execute(room_id, player_id)
            room = await self._state_repo.get_room(room_id)
            if room:
                await self._update_lobby(chat_id, room)
        except Exception as e:
            await self._ui.answer_callback_query(cb_id, text=f"Ошибка: {e}", show_alert=True)
            return
        await self._ui.answer_callback_query(cb_id, text=f"@{username} покинул лобби")

    # ── Вспомогательные методы ───────────────────────

    async def _update_lobby(self, chat_id: int, room) -> None:
        """Отрисовать лобби и при новом сообщении сохранить его ID."""
        new_msg_id = await self._ui.render_lobby_update(chat_id, room)
        if new_msg_id:
            room.last_lobby_message_id = new_msg_id
            await self._state_repo.save_room(room)

    @command("/results")
    async def handle_show_results(self, chat_id: int) -> None:
        """Показать результаты последней игры в этом чате."""
        results = await self._state_repo.get_last_results(chat_id)
        if results:
            await self._ui.send_message(chat_id, f"📝 **Последние результаты:**\n\n{results}")
        else:
            await self._ui.send_message(chat_id, "🤷♂️ Результаты прошлых игр в этом чате не найдены.")
