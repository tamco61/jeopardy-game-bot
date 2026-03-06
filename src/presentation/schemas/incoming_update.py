"""DTO для входящих Telegram-обновлений (long polling)."""

from __future__ import annotations

from pydantic import BaseModel


class TelegramUser(BaseModel):
    """Telegram-пользователь."""

    id: int
    is_bot: bool = False
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None


class TelegramChat(BaseModel):
    """Telegram-чат."""

    id: int
    type: str = "private"
    title: str | None = None


class TelegramMessage(BaseModel):
    """Входящее сообщение."""

    message_id: int
    chat: TelegramChat
    from_user: TelegramUser | None = None
    text: str | None = None
    date: int = 0

    class Config:
        populate_by_name = True
        # Telegram шлёт поле "from", но в Python это зарезервированное слово
        fields = {"from_user": {"alias": "from"}}


class CallbackQuery(BaseModel):
    """Нажатие inline-кнопки."""

    id: str
    from_user: TelegramUser
    message: TelegramMessage | None = None
    data: str | None = None

    class Config:
        populate_by_name = True
        fields = {"from_user": {"alias": "from"}}


class IncomingTelegramUpdateDTO(BaseModel):
    """Одно обновление, полученное через getUpdates (long polling)."""

    update_id: int
    message: TelegramMessage | None = None
    callback_query: CallbackQuery | None = None
