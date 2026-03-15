"""Сущность «Игрок» — «Своя Игра»."""

from __future__ import annotations

from pydantic import BaseModel


class Player(BaseModel):
    """Игрок, привязанный к Telegram-аккаунту."""

    player_id: str  # уникальный ID (str для совместимости с Redis key)
    telegram_id: int
    username: str
    first_name: str = ""
    score: int = 0
    is_ready: bool = False  # отметка «Готов» в лобби
    is_blocked_this_question: bool = False  # заблокирован на текущий вопрос

    # ── Бизнес-методы ────────────────────────────────

    def add_score(self, points: int) -> None:
        """Начислить очки за правильный ответ."""
        self.score += points

    def deduct_score(self, points: int) -> None:
        """Списать очки за неправильный ответ."""
        self.score -= points

    def mark_ready(self) -> None:
        self.is_ready = True

    def mark_not_ready(self) -> None:
        self.is_ready = False

    def block_for_question(self) -> None:
        """Заблокировать на текущий вопрос (неверный ответ / фальстарт)."""
        self.is_blocked_this_question = True

    def unblock(self) -> None:
        """Разблокировать для нового вопроса."""
        self.is_blocked_this_question = False

    @property
    def display_name(self) -> str:
        if self.telegram_id == 0:
            return self.username or self.first_name
        return f"@{self.username}" if self.username else self.first_name
