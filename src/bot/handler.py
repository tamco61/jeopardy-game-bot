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

        room_id = f"room_{chat_id}"
        if is_private:
            active_room = await self._state_repo.get_active_room(user_tg_id)
            if active_room:
                room_id = active_room

        lobby_dto = BaseLobbyDTO(
            room_id=room_id,
            player_id=player_id,
            telegram_id=user_tg_id,
            group_chat_id=chat_id if not is_private else 0, # В ЛС chat_id это ID юзера
            username=username,
            first_name=user.get("first_name", ""),
        )

        # Роутинг команд
        if text == "/create_lobby":
            await self._lobby.handle_create_lobby(chat_id, lobby_dto)
        elif text == "/join":
            await self._lobby.handle_join(chat_id, lobby_dto)
        elif text == "/ready":
            await self._lobby.handle_ready(chat_id, room_id, player_id, username, True)
        elif text == "/notready":
            await self._lobby.handle_ready(chat_id, room_id, player_id, username, False)
        elif text == "/leave":
            await self._lobby.handle_leave(chat_id, room_id, player_id, username)
        elif text == "/start_game":
            await self._game.handle_start_game(chat_id, room_id, player_id, user_tg_id)
        elif text == "/skip":
            await self._game.handle_skip_round(chat_id, room_id, player_id)
        elif text == "/pause":
            await self._admin.handle_pause(chat_id, room_id, player_id)
        elif text == "/unpause":
            await self._admin.handle_unpause(chat_id, room_id, player_id)
        elif text.startswith("/stack "):
            await self._game.handle_place_stake(chat_id, room_id, player_id, username, text)
        elif text == "/results":
            await self._lobby.handle_show_results(chat_id)
        elif text == "/upload_pack":
            await self._lobby._tg.send_message(
                chat_id,
                "📂 Чтобы загрузить свой пакет вопросов, отправьте файл `.siq` и в поле подписи (caption) напишите `/upload_pack`.",
            )
        elif text and not text.startswith("/"):
            room = await self._state_repo.get_room(room_id)
            if room and room.phase in (Phase.ANSWERING, Phase.FINAL_ANSWER):
                await self._game.handle_submit_answer(chat_id, room_id, player_id, username, text, room, is_private)

    async def _handle_callback(self, callback_query: dict) -> None:
        user: dict = callback_query["from"]
        player_id = str(user["id"])
        username: str = user.get("username") or user.get("first_name", "unknown")
        data: str = callback_query.get("data", "")
        message: dict = callback_query["message"]
        chat_id = message["chat"]["id"]
        message_id: int = message["message_id"]
        cb_id = callback_query["id"]

        user_tg_id = int(user["id"])
        room_id = f"room_{chat_id}"
        # Для команд, где ID комнаты зашит в callback_data, мы извлекаем его ниже.
        # Для команд, привязанных к чату (например, buzzer), используем room_id.

        if data.startswith("verdict:"):
            # verdict:{room_id}:{yes/no}:{player_id}
            parts = data.split(":")
            if len(parts) == 4:
                r_id = parts[1]
                v_room = await self._state_repo.get_room(r_id)
                if v_room:
                    await self._game.handle_verdict(chat_id, r_id, message_id, data, v_room)
            await self._lobby._tg.answer_callback_query(cb_id)
        elif data.startswith("select_question:"):
            # select_question:{room_id}:{q_id}
            parts = data.split(":")
            if len(parts) == 3:
                r_id = parts[1]
                q_id = int(parts[2])
                q_room = await self._state_repo.get_room(r_id)
                if q_room:
                    await self._game.handle_select_question(chat_id, r_id, player_id, q_id, q_room)
            await self._lobby._tg.answer_callback_query(cb_id)
        elif data.startswith("select_pack:"):
            # select_pack:{room_id}:{pack_id}
            parts = data.split(":")
            if len(parts) == 3:
                r_id = parts[1]
                p_id = int(parts[2])
                await self._game.handle_select_pack(chat_id, r_id, p_id, player_id, user_tg_id)
            await self._lobby._tg.answer_callback_query(cb_id)
        elif data.startswith("skip_round:"):
            r_id = data.split(":")[1]
            await self._game.handle_skip_round(chat_id, r_id, player_id)
            await self._lobby._tg.answer_callback_query(cb_id)
        elif data.startswith("btn_room_"):
            # Нажатие на зуммер
            await self._game.handle_press_button(chat_id, room_id, player_id, username, message_id, cb_id)
        elif data.startswith("final_start_stakes:"):
            r_id = data.split(":")[1]
            f_room = await self._state_repo.get_room(r_id)
            if f_room:
                await self._game.handle_final_start_stakes(chat_id, r_id, f_room)
            await self._lobby._tg.answer_callback_query(cb_id)
        elif data.startswith("final_close_stakes:"):
            r_id = data.split(":")[1]
            f_room = await self._state_repo.get_room(r_id)
            if f_room:
                await self._game.handle_final_close_stakes(chat_id, r_id, f_room)
            await self._lobby._tg.answer_callback_query(cb_id)
        elif data.startswith("final_reveal:"):
            r_id = data.split(":")[1]
            f_room = await self._state_repo.get_room(r_id)
            if f_room:
                await self._game.handle_final_reveal(chat_id, r_id, f_room)
            await self._lobby._tg.answer_callback_query(cb_id)
