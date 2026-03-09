"""Сущность «Комната» — FSM ядро «Своей Игры».

Чистая бизнес-логика без I/O. Все переходы между состояниями
валидируются — при невалидном переходе бросается InvalidTransitionError.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from enum import Enum

from src.domain.errors import (
    InvalidTransitionError,
    PlayerBlockedError,
    PlayerNotFoundError,
)
from src.domain.player import Player
from src.domain.question import Question, QuestionType


class Phase(str, Enum):
    """Фазы (состояния) FSM игровой комнаты."""

    LOBBY = "lobby"
    BOARD_VIEW = "board_view"
    SPECIAL_EVENT = "special_event"
    READING = "reading"
    WAITING_FOR_PUSH = "waiting_for_push"
    ANSWERING = "answering"
    FINAL_ROUND = "final_round"
    FINAL_STAKE = "final_stake"
    FINAL_ANSWER = "final_answer"
    RESULTS = "results"
    PAUSE = "pause"


class Room(BaseModel):
    """Игровая комната «Своей Игры».

    FSM-переходы::

        LOBBY -> BOARD_VIEW (все игроки ready)
        BOARD_VIEW -> READING | SPECIAL_EVENT (выбран вопрос)
        SPECIAL_EVENT -> READING (после обработки кота/аукциона)
        READING -> WAITING_FOR_PUSH (ведущий активировал кнопки)
        WAITING_FOR_PUSH -> ANSWERING (кто-то первый нажал)
        ANSWERING -> BOARD_VIEW (верный ответ)
        ANSWERING -> WAITING_FOR_PUSH (неверный, можно ещё отвечать)
        ANSWERING -> BOARD_VIEW (неверный, никто не может ответить)
        BOARD_VIEW -> FINAL_ROUND (все вопросы сыграны)
        FINAL_ROUND -> FINAL_STAKE
        FINAL_STAKE -> FINAL_ANSWER
        FINAL_ANSWER -> RESULTS
        Любое (кроме LOBBY) -> PAUSE -> обратно
    """

    room_id: str
    chat_id: int
    phase: Phase = Phase.LOBBY
    players: dict[str, Player] = Field(default_factory=dict)

    # Ведущий (HOST)
    host_id: str = ""
    host_telegram_id: int = 0

    # Привязка пакета и трекинг состояния по доске
    package_id: int | None = None
    current_round_id: int | None = None
    closed_questions: list[int] = Field(default_factory=list)

    # Текущий вопрос (заполняется при выборе с табло)
    current_question: Question | None = None
    answering_player_id: str | None = None
    answering_player_telegram_id: int | None = None  # для отправки ЛС отвечающему
    player_answer: str | None = None

    # Финальный раунд
    final_question: Question | None = None
    final_stakes: dict[str, int] = Field(default_factory=dict)
    final_answers: dict[str, str] = Field(default_factory=dict)

    # Пауза — запоминаем, куда вернуться
    paused_from: Phase | None = Field(default=None, repr=False)

    # ────────────────────────────────────────────────
    #  Управление игроками
    # ────────────────────────────────────────────────

    def add_player(self, player: Player) -> None:
        """Добавить игрока (только в LOBBY)."""
        self._assert_phase(Phase.LOBBY, "add_player")
        self.players[player.player_id] = player

    def get_player(self, player_id: str) -> Player:
        """Получить игрока или бросить PlayerNotFoundError."""
        player = self.players.get(player_id)
        if player is None:
            raise PlayerNotFoundError(player_id)
        return player

    def mark_player_ready(self, player_id: str) -> None:
        """Игрок нажал «Готов»."""
        self._assert_phase(Phase.LOBBY, "mark_ready")
        self.get_player(player_id).mark_ready()

    @property
    def all_ready(self) -> bool:
        """Все ли игроки готовы (и их >= 2)."""
        return len(self.players) >= 2 and all(
            p.is_ready for p in self.players.values()
        )

    # ────────────────────────────────────────────────
    #  LOBBY -> BOARD_VIEW
    # ────────────────────────────────────────────────

    def start_game(self) -> None:
        """Все готовы — переход на табло."""
        self._assert_phase(Phase.LOBBY, "start_game")
        if not self.all_ready:
            msg = "Не все игроки готовы"
            raise InvalidTransitionError(self.phase.value, msg)
        self.phase = Phase.BOARD_VIEW

    # ────────────────────────────────────────────────
    #  BOARD_VIEW -> READING / SPECIAL_EVENT
    # ────────────────────────────────────────────────

    def select_question(self, question: Question) -> None:
        """Выбрать вопрос с табло."""
        self._assert_phase(Phase.BOARD_VIEW, "select_question")
        self.current_question = question
        self.answering_player_id = None

        # Разблокируем всех к новому вопросу
        for p in self.players.values():
            p.unblock()

        if question.question_type in (
            QuestionType.CAT_IN_BAG,
            QuestionType.AUCTION,
        ):
            self.phase = Phase.SPECIAL_EVENT
        else:
            self.phase = Phase.READING

    # ────────────────────────────────────────────────
    #  SPECIAL_EVENT -> READING
    # ────────────────────────────────────────────────

    def resolve_special_event(self) -> None:
        """Кот/Аукцион обработан — переходим к чтению вопроса."""
        self._assert_phase(Phase.SPECIAL_EVENT, "resolve_special_event")
        self.phase = Phase.READING

    # ────────────────────────────────────────────────
    #  READING -> WAITING_FOR_PUSH
    # ────────────────────────────────────────────────

    def activate_buzzer(self) -> None:
        """Вопрос прочитан, кнопки активны."""
        self._assert_phase(Phase.READING, "activate_buzzer")
        self.phase = Phase.WAITING_FOR_PUSH

    # ────────────────────────────────────────────────
    #  WAITING_FOR_PUSH -> ANSWERING  (гонка)
    # ────────────────────────────────────────────────

    def press_button(self, player_id: str) -> None:
        """Игрок нажал кнопку первым (результат гонки).

        Вызывается ПОСЛЕ подтверждения через try_capture_button в Use Case.

        Raises:
            PlayerBlockedError: если игрок заблокирован на этот вопрос.
        """
        self._assert_phase(Phase.WAITING_FOR_PUSH, "press_button")
        player = self.get_player(player_id)

        if player.is_blocked_this_question:
            raise PlayerBlockedError(player.display_name)

        self.answering_player_id = player_id
        self.phase = Phase.ANSWERING

    # ────────────────────────────────────────────────
    #  ANSWERING -> BOARD_VIEW / WAITING_FOR_PUSH
    # ────────────────────────────────────────────────

    def provide_answer(self, player_id: str, answer: str) -> None:
        """Игрок даёт ответ, ожидая вердикта ведущего."""
        self._assert_phase(Phase.ANSWERING, "provide_answer")

        if self.answering_player_id != player_id:
            msg = "Отвечать может только тот, кто нажал кнопку"
            raise InvalidTransitionError(self.phase.value, msg)

        self.player_answer = answer

    def resolve_answer(self, player_id: str, is_correct: bool) -> None:
        """Ведущий выносит вердикт по ответу игрока."""
        self._assert_phase(Phase.ANSWERING, "resolve_answer")

        if self.answering_player_id != player_id:
            msg = "Вердикт относится не к тому игроку, который отвечает"
            raise InvalidTransitionError(self.phase.value, msg)

        if self.current_question is None:
            msg = "Нет текущего вопроса"
            raise InvalidTransitionError(self.phase.value, msg)

        player = self.get_player(player_id)

        if is_correct:
            player.add_score(self.current_question.value)
            self._end_question()
        else:
            player.deduct_score(self.current_question.value)
            player.block_for_question()
            self.answering_player_id = None
            self.player_answer = None

            if self._has_eligible_players():
                self.phase = Phase.WAITING_FOR_PUSH
            else:
                self._end_question()

    def submit_answer(self, player_id: str, answer: str) -> bool:
        """Игрок даёт ответ.

        Returns:
            True — правильный, False — неправильный.
        """
        self._assert_phase(Phase.ANSWERING, "submit_answer")

        if self.answering_player_id != player_id:
            msg = "Отвечать может только тот, кто нажал кнопку"
            raise InvalidTransitionError(self.phase.value, msg)

        if self.current_question is None:
            msg = "Нет текущего вопроса"
            raise InvalidTransitionError(self.phase.value, msg)

        player = self.get_player(player_id)
        correct = self.current_question.check_answer(answer)

        if correct:
            player.add_score(self.current_question.value)
            self._end_question()
            return True

        # Неверный ответ
        player.deduct_score(self.current_question.value)
        player.block_for_question()
        self.answering_player_id = None

        # Есть ли кто-то, кто ещё может ответить?
        if self._has_eligible_players():
            self.phase = Phase.WAITING_FOR_PUSH
        else:
            self._end_question()

        return False

    # ────────────────────────────────────────────────
    #  BOARD_VIEW -> FINAL_ROUND -> ... -> RESULTS
    # ────────────────────────────────────────────────

    def start_final_round(self, question: Question) -> None:
        """Перейти к финальному раунду."""
        self._assert_phase(Phase.BOARD_VIEW, "start_final_round")
        self.final_question = question
        self.final_stakes = {}
        self.final_answers = {}
        self.phase = Phase.FINAL_ROUND

    def open_stakes(self) -> None:
        """Финал: открыть приём ставок."""
        self._assert_phase(Phase.FINAL_ROUND, "open_stakes")
        self.phase = Phase.FINAL_STAKE

    def place_stake(self, player_id: str, stake: int) -> None:
        """Игрок делает ставку (не больше своего счёта)."""
        self._assert_phase(Phase.FINAL_STAKE, "place_stake")
        player = self.get_player(player_id)
        clamped = max(0, min(stake, player.score))
        self.final_stakes[player_id] = clamped

    def close_stakes(self) -> None:
        """Все ставки приняты — переход к ответам."""
        self._assert_phase(Phase.FINAL_STAKE, "close_stakes")
        self.phase = Phase.FINAL_ANSWER

    def submit_final_answer(self, player_id: str, answer: str) -> None:
        """Игрок отправляет финальный ответ."""
        self._assert_phase(Phase.FINAL_ANSWER, "submit_final_answer")
        self.get_player(player_id)  # проверяем что игрок существует
        self.final_answers[player_id] = answer

    def resolve_final(self) -> dict[str, bool]:
        """Подвести итоги финала.

        Returns:
            Словарь player_id → правильность ответа.
        """
        self._assert_phase(Phase.FINAL_ANSWER, "resolve_final")

        if self.final_question is None:
            msg = "Нет финального вопроса"
            raise InvalidTransitionError(self.phase.value, msg)

        results: dict[str, bool] = {}
        for pid, answer in self.final_answers.items():
            correct = self.final_question.check_answer(answer)
            results[pid] = correct
            player = self.get_player(pid)
            stake = self.final_stakes.get(pid, 0)
            if correct:
                player.add_score(stake)
            else:
                player.deduct_score(stake)

        self.phase = Phase.RESULTS
        return results

    # ────────────────────────────────────────────────
    #  PAUSE (из любой фазы кроме LOBBY)
    # ────────────────────────────────────────────────

    def pause(self) -> None:
        """Поставить игру на паузу."""
        if self.phase in (Phase.LOBBY, Phase.PAUSE):
            raise InvalidTransitionError(self.phase.value, "pause")
        self.paused_from = self.phase
        self.phase = Phase.PAUSE

    def resume(self) -> None:
        """Снять паузу — вернуться в прежнее состояние."""
        self._assert_phase(Phase.PAUSE, "resume")
        if self.paused_from is None:
            msg = "Неизвестное состояние до паузы"
            raise InvalidTransitionError(self.phase.value, msg)
        self.phase = self.paused_from
        self.paused_from = None

    # ────────────────────────────────────────────────
    #  Helpers (private)
    # ────────────────────────────────────────────────

    def _assert_phase(self, expected: Phase, action: str) -> None:
        if self.phase != expected:
            raise InvalidTransitionError(self.phase.value, action)

    def _has_eligible_players(self) -> bool:
        """Есть ли хотя бы один незаблокированный игрок?"""
        return any(
            not p.is_blocked_this_question for p in self.players.values()
        )

    def _end_question(self) -> None:
        """Завершить текущий вопрос, закрыть его на табло и вернуться."""
        if self.current_question and self.current_question.question_id:
            self.closed_questions.append(self.current_question.question_id)
            
        self.current_question = None
        self.answering_player_id = None
        self.phase = Phase.BOARD_VIEW
