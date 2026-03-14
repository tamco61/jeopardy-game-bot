from src.shared.domain_events import (
    ButtonClickEvent,
    CommandEvent,
    DocumentEvent,
    DomainEvent,
    TextEvent,
)
from src.shared.logger import get_logger

logger = get_logger(__name__)


class EventMapper:
    """Адаптер сырых JSON объектов Telegram в абстрактные доменные события."""
    
    @staticmethod
    def map_telegram_update(update: dict) -> list[DomainEvent]:
        """Преврящает update от телеграма во внутренние DomainEvent.
        Возвращает список, так как теоретически апдейт может не содержать интересующих нас событий,
        либо мы можем разделять один апдейт на несколько логических пайплайнов (крайне редко).
        Обычно возвращается список из 1 элемента.
        """
        events = []
        
        # 1. Message
        message = update.get("message")
        if message:
            ev = EventMapper._parse_message(message)
            if ev:
                events.append(ev)
                
        # 2. CallbackQuery
        callback_query = update.get("callback_query")
        if callback_query:
            ev = EventMapper._parse_callback(callback_query)
            if ev:
                events.append(ev)
                
        return events

    @staticmethod
    def _parse_message(message: dict) -> DomainEvent | None:
        chat = message.get("chat", {})
        chat_id = chat.get("id", 0)
        is_private = chat.get("type", "") == "private"
        
        user = message.get("from", {})
        user_tg_id = int(user.get("id", 0))
        player_id = str(user_tg_id)
        username = user.get("username") or user.get("first_name", "unknown")
        
        room_id = f"room_{chat_id}"
        
        # 1.1 Document
        if "document" in message:
            doc = message["document"]
            return DocumentEvent(
                source="telegram",
                chat_id=chat_id,
                room_id=room_id,
                player_id=player_id,
                username=username,
                user_tg_id=user_tg_id,
                file_id=doc.get("file_id", ""),
                file_name=doc.get("file_name", ""),
                caption=message.get("caption", "")
            )
            
        # 1.2 Text / Command
        text = (message.get("text") or "").strip()
        if not text:
            return None
            
        if text.startswith("/"):
            parts = text.split(" ", 1)
            cmd = parts[0].split("@")[0]  # /cmd@botname → /cmd
            args = parts[1] if len(parts) > 1 else ""
            return CommandEvent(
                source="telegram",
                chat_id=chat_id,
                room_id=room_id,
                player_id=player_id,
                username=username,
                user_tg_id=user_tg_id,
                command=cmd,
                args=args
            )
        return TextEvent(
                source="telegram",
                chat_id=chat_id,
                room_id=room_id,
                player_id=player_id,
                username=username,
                user_tg_id=user_tg_id,
                text=text,
                is_private=is_private
            )

    @staticmethod
    def _parse_callback(callback: dict) -> DomainEvent | None:
        user = callback.get("from", {})
        user_tg_id = int(user.get("id", 0))
        player_id = str(user_tg_id)
        username = user.get("username") or user.get("first_name", "unknown")
        
        data = callback.get("data", "")
        cb_id = callback.get("id", "")
        message = callback.get("message", {})
        chat_id = message.get("chat", {}).get("id", 0)
        message_id = message.get("message_id", 0)
        
        room_id = f"room_{chat_id}"
        
        return ButtonClickEvent(
            source="telegram",
            chat_id=chat_id,
            room_id=room_id,
            player_id=player_id,
            username=username,
            user_tg_id=user_tg_id,
            callback_id=cb_id,
            data=data,
            message_id=message_id
        )
