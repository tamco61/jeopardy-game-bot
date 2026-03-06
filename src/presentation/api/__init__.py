"""API — входные ворота приложения.

- ``telegram_router.py``  — обработчик Telegram-обновлений (long polling)
- ``websocket_router.py`` — WebSocket-роутер для фронтенда
"""

from src.presentation.api.telegram_router import TelegramRouter
from src.presentation.api.websocket_router import WebSocketRouter

__all__: list[str] = ["TelegramRouter", "WebSocketRouter"]
