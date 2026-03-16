"""Структурированный JSON-логгер."""

import json
import logging
import sys
from datetime import UTC, datetime


class _JSONFormatter(logging.Formatter):
    """Форматирует записи лога в однострочный JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Создать и вернуть настроенный JSON-логгер.

    Args:
        name: имя логгера (обычно __name__).
        level: уровень логирования (DEBUG / INFO / WARNING / ERROR).

    Returns:
        Экземпляр ``logging.Logger`` с JSON-выводом в stdout.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JSONFormatter())
        logger.addHandler(handler)

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger
