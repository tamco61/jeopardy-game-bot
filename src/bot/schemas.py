"""DTO для входящих Telegram-обновлений (long polling)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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

    model_config = ConfigDict(populate_by_name=True)

    message_id: int
    chat: TelegramChat
    # Telegram шлёт поле "from", но в Python это зарезервированное слово
    from_user: TelegramUser | None = Field(None, alias="from")
    text: str | None = None
    date: int = 0


class CallbackQuery(BaseModel):
    """Нажатие inline-кнопки."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_user: TelegramUser = Field(alias="from")
    message: TelegramMessage | None = None
    data: str | None = None


class IncomingTelegramUpdateDTO(BaseModel):
    """Одно обновление, полученное через getUpdates (long polling)."""

    update_id: int
    message: TelegramMessage | None = None
    callback_query: CallbackQuery | None = None
