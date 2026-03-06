"""Workers — фоновые потребители очередей.

- ``base_worker.py``       — BaseWorker (базовый класс воркера)
- ``telegram_sender.py``   — TelegramSenderWorker (отправка сообщений в Telegram)
"""

from src.workers.base_worker import BaseWorker
from src.workers.telegram_sender import TelegramSenderWorker

__all__: list[str] = ["BaseWorker", "TelegramSenderWorker"]
