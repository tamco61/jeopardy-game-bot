"""Адаптер Telegram Bot API.

- ``http_client.py`` — TelegramHttpClient (aiohttp-клиент, long polling)
"""

from src.infrastructure.telegram.http_client import TelegramHttpClient

__all__: list[str] = ["TelegramHttpClient"]
