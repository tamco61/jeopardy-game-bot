"""Сущность «Вопрос» — «Своя Игра»."""

from __future__ import annotations

from pydantic import BaseModel
from enum import Enum


class QuestionType(str, Enum):
    """Тип вопроса."""

    NORMAL = "normal"
    CAT_IN_BAG = "cat_in_bag"  # Кот в мешке
    AUCTION = "auction"  # Аукцион


class Question(BaseModel):
    """Один вопрос из пакета «Своей Игры»."""

    question_id: int | None  # None для ещё не сохранённых
    theme_name: str
    text: str
    answer: str
    value: int = 100 # стоимость (100, 200, …)
    question_type: QuestionType = QuestionType.NORMAL

    def check_answer(self, user_answer: str) -> bool:
        """Проверить ответ (без учёта регистра, с обрезкой пробелов)."""
        return self.answer.strip().lower() == user_answer.strip().lower()
