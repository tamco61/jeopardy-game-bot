import uuid
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

class DomainEvent(BaseModel):
    """Базовый класс для всех событий, поступающих в ядро."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: Literal["telegram", "web"]
    chat_id: int  # Идентификатор комнаты/чата
    room_id: str  # Внутренний идентификатор лобби (например, room_12345)
    player_id: str # Идентификатор пользователя (строка, т.к. может быть uuid из web или str(tg_id))
    username: str
    user_tg_id: Optional[int] = None # Для Telegram специфичных штук (если есть)

class CommandEvent(DomainEvent):
    """Событие команды (например, пользователь ввел /start_game)."""
    command: str
    args: str = ""

class TextEvent(DomainEvent):
    """Обычное текстовое сообщение от пользователя."""
    text: str
    is_private: bool = False

class ButtonClickEvent(DomainEvent):
    """Нажатие на кнопку (Callback/Inline)."""
    callback_id: str
    data: str
    message_id: int # ID сообщения, к которому прикреплена кнопка (для редактирования)

class DocumentEvent(DomainEvent):
    """Загрузка файла."""
    file_id: str
    file_name: str
    caption: str = ""
