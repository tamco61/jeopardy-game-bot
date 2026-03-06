"""Порт для работы с игровыми данными (Postgres).

Статический контент: пакеты, раунды, темы, вопросы, пользователи.
История игр: game_sessions, game_players.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.question import Question


class IGameRepository(ABC):
    """Абстракция работы с БД (статические данные + история)."""

    # ── Вопросы ─────────────────────────────────────

    @abstractmethod
    async def get_question_by_id(self, question_id: int) -> Question | None:
        """Получить вопрос по ID."""
        ...

    @abstractmethod
    async def get_questions_by_theme(self, theme_id: int) -> list[Question]:
        """Получить все вопросы темы."""
        ...

    @abstractmethod
    async def get_random_question(self, theme_id: int | None = None) -> Question | None:
        """Получить случайный вопрос, опционально по теме."""
        ...

    # ── Темы ────────────────────────────────────────

    @abstractmethod
    async def get_themes_by_round(self, round_id: int) -> list[dict]:
        """Получить все темы раунда (id, name)."""
        ...

    # ── Раунды ──────────────────────────────────────

    @abstractmethod
    async def get_rounds_by_package(self, package_id: int) -> list[dict]:
        """Получить все раунды пакета (id, name, is_final)."""
        ...
