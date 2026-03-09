from src.application.lobby_management import BaseLobbyDTO
from src.bot.handlers.admin import AdminHandler
from src.bot.handlers.game import GameHandler
from src.bot.handlers.lobby import LobbyHandler
from src.domain.room import Phase
from src.infrastructure.redis_repo import RedisStateRepository
from src.shared.logger import get_logger

logger = get_logger(__name__)


class TelegramRouter:
    """Диспетчер входящих Telegram-обновлений.
    
    Теперь является легковесным роутером, который делегирует всю логику
    специализированным хендлерам.
    """

    def __init__(
        self,
        state_repo: RedisStateRepository,
        lobby_handler: LobbyHandler,
        game_handler: GameHandler,
        admin_handler: AdminHandler,
    ) -> None:
        self._state_repo = state_repo
        self._lobby = lobby_handler
        self._game = game_handler
        self._admin = admin_handler

    async def handle_update(self, update: dict) -> None:
        """Главный входной пункт для всех Telegram-обновлений."""
        logger.info(f"📩 Получен update: {update.get('update_id')}")

        message: dict | None = update.get("message")
        if message:
            await self._handle_message(message)
            return

        callback_query: dict | None = update.get("callback_query")
        if callback_query:
            await self._handle_callback(callback_query)

    async def _handle_message(self, message: dict) -> None:
        if "document" in message:
            await self._admin.handle_document(message)
            return

        text: str = (message.get("text") or "").strip()
        chat_id: int = message["chat"]["id"]
        is_private = message["chat"].get("type", "") == "private"
        user = message.get("from", {})
        player_id = str(user.get("id", ""))
        user_tg_id = int(user.get("id", 0))
        username = user.get("username") or user.get("first_name", "unknown")

        lobby_dto = BaseLobbyDTO(
            room_id="room_1",
            player_id=player_id,
            telegram_id=user_tg_id,
            group_chat_id=chat_id,
            username=username,
            first_name=user.get("first_name", ""),
        )

        # Роутинг команд
        if text == "/create_lobby":
            await self._lobby.handle_create_lobby(chat_id, lobby_dto)
        elif text == "/join":
            await self._lobby.handle_join(chat_id, lobby_dto)
        elif text == "/ready":
            await self._lobby.handle_ready(chat_id, player_id, username, True)
        elif text == "/notready":
            await self._lobby.handle_ready(chat_id, player_id, username, False)
        elif text == "/leave":
            await self._lobby.handle_leave(chat_id, player_id, username)
        elif text == "/start_game":
            await self._game.handle_start_game(chat_id, player_id, user_tg_id)
        elif text == "/pause":
            await self._admin.handle_pause(chat_id, player_id)
        elif text == "/unpause":
            await self._admin.handle_unpause(chat_id, player_id)
        elif text.startswith("/stack "):
            await self._game.handle_place_stake(chat_id, player_id, username, text)
        elif text == "/upload_pack":
            await self._lobby._tg.send_message(
                chat_id,
                "📂 Чтобы загрузить свой пакет вопросов, отправьте файл `.siq` и в поле подписи (caption) напишите `/upload_pack`.",
            )
        elif text and not text.startswith("/"):
            room = await self._state_repo.get_room("room_1")
            if room and room.phase in (Phase.ANSWERING, Phase.FINAL_ANSWER):
                await self._game.handle_submit_answer(chat_id, player_id, username, text, room, is_private)

    async def _handle_callback(self, callback_query: dict) -> None:
        user: dict = callback_query["from"]
        player_id = str(user["id"])
        username: str = user.get("username") or user.get("first_name", "unknown")
        data: str = callback_query.get("data", "")
        message: dict = callback_query["message"]
        chat_id = message["chat"]["id"]
        message_id: int = message["message_id"]
        cb_id = callback_query["id"]

        room = await self._state_repo.get_room("room_1")
        if not room: return

        if data.startswith("verdict:"):
            await self._game.handle_verdict(chat_id, message_id, data, room)
            await self._lobby._tg.answer_callback_query(cb_id)
        elif data.startswith("select_question:"):
            q_id = int(data.split(":")[1])
            await self._game.handle_select_question(chat_id, player_id, q_id, room)
            await self._lobby._tg.answer_callback_query(cb_id)
        elif data == "btn_room_1":
            await self._game.handle_press_button(chat_id, player_id, username, message_id, cb_id)
        elif data == "final_start_stakes":
            await self._game.handle_final_start_stakes(chat_id, room)
            await self._lobby._tg.answer_callback_query(cb_id)
        elif data == "final_close_stakes":
            await self._game.handle_final_close_stakes(chat_id, room)
            await self._lobby._tg.answer_callback_query(cb_id)
