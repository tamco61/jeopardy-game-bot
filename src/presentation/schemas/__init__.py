"""DTO — Pydantic-модели для парсинга и валидации входных данных.

- ``incoming_update.py`` — IncomingTelegramUpdateDTO (long polling)
- ``ws_message.py``      — WebSocketMessageDTO
"""

from src.presentation.schemas.incoming_update import IncomingTelegramUpdateDTO
from src.presentation.schemas.ws_message import WebSocketMessageDTO

__all__: list[str] = ["IncomingTelegramUpdateDTO", "WebSocketMessageDTO"]
