"""Доменные сущности. Один класс сущности = один файл.

- ``Room``         — FSM игровой комнаты (room.py)
- ``Player``       — игрок (player.py)
- ``Question``     — вопрос (question.py)
"""

from src.domain.entities.player import Player
from src.domain.entities.question import Question, QuestionType
from src.domain.entities.room import Phase, Room

__all__: list[str] = ["Phase", "Player", "Question", "QuestionType", "Room"]
