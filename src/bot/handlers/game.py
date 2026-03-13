import asyncio
import random
import time

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
from src.bot.router import command, callback, message
from src.bot.callback import (
    FinalCloseStakesCallback,
    FinalRevealCallback,
    FinalStartStakesCallback,
    PressButtonCallback,
    SelectPackCallback,
    SelectQuestionCallback,
    SkipRoundCallback,
    StakeCallback,
    StartGameCallback,
    VerdictCallback,
)
from src.bot.ui import JeopardyUI
from src.domain.room import Phase, Room
from src.infrastructure.database.repositories.game_session import (
    GameSessionRepository,
)
from src.infrastructure.database.repositories.package import PackageRepository
from src.infrastructure.database.repositories.question import QuestionRepository
from src.infrastructure.database.repositories.round import RoundRepository
from src.infrastructure.database.repositories.theme import ThemeRepository
from src.infrastructure.redis_repo import RedisStateRepository
from src.shared.logger import get_logger

logger = get_logger(__name__)

class GameHandler:
    """Обработчик игрового процесса (старт, выбор вопроса, ответы, вердикты)."""

    def __init__(
        self,
        ui: JeopardyUI,
        package_repo: PackageRepository,
        question_repo: QuestionRepository,
        theme_repo: ThemeRepository,
        round_repo: RoundRepository,
        state_repo: RedisStateRepository,
        start_game_uc: StartGameUseCase,
        press_button_uc: PressButtonUseCase,
        submit_answer_uc: SubmitAnswerUseCase,
        select_question_uc: SelectQuestionUseCase,
        start_final_stake_uc: StartFinalStakeUseCase,
        place_stake_uc: PlaceStakeUseCase,
        close_final_stake_uc: CloseFinalStakeUseCase,
        session_repo: GameSessionRepository | None = None,
    ) -> None:
        self._ui = ui
        self._package_repo = package_repo
        self._question_repo = question_repo
        self._theme_repo = theme_repo
        self._round_repo = round_repo
        self._state_repo = state_repo
        self._start_game = start_game_uc
        self._press_button = press_button_uc
        self._submit_answer = submit_answer_uc
        self._select_question = select_question_uc
        self._start_final_stake = start_final_stake_uc
        self._place_stake = place_stake_uc
        self._close_final_stake = close_final_stake_uc
        self._session_repo = session_repo

        # Таймеры: room_id -> Task
        self._answer_timers: dict[str, asyncio.Task] = {}
        self._question_timers: dict[str, asyncio.Task] = {}
        # Оставшееся время на раздумья: room_id -> float
        self._remaining_thinking_time: dict[str, float] = {}

    @command("/start_game")
    async def handle_start_game(self, chat_id: int, room_id: str, player_id: str, user_tg_id: int) -> None:
        room = await self._state_repo.get_room(room_id)
        if room and room.host_id != player_id:
            await self._ui.send_message(chat_id, "⚠️ Только ведущий (HOST) может запустить игру.")
            return

        try:
            packs = await self._package_repo.get_all_packages()
            if not packs:
                await self._ui.send_message(chat_id, "⚠️ В базе данных нет доступных пакетов вопросов.")
                return

            await self._ui.render_pack_selection(chat_id, packs, room_id)
        except SQLAlchemyError as e:
            logger.error("Ошибка получения списка паков: %s", e)
            await self._ui.send_message(chat_id, "❌ Произошла ошибка при получении списка пакетов.")

    @callback(StartGameCallback)
    async def handle_start_game_callback(
        self, chat_id: int, room_id: str, player_id: str, user_tg_id: int, cb_id: str
    ) -> None:
        room = await self._state_repo.get_room(room_id)
        if room and room.host_id != player_id:
            await self._ui.answer_callback_query(
                cb_id, text="⚠️ Только ведущий может запустить игру.", show_alert=True
            )
            return
        try:
            packs = await self._package_repo.get_all_packages()
            if not packs:
                await self._ui.answer_callback_query(
                    cb_id, text="⚠️ Нет доступных пакетов вопросов.", show_alert=True
                )
                return
            await self._ui.render_pack_selection(chat_id, packs, room_id)
        except SQLAlchemyError as e:
            logger.error("Ошибка получения пакетов: %s", e)
            await self._ui.answer_callback_query(cb_id, text="❌ Ошибка загрузки пакетов.", show_alert=True)
            return
        await self._ui.answer_callback_query(cb_id)

    @callback(SelectPackCallback)
    async def handle_select_pack(self, chat_id: int, player_id: str, user_tg_id: int, data: SelectPackCallback, cb_id: str) -> None:
        room_id, pack_id = data.room_id, data.pack_id

        room = await self._state_repo.get_room(room_id)
        if room and room.host_id != player_id:
            await self._ui.send_message(chat_id, "⚠️ Только ведущий (HOST) может выбрать пакет.")
            await self._ui.answer_callback_query(cb_id)
            return

        start_dto = StartGameDTO(
            lobby_id=room_id,
            chat_id=chat_id,
            host_player_id=player_id,
            host_telegram_id=user_tg_id,
            pack_id=pack_id,
        )
        try:
            result = await self._start_game.execute(start_dto)
            await self._ui.send_message(chat_id, result.message)

            room = await self._state_repo.get_room(room_id)
            if room and room.phase == Phase.BOARD_VIEW:
                await self.render_board(chat_id, room)

        except (SQLAlchemyError, aioredis.RedisError) as e:
            logger.error("Ошибка старта игры: %s", e)
            await self._ui.send_message(chat_id, f"Ошибка старта игры: {e}")
        finally:
            await self._ui.answer_callback_query(cb_id)

    @callback(SelectQuestionCallback)
    async def handle_select_question(self, chat_id: int, player_id: str, data: SelectQuestionCallback, cb_id: str) -> None:
        room_id, q_id = data.room_id, data.question_id
        room = await self._state_repo.get_room(room_id)
        if not room:
            await self._ui.answer_callback_query(cb_id)
            return
        try:
            dto = SelectQuestionDTO(
                room_id=room_id,
                player_id=player_id,
                question_id=q_id,
            )
            res = await self._select_question.execute(dto)

            if res.phase == Phase.READING.value:
                # Вопрос и кнопка — одно сообщение
                red_btn = {
                    "inline_keyboard": [[{
                        "text": "🔴 Ждите...",
                        "callback_data": PressButtonCallback(chat_id=chat_id).pack(),
                    }]]
                }
                print(res)
                media_type = getattr(res, "media_type")
                media = getattr(res, "telegram_file_id")

                msg_id = await self._ui.show_question(
                    room.chat_id,
                    room_id,
                    res.question_text,
                    res.question_value,
                    reply_markup=red_btn,
                    media_type=media_type,
                    media_file_id=media,
                )
                if msg_id:
                    try:
                        room = await self._state_repo.get_room(room_id)
                        if room:
                            room.last_buzzer_message_id = msg_id
                            await self._state_repo.save_room(room)
                    except Exception as e:
                        logger.error("Error saving buzzer msg id: %s", e)

                    asyncio.create_task(
                        self._activate_button(room_id, room.chat_id, msg_id, random.uniform(2.0, 5.0))
                    )
            elif res.phase == Phase.SPECIAL_EVENT.value:
                await self._ui.send_message(
                    chat_id,
                    "Спец-ивент!\n(Заглушка для Кота в мешке / Аукциона)",
                )
            elif res.phase == Phase.FINAL_ROUND.value:
                kb = {
                    "inline_keyboard": [[{"text": "🏁 Прием ставок", "callback_data": FinalStartStakesCallback(room_id=room_id).pack()}]]
                }
                await self._ui.send_message(
                    chat_id,
                    "ФИНАЛЬНЫЙ РАУНД! Ведущий: откройте прием ставок.",
                    reply_markup=kb,
                )

        except (SQLAlchemyError, aioredis.RedisError) as e:
            logger.error("Ошибка при выборе вопроса: %s", e)
        except Exception as e:
            logger.exception("Критическая ошибка при отрисовке вопроса: %s", e)
        finally:
            await self._ui.answer_callback_query(cb_id)

    @callback(PressButtonCallback)
    async def handle_press_button(
        self,
        chat_id: int,
        room_id: str,
        player_id: str,
        username: str,
        message_id: int,
        cb_id: str,
        user_tg_id: int,
    ) -> None:
        result = await self._press_button.execute(room_id, player_id)

        if result.captured:
            # Остановка общего таймера вопроса
            if room_id in self._question_timers:
                self._question_timers[room_id].cancel()

            room_now = await self._state_repo.get_room(room_id)
            if room_now:
                room_now.answering_player_telegram_id = user_tg_id
                await self._state_repo.save_room(room_now)
                await self._ui.render_answering_view(room_id, player_id, username)

                q_text = room_now.current_question.text if room_now.current_question else "Вопрос"
                
                # Если нажато с Веба, берем ID сообщения из стейта комнаты
                msg_id_to_edit = message_id if message_id > 0 else (room_now.last_buzzer_message_id or 0)

                if msg_id_to_edit > 0:
                    # Узнаем, была ли картинка в текущем вопросе
                    media_type = room_now.current_question.media_type if room_now.current_question else None
                    new_text = f"🛑 Отвечает @{username}! Ждём ответа..."

                    if media_type:
                        # Если это картинка, меняем подпись (через клиент Telegram)
                        # Замени _tg на то, как у тебя называется доступ к клиенту в UI
                        await getattr(self._ui._tg, "edit_message_caption")(
                            chat_id=room_now.chat_id,
                            message_id=msg_id_to_edit,
                            caption=new_text,
                            reply_markup=None
                        )
                    else:
                        # Если обычный текст
                        await self._ui.edit_message_text(
                            chat_id=room_now.chat_id,
                            message_id=msg_id_to_edit,
                            text=new_text,
                            reply_markup=None
                        )

                if user_tg_id:
                    await self._ui.send_message(
                        chat_id=user_tg_id,
                        text=f"❓ Ты первый! Вопрос:\n\n*{q_text}*\n\nНапиши ответ прямо в это ЛС. У тебя 10 секунд!"
                    )
                    # Запоминаем активную комнату для игрока (для приема ответа в ЛС)
                    await self._state_repo.set_active_room(user_tg_id, room_id)
                
                await self._ui.answer_callback_query(cb_id, text="Твой ответ!")

                # Запуск таймера на ответ (10 сек)
                tmr = asyncio.create_task(self._answer_timeout_task(room_id, player_id, username))
                self._answer_timers[room_id] = tmr
        else:
            await self._ui.answer_callback_query(
                callback_query_id=cb_id,
                text=result.error or "Кто-то успел раньше!"
            )

    @message()
    async def handle_submit_answer(self, chat_id: int, room_id: str, player_id: str, username: str, text: str, room: Room, is_private: bool) -> None:
        if not text or text.startswith("/"): return
        if not room or room.phase not in (Phase.ANSWERING, Phase.FINAL_ANSWER): return

        dto = SubmitAnswerDTO(room_id=room_id, player_id=player_id, answer=text)
        try:
            # Отменяем таймер на ответ, так как ответ пришел
            if room_id in self._answer_timers:
                self._answer_timers[room_id].cancel()
                del self._answer_timers[room_id]

            await self._submit_answer.execute(dto)
            room = await self._state_repo.get_room(room_id)
            if not room: return

            if room.phase == Phase.ANSWERING:
                if not room.host_telegram_id:
                    await self._ui.send_message(room.chat_id, "⚠️ Ошибка: ID ведущего не найден.")
                    return

                keyboard = {
                    "inline_keyboard": [[
                        {"text": "✅ Верно", "callback_data": VerdictCallback(room_id=room_id, verdict="yes", target_player_id=player_id).pack()},
                        {"text": "❌ Неверно", "callback_data": VerdictCallback(room_id=room_id, verdict="no", target_player_id=player_id).pack()}
                    ]]
                }

                # Получаем правильный ответ, чтобы ведущему было с чем сравнивать
                correct_answer_text = "Неизвестно"
                if room.current_question:
                    q = await self._question_repo.get_question_by_id(room.current_question.question_id)
                    if q:
                        correct_answer_text = q.answer

                await self._ui.send_message(
                    chat_id=room.host_telegram_id,
                    text=(
                        f"Игрок @{username} дал ответ!\n\n"
                        f"🔸 **Его ответ:** {text}\n"
                        f"🔹 **Правильный ответ:** {correct_answer_text}\n\n"
                        f"Ваш вердикт?"
                    ),
                    reply_markup=keyboard,
                )

                if is_private:
                    await self._ui.send_message(chat_id, "✅ Твой ответ передан ведущему!")

            elif room.phase == Phase.FINAL_ANSWER:
                await self._ui.send_message(room.chat_id, f"Финальный ответ от @{username} принят.")

        except (SQLAlchemyError, aioredis.RedisError) as e:
            logger.error("Ошибка при сохранении ответа: %s", e)

    @callback(VerdictCallback)
    async def handle_verdict(self, chat_id: int, message_id: int, data: VerdictCallback, cb_id: str) -> None:
        room_id = data.room_id
        room = await self._state_repo.get_room(room_id)
        if not room: return

        if room.phase == Phase.ANSWERING:
            verdict, target_player_id = data.verdict, data.target_player_id
            is_correct = verdict == "yes"
            try:
                room.resolve_answer(target_player_id, is_correct)
                await self._state_repo.save_room(room)
                await self._state_repo.release_button(room_id)

                verdict_text = "✅ Верно" if is_correct else "❌ Неверно"
                if message_id > 0:
                    media_type = room.current_question.media_type if room.current_question else None
                    new_text = f"Вердикт: {verdict_text}"

                    if media_type:
                        await getattr(self._ui._tg, "edit_message_caption")(
                            chat_id=chat_id, message_id=message_id, caption=new_text
                        )
                    else:
                        await self._ui.edit_message_text(
                            chat_id=chat_id, message_id=message_id, text=new_text
                        )

                await self._ui.show_verdict(
                    room.chat_id, room_id, verdict_text,
                    buzzer_message_id=room.last_buzzer_message_id,
                )

                # Чекпоинт: сохраняем текущее состояние в Postgres
                if self._session_repo:
                    try:
                        await self._session_repo.update_session(room)
                    except Exception as e:
                        logger.error("Ошибка update_session: %s", e)

                # Проверка завершения раунда — без дублирования вызовов
                round_finished = False
                if room.current_round_id:
                    board_data = await self._theme_repo.get_board_for_round(room.current_round_id)
                    all_q_ids = [q["id"] for theme in board_data for q in theme["questions"]]
                    if room.is_round_finished(all_q_ids):
                        round_finished = True
                        await self._handle_round_transition(room)

                if not round_finished and room.phase == Phase.BOARD_VIEW:
                    # Сбрасываем buzzer_message_id — show_verdict уже
                    # запустил auto-delete, render_board не должен удалять его
                    room.last_buzzer_message_id = None
                    await self._state_repo.save_room(room)
                    await self.render_board(room.chat_id, room)
                elif room.phase == Phase.WAITING_FOR_PUSH:
                    # Восстанавливаем кнопку (редактируем то же сообщение)
                    if room.last_buzzer_message_id:
                        await self._ui.render_buzzer(room.chat_id, room_id, room.last_buzzer_message_id)

                    # Возобновляем общий таймер вопроса
                    tmr = asyncio.create_task(self._question_timeout_task(room_id, room.chat_id))
                    self._question_timers[room_id] = tmr

            except (SQLAlchemyError, aioredis.RedisError) as e:
                logger.error("Ошибка при вынесении вердикта: %s", e)

    @command("/sync")
    async def handle_sync(self, room_id: str) -> None:
        """Синхронизация состояния для переподключившегося веб-клиента."""
        room = await self._state_repo.get_room(room_id)
        if not room:
            return

        board_data = None
        if room.phase == Phase.BOARD_VIEW and room.current_round_id:
            board_data = await self._theme_repo.get_board_for_round(room.current_round_id)

        await self._ui.send_game_snapshot(room, board_data)
        logger.info("🔄 Снимок состояния отправлен для комнаты %s", room_id)

    async def render_board(self, chat_id: int, room: Room) -> None:
        if not room.current_round_id:
            return
        # Удаляем сообщение с вопросом/кнопкой перед показом табло
        if room.last_buzzer_message_id:
            await self._ui.delete_message(chat_id, room.last_buzzer_message_id)
            room.last_buzzer_message_id = None
            await self._state_repo.save_room(room)
        board_data = await self._theme_repo.get_board_for_round(room.current_round_id)
        new_msg_id = await self._ui.render_board(chat_id, room, board_data)
        if new_msg_id:
            room.last_board_message_id = new_msg_id
            await self._state_repo.save_room(room)

    async def _activate_button(self, room_id: str, chat_id: int, message_id: int, delay: float) -> None:
        await asyncio.sleep(delay)
        room = await self._state_repo.get_room(room_id)
        if not room or room.phase != Phase.READING: return
        room.activate_buzzer()
        await self._state_repo.save_room(room)

        await self._ui.render_buzzer(chat_id, room_id, message_id)

        # Запуск общего таймера вопроса (10 сек)
        self._remaining_thinking_time[room_id] = 10.0
        tmr = asyncio.create_task(self._question_timeout_task(room_id, chat_id))
        self._question_timers[room_id] = tmr

    async def _answer_timeout_task(self, room_id: str, player_id: str, username: str) -> None:
        """Таймер на ввод текста ответа (10 сек)."""
        try:
            await asyncio.sleep(10)
            room = await self._state_repo.get_room(room_id)
            if room and room.phase == Phase.ANSWERING and room.answering_player_id == player_id:
                await self._ui.send_temporary(room.chat_id, f"⏰ Время вышло! @{username} не успел ответить.")

                # СОЗДАЕМ ОБЪЕКТ, А НЕ СТРОКУ:
                verdict_data = VerdictCallback(
                    room_id=room_id,
                    verdict="no",
                    target_player_id=player_id
                )

                await self.handle_verdict(
                    chat_id=room.chat_id,
                    message_id=0,
                    data=verdict_data,
                    cb_id="",
                )
        except asyncio.CancelledError:
            pass

    async def _question_timeout_task(self, room_id: str, chat_id: int) -> None:
        """Общий таймер на обдумывание вопроса (10 сек, не сбрасывается)."""
        timeout = self._remaining_thinking_time.get(room_id, 10.0)

        try:
            start_time = time.time()
            await asyncio.sleep(timeout)
            # Если дождались - значит время вышло
            logger.info("⏰ Общее время на вопрос %s истекло.", room_id)
            self._remaining_thinking_time[room_id] = 0

            room = await self._state_repo.get_room(room_id)
            if room and room.phase == Phase.WAITING_FOR_PUSH:
                await self._ui.send_temporary(chat_id, "⏰ Время истекло! Никто не ответил.")
                # Вызываем переход (он внутри себя закроет вопрос и проверит раунд)
                await self._handle_round_transition(room)

                # Если мы остались в фазе табло, нужно его отрисовать
                if room.phase == Phase.BOARD_VIEW:
                    await self.render_board(chat_id, room)
        except asyncio.CancelledError:
            # Считаем сколько времени прошло и вычитаем
            elapsed = time.time() - start_time
            self._remaining_thinking_time[room_id] = max(0.0, timeout - elapsed)
            logger.debug(
                "Таймер вопроса приостановлен. Осталось: %.1fс",
                self._remaining_thinking_time[room_id],
            )

    async def restore_timers(self) -> None:
        """Восстановить in-memory таймеры при старте (для активных комнат в Redis)."""
        rooms = await self._state_repo.get_all_rooms()
        for room in rooms:
            if room.phase == Phase.WAITING_FOR_PUSH:
                self._remaining_thinking_time[room.room_id] = 10.0
                tmr = asyncio.create_task(
                    self._question_timeout_task(room.room_id, room.chat_id)
                )
                self._question_timers[room.room_id] = tmr
                logger.info("Восстановлен таймер вопроса для комнаты %s", room.room_id)
            elif room.phase == Phase.ANSWERING and room.answering_player_id:
                player = room.players.get(room.answering_player_id)
                username = player.username if player else "unknown"
                tmr = asyncio.create_task(
                    self._answer_timeout_task(room.room_id, room.answering_player_id, username)
                )
                self._answer_timers[room.room_id] = tmr
                logger.info("Восстановлен таймер ответа для комнаты %s", room.room_id)

    @callback(SkipRoundCallback)
    async def handle_skip_round(self, chat_id: int, room_id: str, player_id: str, data: SkipRoundCallback = None, cb_id: str = None) -> None:
        """Принудительный пропуск текущего раунда (только для хоста)."""
        if data:
            room_id = data.room_id

        room = await self._state_repo.get_room(room_id)
        if not room:
            if cb_id: await self._ui.answer_callback_query(cb_id)
            return

        if room.host_id != player_id:
            await self._ui.send_message(chat_id, "⚠️ Только ведущий (HOST) может пропустить раунд.")
            if cb_id: await self._ui.answer_callback_query(cb_id)
            return

        await self._ui.send_temporary(room.chat_id, "⏩ Ведущий пропустил раунд!")
        # Принудительно закрываем текущий вопрос если он есть
        if room.current_question and room.current_question.question_id is not None:
            room.closed_questions.append(room.current_question.question_id)
            room.current_question = None

        # Останавливаем таймеры
        if room_id in self._question_timers:
            self._question_timers[room_id].cancel()
        if room_id in self._answer_timers:
            self._answer_timers[room_id].cancel()

        # Закрываем все вопросы раунда, чтобы сработал переход
        if room.current_round_id:
            board_data = await self._theme_repo.get_board_for_round(room.current_round_id)
            for theme in board_data:
                for q in theme["questions"]:
                    if q["id"] not in room.closed_questions:
                        room.closed_questions.append(q["id"])

            # Сохраняем перед проверкой перехода, чтобы is_round_finished вернул True
            await self._state_repo.save_room(room)
            await self._handle_round_transition(room)

        if cb_id:
            await self._ui.answer_callback_query(cb_id)

    @command("/stack")
    async def handle_place_stake(self, chat_id: int, room_id: str, player_id: str, username: str, text: str) -> None:
        try:
            stake_val = int(text.split(" ")[1])
            await self._place_stake.execute(room_id, player_id, stake_val)
            await self._ui.send_message(
                chat_id,
                f"Игрок @{username} поставил {stake_val} очков!",
            )
        except ValueError:
            await self._ui.send_message(chat_id, "Использование: /stack <сумма>")
        except (SQLAlchemyError, aioredis.RedisError) as e:
            await self._ui.send_message(chat_id, f"Ошибка: {e}")

    @callback(FinalStartStakesCallback)
    async def handle_final_start_stakes(self, chat_id: int, data: FinalStartStakesCallback, cb_id: str) -> None:
        room_id = data.room_id
        room = await self._state_repo.get_room(room_id)
        if not room: return
        if room.phase == Phase.FINAL_ROUND:
            try:
                await self._start_final_stake.execute(room_id)
                kb = {
                    "inline_keyboard": [[
                        {"text": "🔒 Закрыть ставки", "callback_data": FinalCloseStakesCallback(room_id=room_id).pack()}
                    ]]
                }
                await self._ui.send_message(
                    chat_id,
                    "📝 Прием ставок начат! Каждый игрок получит кнопки ставок в личные сообщения.\n"
                    "Ведущий: закройте прием, когда все поставят.",
                    reply_markup=kb,
                )
                # Рассылаем кнопки ставок каждому игроку в ЛС
                for player in room.players.values():
                    if player.telegram_id:
                        await self._ui.send_stake_options(
                            player.telegram_id, room_id, player.score
                        )
            except (SQLAlchemyError, aioredis.RedisError) as e:
                logger.error("Ошибка старта финальных ставок: %s", e)
        await self._ui.answer_callback_query(cb_id)

    @callback(StakeCallback)
    async def handle_stake_callback(
        self, chat_id: int, player_id: str, username: str, message_id: int, data: StakeCallback, cb_id: str
    ) -> None:
        room_id, amount = data.room_id, data.amount
        try:
            await self._place_stake.execute(room_id, player_id, amount)
            if message_id > 0:
                await self._ui.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"✅ Ставка принята: **{amount}** очков",
                )
            await self._ui.answer_callback_query(cb_id, text=f"Ставка {amount} принята!")
        except (SQLAlchemyError, aioredis.RedisError) as e:
            await self._ui.answer_callback_query(cb_id, text=f"Ошибка: {e}", show_alert=True)

    @callback(FinalCloseStakesCallback)
    async def handle_final_close_stakes(self, chat_id: int, data: FinalCloseStakesCallback, cb_id: str) -> None:
        room_id = data.room_id
        room = await self._state_repo.get_room(room_id)
        if not room: return
        if room.phase == Phase.FINAL_STAKE:
            try:
                await self._close_final_stake.execute(room_id)
                kb = {
                    "inline_keyboard": [[
                        {"text": "📊 Огласить результаты", "callback_data": FinalRevealCallback(room_id=room_id).pack()}
                    ]]
                }
                await self._ui.send_message(
                    chat_id,
                    "🔒 Ставки закрыты! Игроки: отправьте свой ответ в чат обычным сообщением.",
                )
                await self._ui.send_message(
                    room.host_telegram_id,
                    "Игроки пишут ответы. Когда будете готовы — нажимайте кнопку:",
                    reply_markup=kb,
                )
            except (SQLAlchemyError, aioredis.RedisError) as e:
                logger.error("Ошибка закрытия финальных ставок: %s", e)
        await self._ui.answer_callback_query(cb_id)

    async def _handle_round_transition(self, room: Room) -> None:
        """Внутренняя логика закрытия вопроса и проверки перехода раунда."""
        # 1. Закрываем текущий вопрос если он есть
        if room.current_question and room.current_question.question_id is not None:
            room.closed_questions.append(room.current_question.question_id)
            room.current_question = None

        room.phase = Phase.BOARD_VIEW
        await self._state_repo.save_room(room)
        await self._state_repo.release_button(room.room_id)

        # 2. Проверяем, закончился ли текущий раунд
        if not room.current_round_id: return
        board_data = await self._theme_repo.get_board_for_round(room.current_round_id)
        all_q_ids = [q["id"] for theme in board_data for q in theme["questions"]]

        if not room.is_round_finished(all_q_ids):
            # Раунд еще не закончен
            return

        # 3. Переход к следующему раунду
        if not room.package_id: return
        rounds: list[dict] = await self._round_repo.get_rounds_by_package(room.package_id)
        idx = next((i for i, r in enumerate(rounds) if r["id"] == room.current_round_id), -1)

        if idx != -1 and idx + 1 < len(rounds):
            nxt = rounds[idx + 1]
            if nxt["is_final"]:
                board = await self._theme_repo.get_board_for_round(nxt["id"])
                if board and board[0]["questions"]:
                    q_data = board[0]["questions"][0]
                    q = await self._question_repo.get_question_by_id(q_data["id"])
                    if q:
                        room.start_final_round(q)
                        room.current_round_name = nxt["name"]
                        room.round_number += 1
                        await self._state_repo.save_room(room)
                        await self._ui.send_message(room.chat_id, "🏆 Время ФИНАЛА!")
                        await self._ui.send_message(room.chat_id, f"Тема: *{q.theme_name}*")
                        kb = {"inline_keyboard": [[{"text": "🏁 Прием ставок", "callback_data": FinalStartStakesCallback(room_id=f"room_{room.chat_id}").pack()}]]}
                        await self._ui.send_message(room.chat_id, "Откройте прием ставок.", reply_markup=kb)
            else:
                room.current_round_id = nxt["id"]
                room.current_round_name = nxt["name"]
                room.round_number += 1
                room.last_board_message_id = None
                room.phase = Phase.BOARD_VIEW
                await self._state_repo.save_room(room)
                await self._ui.send_temporary(room.chat_id, f"🔔 Переходим к раунду: {nxt['name']}")
                await self.render_board(room.chat_id, room)
        else:
            # Больше раундов нет — сохраняем результаты и удаляем комнату
            room.phase = Phase.RESULTS
            res_text = await self._ui.render_results(room.chat_id, room)
            await self._state_repo.save_last_results(room.chat_id, res_text)
            # Финализация в Postgres до удаления из Redis
            if self._session_repo:
                try:
                    await self._session_repo.mark_finished(room)
                except Exception as e:
                    logger.error("Ошибка mark_finished: %s", e)
            await self._state_repo.delete_room(room.room_id)

    @callback(FinalRevealCallback)
    async def handle_final_reveal(self, chat_id: int, data: FinalRevealCallback, cb_id: str) -> None:
        """Хост оглашает результаты финала."""
        room_id = data.room_id
        room = await self._state_repo.get_room(room_id)
        if not room: return
        if room.phase == Phase.FINAL_ANSWER:
            # Считаем итоги в домене
            results = room.resolve_final()
            text = "🏁 **РЕЗУЛЬТАТЫ ФИНАЛА** 🏁\n\n"
            q_text = room.final_question.text if room.final_question else "???"
            a_text = room.final_question.answer if room.final_question else "???"
            text += f"Вопрос: {q_text}\nОтвет: *{a_text}*\n\n"

            for pid, correct in results.items():
                p = room.players.get(pid)
                if p:
                    v = "✅" if correct else "❌"
                    ans = room.final_answers.get(pid, "---")
                    stake = room.final_stakes.get(pid, 0)
                    text += f"{v} @{p.username}: {ans} (Ставка: {stake})\n"

            await self._ui.send_message(room.chat_id, text)
            res_text = await self._ui.render_results(room.chat_id, room)
            await self._state_repo.save_last_results(room.chat_id, res_text)
            # Финализация в Postgres до удаления из Redis
            if self._session_repo:
                try:
                    await self._session_repo.mark_finished(room)
                except Exception as e:
                    logger.error("Ошибка mark_finished (final): %s", e)
            await self._state_repo.delete_room(room_id)

        await self._ui.answer_callback_query(cb_id)
