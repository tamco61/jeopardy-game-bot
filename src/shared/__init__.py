"""Сквозные утилиты.

- ``config.py``       — AppSettings (pydantic-settings)
- ``di_container.py`` — сборка зависимостей (DI)
- ``logger.py``       — JSON-логгер
"""

from src.shared.config import AppSettings

__all__: list[str] = ["AppSettings"]
