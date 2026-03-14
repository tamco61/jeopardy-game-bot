from typing import Any

from pydantic import BaseModel


class OutgoingTelegramCommand(BaseModel):
    """Команда для отправки в Telegram (публикуется Core, слушается Worker)."""
    method: str
    kwargs: dict[str, Any]
    reply_to: str | None = None  # Имя временной очереди для ответа (если нужен, например message_id)
    correlation_id: str | None = None  # ID для сопоставления запроса и ответа (RPC)


class IncomingTelegramEvent(BaseModel):
    """Событие от Telegram (публикуется Poller, слушается Core)."""
    update_id: int
    data: dict[str, Any]  # Полный JSON update от Telegram


class WebUIUpdate(BaseModel):
    """Обновление состояния UI для Web-клиентов."""
    room_id: str
    event_type: str  # 'board_updated', 'buzzer_captured', 'question_opened', etc.
    payload: dict[str, Any]
