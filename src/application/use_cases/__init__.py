"""Use Cases — сценарии использования «Своей игры».

- ``StartGameUseCase``    — старт раунда (start_game.py)
- ``PressButtonUseCase``  — нажатие кнопки (press_button.py)
- ``SubmitAnswerUseCase`` — отправка ответа (submit_answer.py)
"""

from src.application.use_cases.press_button import PressButtonUseCase
from src.application.use_cases.start_game import StartGameUseCase
from src.application.use_cases.submit_answer import SubmitAnswerUseCase

__all__: list[str] = [
    "PressButtonUseCase",
    "StartGameUseCase",
    "SubmitAnswerUseCase",
]
