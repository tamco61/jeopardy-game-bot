"""Юнит-тесты доменной логики «Своей Игры».

1. FSM-переходы Room.
2. PressButtonUseCase с моком RedisStateRepository.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.application.press_button import PressButtonUseCase
from src.domain.errors import InvalidTransitionError, PlayerBlockedError
from src.domain.player import Player
from src.domain.question import Question, QuestionType
from src.domain.room import Phase, Room
from src.infrastructure.redis_repo import RedisStateRepository

# ────────────────────────────────────────────────────
#  Фикстуры
# ────────────────────────────────────────────────────


@pytest.fixture
def player_alice() -> Player:
    return Player(player_id="p1", telegram_id=111, username="alice")


@pytest.fixture
def player_bob() -> Player:
    return Player(player_id="p2", telegram_id=222, username="bob")


@pytest.fixture
def sample_question() -> Question:
    return Question(
        question_id=1,
        theme_name="География",
        text="Столица Франции?",
        answer="Париж",
        value=200,
    )


@pytest.fixture
def cat_question() -> Question:
    return Question(
        question_id=2,
        theme_name="Наука",
        text="Формула воды?",
        answer="H2O",
        value=300,
        question_type=QuestionType.CAT_IN_BAG,
    )


@pytest.fixture
def lobby_room(player_alice: Player, player_bob: Player) -> Room:
    """Комната в LOBBY с двумя игроками."""
    room = Room(room_id="r1", chat_id=100)
    room.add_player(player_alice)
    room.add_player(player_bob)
    return room


@pytest.fixture
def board_room(lobby_room: Room) -> Room:
    """Комната в BOARD_VIEW (все ready, игра начата)."""
    for p in lobby_room.players.values():
        p.mark_ready()
    lobby_room.start_game()
    return lobby_room


# ────────────────────────────────────────────────────
#  1. FSM — Переходы состояний
# ────────────────────────────────────────────────────


class TestFSMTransitions:
    """Тесты переходов FSM."""

    def test_initial_phase_is_lobby(self) -> None:
        room = Room(room_id="r1", chat_id=100)
        assert room.phase == Phase.LOBBY

    def test_add_player_only_in_lobby(self, board_room: Room) -> None:
        with pytest.raises(InvalidTransitionError):
            board_room.add_player(
                Player(player_id="p3", telegram_id=333, username="eve"),
            )

    def test_start_game_requires_all_ready(self, lobby_room: Room) -> None:
        """Нельзя начать, если не все готовы."""
        lobby_room.players["p1"].mark_ready()
        # p2 ещё не ready
        with pytest.raises(InvalidTransitionError):
            lobby_room.start_game()

    def test_start_game_requires_min_2_players(self) -> None:
        room = Room(room_id="r1", chat_id=100)
        p = Player(player_id="p1", telegram_id=111, username="alice")
        room.add_player(p)
        p.mark_ready()
        with pytest.raises(InvalidTransitionError):
            room.start_game()

    def test_lobby_to_board_view(self, lobby_room: Room) -> None:
        for p in lobby_room.players.values():
            p.mark_ready()
        lobby_room.start_game()
        assert lobby_room.phase == Phase.BOARD_VIEW

    def test_select_normal_question(
        self,
        board_room: Room,
        sample_question: Question,
    ) -> None:
        board_room.select_question(sample_question)
        assert board_room.phase == Phase.READING
        assert board_room.current_question is sample_question

    def test_select_cat_question_goes_to_special(
        self,
        board_room: Room,
        cat_question: Question,
    ) -> None:
        board_room.select_question(cat_question)
        assert board_room.phase == Phase.SPECIAL_EVENT

    def test_special_event_to_reading(
        self,
        board_room: Room,
        cat_question: Question,
    ) -> None:
        board_room.select_question(cat_question)
        board_room.resolve_special_event()
        assert board_room.phase == Phase.READING

    def test_reading_to_waiting_for_push(
        self,
        board_room: Room,
        sample_question: Question,
    ) -> None:
        board_room.select_question(sample_question)
        board_room.activate_buzzer()
        assert board_room.phase == Phase.WAITING_FOR_PUSH

    def test_press_button_to_answering(
        self,
        board_room: Room,
        sample_question: Question,
    ) -> None:
        board_room.select_question(sample_question)
        board_room.activate_buzzer()
        board_room.press_button("p1")
        assert board_room.phase == Phase.ANSWERING
        assert board_room.answering_player_id == "p1"

    def test_correct_answer_returns_to_board(
        self,
        board_room: Room,
        sample_question: Question,
    ) -> None:
        board_room.select_question(sample_question)
        board_room.activate_buzzer()
        board_room.press_button("p1")
        board_room.provide_answer("p1", "Париж")
        board_room.resolve_answer("p1", True)
        assert board_room.phase == Phase.BOARD_VIEW
        assert board_room.players["p1"].score == 200
        # p1 ответил верно, теперь он выбирает
        assert board_room.selecting_player_id == "p1"

    def test_wrong_answer_back_to_waiting(
        self,
        board_room: Room,
        sample_question: Question,
    ) -> None:
        """Неправильный ответ — кнопка снова доступна для других."""
        board_room.select_question(sample_question)
        board_room.activate_buzzer()
        board_room.press_button("p1")
        board_room.provide_answer("p1", "Лондон")
        board_room.resolve_answer("p1", False)
        assert board_room.phase == Phase.WAITING_FOR_PUSH
        assert board_room.players["p1"].is_blocked_this_question
        assert board_room.players["p1"].score == -200

    def test_all_wrong_returns_to_board(
        self,
        board_room: Room,
        sample_question: Question,
    ) -> None:
        """Все ошиблись — возврат на табло."""
        board_room.select_question(sample_question)
        board_room.activate_buzzer()

        # p1 ошибается
        board_room.press_button("p1")
        board_room.provide_answer("p1", "Лондон")
        board_room.resolve_answer("p1", False)

        # p2 ошибается — больше некому
        board_room.press_button("p2")
        board_room.provide_answer("p2", "Берлин")
        board_room.resolve_answer("p2", False)

        assert board_room.phase == Phase.BOARD_VIEW

    def test_blocked_player_cannot_press(
        self,
        board_room: Room,
        sample_question: Question,
    ) -> None:
        board_room.select_question(sample_question)
        board_room.activate_buzzer()

        # p1 ошибается
        board_room.press_button("p1")
        board_room.provide_answer("p1", "Лондон")
        board_room.resolve_answer("p1", False)

        # p1 пытается снова
        with pytest.raises(PlayerBlockedError):
            board_room.press_button("p1")

    def test_round_finished_detection(self, board_room: Room, sample_question: Question) -> None:
        """Проверка детекции завершения раунда."""
        q1_id = 1
        q2_id = 2
        
        # Сначала вопросы не закрыты
        assert board_room.is_round_finished([q1_id, q2_id]) is False
        
        # Закрываем один
        board_room.closed_questions.append(q1_id)
        assert board_room.is_round_finished([q1_id, q2_id]) is False
        
        # Закрываем второй
        board_room.closed_questions.append(q2_id)
        assert board_room.is_round_finished([q1_id, q2_id]) is True

    def test_wrong_phase_raises_error(self, lobby_room: Room) -> None:
        """Нельзя жать кнопку в LOBBY."""
        with pytest.raises(InvalidTransitionError):
            lobby_room.press_button("p1")


# ────────────────────────────────────────────────────
#  2. FSM — Пауза
# ────────────────────────────────────────────────────


class TestPause:
    """Тесты паузы/возобновления."""

    def test_pause_and_resume(
        self,
        board_room: Room,
        sample_question: Question,
    ) -> None:
        board_room.select_question(sample_question)
        board_room.activate_buzzer()
        assert board_room.phase == Phase.WAITING_FOR_PUSH

        board_room.pause()
        assert board_room.phase == Phase.PAUSE

        board_room.resume()
        assert board_room.phase == Phase.WAITING_FOR_PUSH

    def test_cannot_pause_in_lobby(self) -> None:
        room = Room(room_id="r1", chat_id=100)
        with pytest.raises(InvalidTransitionError):
            room.pause()

    def test_cannot_pause_twice(self, board_room: Room) -> None:
        board_room.pause()
        with pytest.raises(InvalidTransitionError):
            board_room.pause()


# ────────────────────────────────────────────────────
#  3. FSM — Финальный раунд
# ────────────────────────────────────────────────────


class TestFinalRound:
    """Тесты финального раунда."""

    def test_final_round_flow(self, board_room: Room) -> None:
        final_q = Question(
            question_id=99,
            theme_name="Финал",
            text="Самая длинная река?",
            answer="Нил",
            value=0,
        )
        # Даём обоим ненулевой счёт
        board_room.players["p1"].add_score(500)
        board_room.players["p2"].add_score(300)

        board_room.start_final_round(final_q)
        assert board_room.phase == Phase.FINAL_ROUND

        board_room.open_stakes()
        assert board_room.phase == Phase.FINAL_STAKE

        board_room.place_stake("p1", 200)
        board_room.place_stake("p2", 300)

        board_room.close_stakes()
        assert board_room.phase == Phase.FINAL_ANSWER

        board_room.submit_final_answer("p1", "Нил")
        board_room.submit_final_answer("p2", "Амазонка")

        board_room.final_verdicts = {"p1": True, "p2": False}
        results = board_room.resolve_final()
        assert board_room.phase == Phase.RESULTS

        assert results["p1"] is True
        assert results["p2"] is False
        assert board_room.players["p1"].score == 700  # 500 + 200
        assert board_room.players["p2"].score == 0  # 300 - 300

    def test_stake_clamped_to_score(self, board_room: Room) -> None:
        """Ставка не может превышать счёт игрока."""
        final_q = Question(
            question_id=99, theme_name="Ф", text="?", answer="a", value=0,
        )
        board_room.players["p1"].add_score(100)
        board_room.start_final_round(final_q)
        board_room.open_stakes()

        board_room.place_stake("p1", 9999)
        assert board_room.final_stakes["p1"] == 100


# ────────────────────────────────────────────────────
#  4. PressButtonUseCase (с моком)
# ────────────────────────────────────────────────────


class TestPressButtonUseCase:
    """Тесты Use Case нажатия кнопки с моком RedisStateRepository."""

    @pytest.fixture
    def room_waiting(
        self,
        board_room: Room,
        sample_question: Question,
    ) -> Room:
        """Комната в фазе WAITING_FOR_PUSH."""
        board_room.select_question(sample_question)
        board_room.activate_buzzer()
        return board_room

    @pytest.fixture
    def mock_repo(self, room_waiting: Room) -> AsyncMock:
        """Мок RedisStateRepository."""
        repo = AsyncMock(spec=RedisStateRepository)
        repo.get_room.return_value = room_waiting
        repo.try_capture_button.return_value = True
        return repo

    @pytest.mark.asyncio
    async def test_successful_capture(self, mock_repo: AsyncMock) -> None:
        uc = PressButtonUseCase(state_repo=mock_repo)
        result = await uc.execute(room_id="r1", player_id="p1")

        assert result.captured is True
        assert result.player_id == "p1"
        mock_repo.try_capture_button.assert_awaited_once_with("r1", "p1")
        mock_repo.save_room.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lost_race(self, mock_repo: AsyncMock) -> None:
        """Игрок проиграл гонку (SETNX вернул False)."""
        mock_repo.try_capture_button.return_value = False

        uc = PressButtonUseCase(state_repo=mock_repo)
        result = await uc.execute(room_id="r1", player_id="p1")

        assert result.captured is False
        assert result.error is not None
        mock_repo.get_room.assert_not_awaited()  # даже не пошли в Redis за Room

    @pytest.mark.asyncio
    async def test_room_not_found(self, mock_repo: AsyncMock) -> None:
        mock_repo.get_room.return_value = None

        uc = PressButtonUseCase(state_repo=mock_repo)
        result = await uc.execute(room_id="r1", player_id="p1")

        assert result.captured is False
        assert "не найдена" in result.error

    @pytest.mark.asyncio
    async def test_blocked_player_rollback(
        self,
        mock_repo: AsyncMock,
        room_waiting: Room,
    ) -> None:
        """Заблокированный игрок: кнопка откатывается."""
        room_waiting.players["p1"].block_for_question()

        uc = PressButtonUseCase(state_repo=mock_repo)
        result = await uc.execute(room_id="r1", player_id="p1")

        assert result.captured is False
        mock_repo.release_button.assert_awaited_once_with("r1")
