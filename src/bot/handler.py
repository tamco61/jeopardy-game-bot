from src.application.lobby_management import BaseLobbyDTO
from src.bot.handlers.admin import AdminHandler
from src.bot.handlers.game import GameHandler
from src.bot.handlers.lobby import LobbyHandler
from src.bot.router import Router
from src.infrastructure.redis_repo import RedisStateRepository
from src.shared.logger import get_logger

logger = get_logger(__name__)


class TelegramRouter:
    """Диспетчер входящих Telegram-обновлений.

    Теперь использует декораторы и реестр `Router` для маршрутизации.
    """

    def __init__(
        self,
        state_repo: RedisStateRepository,
        lobby_handler: LobbyHandler,
        game_handler: GameHandler,
        admin_handler: AdminHandler,
    ) -> None:
        self._state_repo = state_repo

        self.router = Router()
        self.router.include_class(lobby_handler)
        self.router.include_class(game_handler)
        self.router.include_class(admin_handler)

    async def handle_update(self, update: dict) -> None:
        """Главный входной пункт для всех Telegram-обновлений."""
        logger.info("📩 Получен update: %s", update.get("update_id"))

        message: dict | None = update.get("message")
        if message:
            await self._handle_message(message)
            return

        callback_query: dict | None = update.get("callback_query")
        if callback_query:
            await self._handle_callback(callback_query)

    async def _handle_message(self, message: dict) -> None:
        text: str = (message.get("text") or "").strip()
        chat_id: int = message.get("chat", {}).get("id", 0)
        is_private = message.get("chat", {}).get("type", "") == "private"
        user = message.get("from", {})
        player_id = str(user.get("id", ""))
        user_tg_id = int(user.get("id", 0))
        username = user.get("username") or user.get("first_name", "unknown")

        room_id = f"room_{chat_id}"

        lobby_dto = BaseLobbyDTO(
            room_id=room_id,
            player_id=player_id,
            telegram_id=user_tg_id,
            group_chat_id=chat_id if not is_private else 0,
            username=username,
            first_name=user.get("first_name", ""),
        )

        kwargs = {
            "message": message,
            "text": text,
            "chat_id": chat_id,
            "is_private": is_private,
            "player_id": player_id,
            "user_tg_id": user_tg_id,
            "username": username,
            "room_id": room_id,
            "lobby_dto": lobby_dto,
        }

        if "document" in message:
            for handler in self.router.document_handlers:
                await self.router.execute_handler(handler, **kwargs)
            return

        if text.startswith("/"):
            cmd = text.split(" ")[0]
            if cmd in self.router.commands:
                handler = self.router.commands[cmd]
                await self.router.execute_handler(handler, **kwargs)
        elif text:
            # Для не-команд в ЛС ищем активную комнату игрока
            if is_private:
                active_room = await self._state_repo.get_active_room(user_tg_id)
                if active_room:
                    room_id = active_room
                    kwargs["room_id"] = room_id

            room = await self._state_repo.get_room(room_id)
            kwargs["room"] = room
            for handler in self.router.message_handlers:
                result = await self.router.execute_handler(handler, **kwargs)
                if result:
                    break

    async def _handle_callback(self, callback_query: dict) -> None:
        user: dict = callback_query.get("from", {})
        player_id = str(user.get("id", ""))
        username: str = user.get("username") or user.get("first_name", "unknown")
        user_tg_id = int(user.get("id", 0))

        data: str = callback_query.get("data", "")
        message: dict = callback_query.get("message", {})
        chat_id = message.get("chat", {}).get("id", 0)
        message_id: int = message.get("message_id", 0)
        cb_id = callback_query.get("id", "")

        room_id = f"room_{chat_id}"

        kwargs = {
            "callback_query": callback_query,
            "data": data,
            "cb_id": cb_id,
            "message": message,
            "chat_id": chat_id,
            "message_id": message_id,
            "player_id": player_id,
            "username": username,
            "user_tg_id": user_tg_id,
            "room_id": room_id,
        }

        for prefix, handler in self.router.callbacks.items():
            if data.startswith(prefix):
                await self.router.execute_handler(handler, **kwargs)
                return
