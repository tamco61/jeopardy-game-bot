from typing import Any, Dict, Optional
from pydantic import BaseModel

class OutgoingTelegramCommand(BaseModel):
    """Команда для отправки в Telegram (публикуется Core, слушается Worker)."""
    method: str
    kwargs: Dict[str, Any]
    reply_to: Optional[str] = None  # Имя временной очереди для ответа (если нужен, например message_id)
    correlation_id: Optional[str] = None # ID для сопоставления запроса и ответа (RPC)

class IncomingTelegramEvent(BaseModel):
    """Событие от Telegram (публикуется Poller, слушается Core)."""
    update_id: int
    data: Dict[str, Any] # Полный JSON update от Telegram
