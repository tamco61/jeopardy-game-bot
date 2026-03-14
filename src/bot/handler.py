from src.application.lobby_management import BaseLobbyDTO
from src.bot.handlers.admin import AdminHandler
from src.bot.handlers.game import GameHandler
from src.bot.handlers.lobby import LobbyHandler
from src.bot.router import Router
from src.infrastructure.redis_repo import RedisStateRepository
from src.shared.domain_events import (
    ButtonClickEvent,
    CommandEvent,
    DocumentEvent,
    DomainEvent,
    TextEvent,
)
from src.shared.logger import get_logger

logger = get_logger(__name__)


class EventRouter:
    """Диспетчер входящих абстрактных событий (DomainEvent)."""

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

    async def handle_event(self, event: DomainEvent) -> None:
        """Главный входной пункт для всех событий (Telegram/Web)."""
        logger.info("📩 Получено событие: %s от %s", type(event).__name__, event.source)

        if isinstance(event, CommandEvent):
            await self._handle_command(event)
        elif isinstance(event, TextEvent):
            await self._handle_text(event)
        elif isinstance(event, ButtonClickEvent):
            await self._handle_callback(event)
        elif isinstance(event, DocumentEvent):
            await self._handle_document(event)

    async def _handle_command(self, event: CommandEvent) -> None:
        lobby_dto = BaseLobbyDTO(
            room_id=event.room_id,
            player_id=event.player_id,
            telegram_id=event.user_tg_id or 0,
            group_chat_id=event.chat_id,
            username=event.username,
            first_name=event.username,
        )

        kwargs = {
            "chat_id": event.chat_id,
            "player_id": event.player_id,
            "user_tg_id": event.user_tg_id,
            "username": event.username,
            "room_id": event.room_id,
            "lobby_dto": lobby_dto,
            "text": f"{event.command} {event.args}".strip(),  # For compatibility if handlers parse text
        }

        if event.command in self.router.commands:
            handler = self.router.commands[event.command]
            await self.router.execute_handler(handler, **kwargs)
        else:
            logger.debug("Неизвестная команда: %s", event.command)

    async def _handle_text(self, event: TextEvent) -> None:
        room_id = event.room_id
        
        # Для сообщений в ЛС ищем активную игру
        if event.is_private and event.user_tg_id:
            active_room = await self._state_repo.get_active_room(event.user_tg_id)
            if active_room:
                room_id = active_room

        room = await self._state_repo.get_room(room_id)

        kwargs = {
            "chat_id": event.chat_id,
            "is_private": event.is_private,
            "player_id": event.player_id,
            "user_tg_id": event.user_tg_id,
            "username": event.username,
            "room_id": room_id,
            "room": room,
            "text": event.text,
        }

        for handler in self.router.message_handlers:
            result = await self.router.execute_handler(handler, **kwargs)
            if result:
                break

    async def _handle_callback(self, event: ButtonClickEvent) -> None:
        kwargs = {
            "data": event.data,  # Может быть переопределено parse()
            "cb_id": event.callback_id,
            "chat_id": event.chat_id,
            "message_id": event.message_id,
            "player_id": event.player_id,
            "username": event.username,
            "user_tg_id": event.user_tg_id,
            "room_id": event.room_id,
        }

        for prefix, handler in self.router.callbacks.items():
            if event.data.startswith(prefix):
                callback_class = getattr(handler, "__callback_class__", None)
                if callback_class:
                    try:
                        parsed_data = callback_class.parse(event.data)
                        kwargs["data"] = parsed_data
                    except Exception as e:
                        logger.error("Failed to parse callback data '%s': %s", event.data, e)
                        return

                await self.router.execute_handler(handler, **kwargs)
                return

    async def _handle_document(self, event: DocumentEvent) -> None:
        kwargs = {
            "chat_id": event.chat_id,
            "file_id": event.file_id,
            "file_name": event.file_name,
            "caption": event.caption,
        }
        for handler in self.router.document_handlers:
            await self.router.execute_handler(handler, **kwargs)
