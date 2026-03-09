import asyncio
import random

import redis.asyncio as aioredis
from sqlalchemy.exc import SQLAlchemyError

from src.application.press_button import PressButtonUseCase
from src.application.select_question import (
    SelectQuestionDTO,
    SelectQuestionUseCase,
)
from src.application.special_events import (
    CloseFinalStakeUseCase,
    PlaceStakeUseCase,
    StartFinalStakeUseCase,
)
from src.application.start_game import StartGameDTO, StartGameUseCase
from src.application.submit_answer import SubmitAnswerDTO, SubmitAnswerUseCase
from src.bot.ui import JeopardyUI
from src.domain.room import Phase, Room
from src.infrastructure.database.postgres_repo import PostgresGameRepository
from src.infrastructure.redis_repo import RedisStateRepository
from src.shared.logger import get_logger

logger = get_logger(__name__)

class GameHandler:
    """Обработчик игрового процесса (старт, выбор вопроса, ответы, вердикты)."""

    def __init__(
        self,
        ui: JeopardyUI,
        game_repo: PostgresGameRepository,
        state_repo: RedisStateRepository,
        start_game_uc: StartGameUseCase,
        press_button_uc: PressButtonUseCase,
        submit_answer_uc: SubmitAnswerUseCase,
        select_question_uc: SelectQuestionUseCase,
        start_final_stake_uc: StartFinalStakeUseCase,
        place_stake_uc: PlaceStakeUseCase,
        close_final_stake_uc: CloseFinalStakeUseCase,
    ) -> None:
        self._ui = ui
        self._game_repo = game_repo
        self._state_repo = state_repo
        self._start_game = start_game_uc
        self._press_button = press_button_uc
        self._submit_answer = submit_answer_uc
        self._select_question = select_question_uc
        self._start_final_stake = start_final_stake_uc
        self._place_stake = place_stake_uc
        self._close_final_stake = close_final_stake_uc

    async def handle_start_game(self, chat_id: int, player_id: str, user_telegram_id: int) -> None:
        # todo: Временно хардкодим pack_id=1
        start_dto = StartGameDTO(
            lobby_id="room_1",
            chat_id=chat_id,
            host_player_id=player_id,
            host_telegram_id=user_telegram_id,
            pack_id=1,
        )
        try:
            result = await self._start_game.execute(start_dto)
            await self._ui._tg.send_message(chat_id, result.message)

            room = await self._state_repo.get_room("room_1")
            if room and room.phase == Phase.BOARD_VIEW:
                await self.render_board(chat_id, room)

        except (SQLAlchemyError, aioredis.RedisError) as e:
            logger.error(f"Ошибка старта игры: {e}")
            await self._ui._tg.send_message(chat_id, f"Ошибка старта игры: {e}")

    async def handle_select_question(self, chat_id: int, player_id: str, q_id: int, room: Room) -> None:
        try:
            dto = SelectQuestionDTO(
                room_id="room_1",
                player_id=player_id,
                question_id=q_id,
            )
            res = await self._select_question.execute(dto)

            await self._ui.show_question(room.chat_id, res.question_text, res.question_value)

            if res.phase == Phase.READING.value:
                kb = {
                    "inline_keyboard": [[{"text": "🔴 Ждите...", "callback_data": "btn_room_1"}]]
                }
                sent_msg = await self._ui._tg.send_message(
                    room.chat_id,
                    "Ожидайте активации кнопки...",
                    reply_markup=kb,
                )
                if "result" in sent_msg:
                    msg_id = sent_msg["result"]["message_id"]
                    asyncio.create_task(
                        self._activate_button(room.chat_id, msg_id, random.uniform(2.0, 5.0))
                    )
            elif res.phase == Phase.SPECIAL_EVENT.value:
                await self._ui._tg.send_message(
                    chat_id,
                    "Спец-ивент!\n(Заглушка для Кота в мешке / Аукциона)",
                )
            elif res.phase == Phase.FINAL_ROUND.value:
                kb = {
                    "inline_keyboard": [[{"text": "🏁 Прием ставок", "callback_data": "final_start_stakes"}]]
                }
                await self._ui._tg.send_message(
                    chat_id,
                    "ФИНАЛЬНЫЙ РАУНД! Ведущий: откройте прием ставок.",
                    reply_markup=kb,
                )

        except (SQLAlchemyError, aioredis.RedisError) as e:
            logger.error(f"Ошибка при выборе вопроса: {e}")

    async def handle_press_button(self, chat_id: int, player_id: str, username: str, message_id: int, callback_query_id: str) -> None:
        result = await self._press_button.execute("room_1", player_id)

        if result.captured:
            room_now = await self._state_repo.get_room("room_1")
            if room_now:
                room_now.answering_player_telegram_id = int(player_id)
                await self._state_repo.save_room(room_now)

                q_text = room_now.current_question.text if room_now.current_question else "Вопрос"

                await self._ui._tg.edit_message_text(
                    chat_id=room_now.chat_id,
                    message_id=message_id,
                    text=f"🛑 Отвечает @{username}! Ждём ответа в личку...",
                )

                await self._ui._tg.send_message(
                    chat_id=int(player_id),
                    text=f"❓ Ты первый! Вопрос:\n\n*{q_text}*\n\nНапиши ответ прямо в это ЛС."
                )
                await self._ui._tg.answer_callback_query(callback_query_id, text="Твой ответ!")
        else:
            await self._ui._tg.answer_callback_query(
                callback_query_id=callback_query_id,
                text=result.error or "Кто-то успел раньше!"
            )

    async def handle_submit_answer(self, chat_id: int, player_id: str, username: str, text: str, room: Room, is_private: bool) -> None:
        dto = SubmitAnswerDTO(room_id="room_1", player_id=player_id, answer=text)
        try:
            await self._submit_answer.execute(dto)
            room = await self._state_repo.get_room("room_1")
            if not room: return

            if room.phase == Phase.ANSWERING:
                if not room.host_telegram_id:
                    await self._ui._tg.send_message(room.chat_id, "⚠️ Ошибка: ID ведущего не найден.")
                    return

                keyboard = {
                    "inline_keyboard": [[
                        {"text": "✅ Верно", "callback_data": f"verdict:yes:{player_id}"},
                        {"text": "❌ Неверно", "callback_data": f"verdict:no:{player_id}"}
                    ]]
                }
                await self._ui._tg.send_message(
                    chat_id=room.host_telegram_id,
                    text=f"Игрок @{username} ответил: *{text}*\nВаш вердикт:",
                    reply_markup=keyboard,
                )

                await self._ui._tg.send_message(
                    chat_id=room.chat_id,
                    text=f"Игрок @{username} дал ответ. Ждём вердикт ведущего...",
                )
                if is_private:
                    await self._ui._tg.send_message(chat_id, "✅ Твой ответ передан ведущему!")

            elif room.phase == Phase.FINAL_ANSWER:
                await self._ui._tg.send_message(room.chat_id, f"Финальный ответ от @{username} принят.")

        except (SQLAlchemyError, aioredis.RedisError) as e:
            logger.error(f"Ошибка при сохранении ответа: {e}")

    async def handle_verdict(self, chat_id: int, message_id: int, data: str, room: Room) -> None:
        parts = data.split(":")
        if len(parts) == 3 and room and room.phase == Phase.ANSWERING:
            verdict, target_player_id = parts[1], parts[2]
            is_correct = verdict == "yes"
            try:
                room.resolve_answer(target_player_id, is_correct)
                await self._state_repo.save_room(room)
                await self._state_repo.release_button("room_1")

                verdict_text = "✅ Верно" if is_correct else "❌ Неверно"
                await self._ui._tg.edit_message_text(
                    chat_id=chat_id, message_id=message_id, text=f"Вердикт: {verdict_text}"
                )

                await self._ui.show_verdict(room.chat_id, verdict_text)

                # Проверка завершения раунда
                if room.current_round_id:
                    board_data = await self._game_repo.get_board_for_round(room.current_round_id)
                    all_q_ids = [q["id"] for theme in board_data for q in theme["questions"]]
                    if room.is_round_finished(all_q_ids):
                        await self._handle_round_transition(room)

                if room.phase == Phase.BOARD_VIEW:
                    await self.render_board(room.chat_id, room)
                elif room.phase == Phase.WAITING_FOR_PUSH:
                    await self._ui._tg.send_message(room.chat_id, "❌ Неверно! Кто ещё?")

            except (SQLAlchemyError, aioredis.RedisError) as e:
                logger.error(f"Ошибка при вынесении вердикта: {e}")

    async def render_board(self, chat_id: int, room: Room) -> None:
        if not room.current_round_id: return
        board_data = await self._game_repo.get_board_for_round(room.current_round_id)
        await self._ui.render_board(chat_id, room, board_data)

    async def _activate_button(self, chat_id: int, message_id: int, delay: float) -> None:
        await asyncio.sleep(delay)
        room = await self._state_repo.get_room("room_1")
        if not room or room.phase != Phase.READING: return
        room.activate_buzzer()
        await self._state_repo.save_room(room)

        markup = {"inline_keyboard": [[{"text": "🟢 Ответить", "callback_data": "btn_room_1"}]]}
        await self._ui._tg.edit_message_text(chat_id, message_id, "Жмите кнопку!", reply_markup=markup)

    async def handle_place_stake(self, chat_id: int, player_id: str, username: str, text: str) -> None:
        try:
            stake_val = int(text.split(" ")[1])
            await self._place_stake.execute("room_1", player_id, stake_val)
            await self._ui._tg.send_message(
                chat_id,
                f"Игрок @{username} поставил {stake_val} очков!",
            )
        except ValueError:
            await self._ui._tg.send_message(chat_id, "Использование: /stack <сумма>")
        except (SQLAlchemyError, aioredis.RedisError) as e:
            await self._ui._tg.send_message(chat_id, f"Ошибка: {e}")

    async def handle_final_start_stakes(self, chat_id: int, room: Room) -> None:
        if room.phase == Phase.FINAL_ROUND:
            try:
                await self._start_final_stake.execute("room_1")
                kb = {
                    "inline_keyboard": [[
                        {"text": "🔒 Закрыть ставки", "callback_data": "final_close_stakes"}
                    ]]
                }
                await self._ui._tg.send_message(
                    chat_id,
                    "📝 Прием ставок начат. Игроки могут делать ставки через `/stack <сумма>`. "
                    "Ведущий: закройте прием, когда все ответят.",
                    reply_markup=kb,
                )
            except (SQLAlchemyError, aioredis.RedisError) as e:
                logger.error(f"Ошибка старта финальных ставок: {e}")

    async def handle_final_close_stakes(self, chat_id: int, room: Room) -> None:
        if room.phase == Phase.FINAL_STAKE:
            try:
                await self._close_final_stake.execute("room_1")
                await self._ui._tg.send_message(
                    chat_id,
                    "🔒 Ставки закрыты! Игроки: отправьте свой ответ в чат обычным сообщением.",
                )
            except (SQLAlchemyError, aioredis.RedisError) as e:
                logger.error(f"Ошибка закрытия финальных ставок: {e}")

    async def _handle_round_transition(self, room: Room) -> None:
        if not room.package_id: return
        rounds: list[dict] = await self._game_repo.get_rounds_by_package(room.package_id)
        idx = next((i for i, r in enumerate(rounds) if r["id"] == room.current_round_id), -1)

        if idx != -1 and idx + 1 < len(rounds):
            nxt = rounds[idx + 1]
            if nxt["is_final"]:
                board = await self._game_repo.get_board_for_round(nxt["id"])
                if board and board[0]["questions"]:
                    q_data = board[0]["questions"][0]
                    q = await self._game_repo.get_question_by_id(q_data["id"])
                    if q:
                        room.start_final_round(q)
                        await self._ui._tg.send_message(room.chat_id, "🏆 Время ФИНАЛА!")
                        await self._ui._tg.send_message(room.chat_id, f"Тема: *{q.theme_name}*")
                        kb = {"inline_keyboard": [[{"text": "🏁 Прием ставок", "callback_data": "final_start_stakes"}]]}
                        await self._ui._tg.send_message(room.chat_id, "Откройте прием ставок.", reply_markup=kb)
            else:
                room.current_round_id = nxt["id"]
                room.last_board_message_id = None
                await self._ui._tg.send_message(room.chat_id, f"🔔 Раунд завершен! Переходим к: {nxt['name']}")
        else:
            await self._ui._tg.send_message(room.chat_id, "🏁 Пакет пройден! Игра окончена.")
            room.phase = Phase.RESULTS
