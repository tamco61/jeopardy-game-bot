"""Обработчик Telegram-обновлений (long polling).

Роутер разбирает входящий Update и направляет
в соответствующий Use Case.
"""

from __future__ import annotations

from src.application.use_cases.press_button import PressButtonUseCase
from src.application.use_cases.start_game import StartGameUseCase
from src.application.use_cases.submit_answer import SubmitAnswerUseCase
from src.infrastructure.telegram.http_client import TelegramHttpClient
from src.presentation.schemas.incoming_update import IncomingTelegramUpdateDTO


class TelegramRouter:
    """Диспетчер входящих Telegram-обновлений.

    TODO: реализовать маршрутизацию обновлений по use case'ам.
    """

    def __init__(
        self,
        telegram_client: TelegramHttpClient,
        start_game_uc: StartGameUseCase,
        press_button_uc: PressButtonUseCase,
        submit_answer_uc: SubmitAnswerUseCase,
    ) -> None:
        self._tg = telegram_client
        self._start_game = start_game_uc
        self._press_button = press_button_uc
        self._submit_answer = submit_answer_uc

    async def handle_update(self, update: IncomingTelegramUpdateDTO) -> None:
        """Обработать одно обновление от Telegram.

        TODO: реализовать логику маршрутизации.
        """
        raise NotImplementedError
