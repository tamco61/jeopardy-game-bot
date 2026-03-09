import asyncio
import os

from src.application.game_process import PauseGameUseCase, UnpauseGameUseCase
from src.application.lobby_management import (
    BaseLobbyDTO,
    CreateLobbyUseCase,
    JoinLobbyUseCase,
    LeaveLobbyUseCase,
    ReadyUseCase,
)
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
from src.domain.player import Player
from src.domain.room import Phase, Room
from src.infrastructure.rabbit import RabbitMQPublisher
from src.infrastructure.redis_repo import RedisStateRepository
from src.infrastructure.telegram import TelegramHttpClient
from src.infrastructure.database.postgres_repo import PostgresGameRepository


class TelegramRouter:
    """Диспетчер входящих Telegram-обновлений."""

    def __init__(
        self,
        telegram_client: TelegramHttpClient,
        game_repo: PostgresGameRepository,
        start_game_uc: StartGameUseCase,
        press_button_uc: PressButtonUseCase,
        submit_answer_uc: SubmitAnswerUseCase,
        create_lobby_uc: CreateLobbyUseCase,
        join_lobby_uc: JoinLobbyUseCase,
        ready_uc: ReadyUseCase,
        leave_lobby_uc: LeaveLobbyUseCase,
        pause_game_uc: PauseGameUseCase,
        unpause_game_uc: UnpauseGameUseCase,
        select_question_uc: SelectQuestionUseCase,
        place_stake_uc: PlaceStakeUseCase,
        start_final_stake_uc: StartFinalStakeUseCase,
        close_final_stake_uc: CloseFinalStakeUseCase,
        state_repo: RedisStateRepository,
        rabbit_publisher: RabbitMQPublisher,
    ) -> None:
        self._tg = telegram_client
        self._game_repo = game_repo
        self._start_game = start_game_uc
        self._press_button = press_button_uc
        self._submit_answer = submit_answer_uc
        self._create_lobby = create_lobby_uc
        self._join_lobby = join_lobby_uc
        self._ready = ready_uc
        self._leave_lobby = leave_lobby_uc
        self._pause = pause_game_uc
        self._unpause = unpause_game_uc
        self._select_question = select_question_uc
        self._place_stake = place_stake_uc
        self._start_final_stake = start_final_stake_uc
        self._close_final_stake = close_final_stake_uc
        self._state_repo = state_repo
        self._rabbit = rabbit_publisher

    async def handle_update(self, update: dict) -> None:
        print(f"📩 Получен update: {update.get('update_id')}")

        message: dict | None = update.get("message")
        if message is not None:
            if "document" in message:
                await self._handle_document(message)
                return

            text: str = (message.get("text") or "").strip()
            chat_id: int = message["chat"]["id"]
            is_private = message["chat"].get("type", "") == "private"

            user = message.get("from", {})
            player_id = str(user.get("id", ""))
            # telegram_id — Ы пользователя (не chat!). По этому ID бот может слать ЛС.
            user_telegram_id = int(user.get("id", 0))
            username = user.get("username") or user.get("first_name", "unknown")

            # Базовое DTO для команд лобби
            lobby_dto = BaseLobbyDTO(
                room_id="room_1",
                player_id=player_id,
                telegram_id=user_telegram_id,   # ЛИЧНЫЙ ID для ЛС
                group_chat_id=chat_id,           # ГРУППОВОЙ чат (где будет игра)
                username=username,
                first_name=user.get("first_name", ""),
            )

            if text == "/upload_pack":
                await self._tg.send_message(
                    chat_id,
                    "📂 Чтобы загрузить свой пакет вопросов, отправьте файл `.siq` и в поле подписи (caption) напишите `/upload_pack`.",
                )
                return

            if text == "/create_lobby":
                try:
                    await self._create_lobby.execute(lobby_dto)
                    await self._tg.send_message(
                        chat_id,
                        "Лобби создано! Вы ведущий (HOST). Игроки могут писать /join.",
                    )
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/join":
                try:
                    await self._join_lobby.execute(lobby_dto)
                    await self._tg.send_message(
                        chat_id, f"Игрок @{username} присоединился к лобби!"
                    )
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/ready":
                try:
                    await self._ready.execute(
                        "room_1", player_id, is_ready=True
                    )
                    await self._tg.send_message(
                        chat_id, f"Игрок @{username} готов!"
                    )
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/notready":
                try:
                    await self._ready.execute(
                        "room_1", player_id, is_ready=False
                    )
                    await self._tg.send_message(
                        chat_id, f"Игрок @{username} не готов."
                    )
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/leave":
                try:
                    await self._leave_lobby.execute("room_1", player_id)
                    await self._tg.send_message(
                        chat_id, f"Игрок @{username} покинул лобби."
                    )
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/start_game":
                # Проверяем что команду даёт ведущий
                room_check = await self._state_repo.get_room("room_1")
                if room_check and room_check.host_id and room_check.host_id != player_id:
                    await self._tg.send_message(
                        chat_id, "⛔ Только ведущий может начать игру."
                    )
                    return

                # Временно хардкодим pack_id=1
                start_dto = StartGameDTO(
                    lobby_id="room_1",
                    chat_id=chat_id,  # Групповой чат сохраняется в этом месте
                    host_player_id=player_id,
                    host_telegram_id=user_telegram_id, # ЛИЧНЫЙ ID ведущего
                    pack_id=1,
                )
                try:
                    result = await self._start_game.execute(start_dto)
                    # Отвечаем в тот чат, откуда пришла команда
                    await self._tg.send_message(chat_id, result.message)

                    # Табло рендерим в ГРУППУ (room.chat_id)
                    room = await self._state_repo.get_room("room_1")
                    if room and room.phase == Phase.BOARD_VIEW:
                        print(f"DEBUG: Game started. Host ID: {room.host_id}, Host TG ID: {room.host_telegram_id}")
                        await self._render_board(room.chat_id, room)

                except Exception as e:
                    await self._tg.send_message(
                        chat_id, f"Ошибка старта игры: {e}"
                    )
                return

            if text == "/pause":
                try:
                    await self._pause.execute("room_1", player_id)
                    await self._tg.send_message(
                        chat_id, "⏸ Игра поставлена на паузу."
                    )
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/unpause":
                try:
                    phase_name = await self._unpause.execute(
                        "room_1", player_id
                    )
                    await self._tg.send_message(
                        chat_id,
                        f"▶️ Игра снята с паузы. Возврат в: {phase_name}",
                    )
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text.startswith("/stack "):
                try:
                    stake_val = int(text.split(" ")[1])
                    await self._place_stake.execute(
                        "room_1", player_id, stake_val
                    )
                    await self._tg.send_message(
                        chat_id,
                        f"Игрок @{username} поставил {stake_val} очков!",
                    )
                except ValueError:
                    await self._tg.send_message(
                        chat_id, "Использование: /stack <сумма>"
                    )
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text and not text.startswith("/"):
                room = await self._state_repo.get_room("room_1")
                if room and room.phase in (Phase.ANSWERING, Phase.FINAL_ANSWER):
                    # Проверяем: если ANSWERING — только отвечающий игрок может ответить
                    if (
                        room.phase == Phase.ANSWERING
                        and room.answering_player_id != player_id
                    ):
                        if is_private:
                            # Игрок пишет в ЛС, но не его очередь
                            await self._tg.send_message(chat_id, "Сейчас отвечает другой игрок.")
                        return

                    dto = SubmitAnswerDTO(
                        room_id="room_1",
                        player_id=player_id,
                        answer=text,
                    )
                    try:
                        await self._submit_answer.execute(dto)

                        # Перезагружаем комнату, чтобы быть уверенными в host_telegram_id
                        room = await self._state_repo.get_room("room_1")
                        if not room:
                            return

                        if room.phase == Phase.ANSWERING:
                            print(f"DEBUG: Player {username} answered. Host TG ID: {room.host_telegram_id}")
                            if not room.host_telegram_id:
                                await self._tg.send_message(
                                    chat_id=room.chat_id,
                                    text="⚠️ Ошибка: ID ведущего не найден. Ведущий, напишите /create_lobby ещё раз."
                                )
                                return

                            # Отправляем ведущему в ЛС кнопки вердикта
                            keyboard = {
                                "inline_keyboard": [
                                    [
                                        {
                                            "text": "✅ Верно",
                                            "callback_data": f"verdict:yes:{player_id}",
                                        },
                                        {
                                            "text": "❌ Неверно",
                                            "callback_data": f"verdict:no:{player_id}",
                                        },
                                    ]
                                ]
                            }
                            # Сообщаем ведущему в ЛС
                            try:
                                await self._tg.send_message(
                                    chat_id=room.host_telegram_id,
                                    text=f"Игрок @{username} ответил: *{text}*\nВаш вердикт:",
                                    reply_markup=keyboard,
                                )
                            except Exception as e:
                                print(f"ERROR: Could not send DM to host: {e}")
                                await self._tg.send_message(
                                    chat_id=room.chat_id,
                                    text=f"⚠️ Не удалось отправить вердикт ведущему в ЛС. Ведущий, вы начали диалог с ботом? Ошибка: {e}"
                                )

                            # Также сообщаем в группу, что игрок ответил
                            await self._tg.send_message(
                                chat_id=room.chat_id,
                                text=f"Игрок @{username} дал ответ. Ждём вердикт ведущего...",
                            )
                            # Подтверждаем игроку что ответ принят
                            if is_private:
                                await self._tg.send_message(chat_id, "✅ Твой ответ передан ведущему!")

                        elif room.phase == Phase.FINAL_ANSWER:
                            await self._tg.send_message(
                                chat_id=room.chat_id,
                                text=f"Финальный ответ от @{username} принят.",
                            )
                    except Exception as e:
                        print(f"Ошибка при сохранении ответа: {e}")
            return

        callback_query: dict | None = update.get("callback_query")
        if callback_query is not None:
            user: dict = callback_query["from"]
            player_id = str(user["id"])
            username: str = user.get("username") or user.get(
                "first_name", "unknown"
            )

            callback_message: dict = callback_query["message"]
            chat_id = callback_message["chat"]["id"]
            message_id: int = callback_message["message_id"]
            data: str = callback_query.get("data", "")

            # Хак для MVP: автоматически добавляем юзера в комнату, если он кликнул
            room = await self._state_repo.get_room("room_1")

            if data.startswith("verdict:"):
                parts = data.split(":")
                if len(parts) == 3 and room and room.phase == Phase.ANSWERING:
                    verdict, target_player_id = parts[1], parts[2]
                    is_correct = verdict == "yes"
                    try:
                        room.resolve_answer(target_player_id, is_correct)
                        await self._state_repo.save_room(room)

                        # ФИКС: всегда освобождаем кнопку после вердикта
                        await self._state_repo.release_button("room_1")

                        verdict_text = "✅ Верно" if is_correct else "❌ Неверно"
                        # Редактируем сообщение в ЛС ведущего
                        await self._tg.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=f"Ведущий вынес вердикт: {verdict_text}",
                        )

                        # Объявляем результат в ГРУППУ
                        await self._tg.send_message(
                            chat_id=room.chat_id,
                            text=f"Ведущий вынес вердикт: {verdict_text}",
                        )

                        # Если вернулись на табло — отправляем табло в ГРУППУ
                        if room.phase == Phase.BOARD_VIEW:
                            await self._render_board(room.chat_id, room)
                        # Если неверно — ещё кто-то может ответить
                        elif room.phase == Phase.WAITING_FOR_PUSH:
                            await self._tg.send_message(
                                room.chat_id,
                                "❌ Неверно! Кто ещё хочет ответить?",
                            )

                    except Exception as e:
                        print(f"Ошибка при вынесении вердикта: {e}")

                await self._tg.answer_callback_query(callback_query["id"])
                return

            if data.startswith("select_question:"):
                parts = data.split(":")
                if len(parts) == 2 and room and room.phase == Phase.BOARD_VIEW:
                    try:
                        q_id = int(parts[1])
                        dto = SelectQuestionDTO(
                            room_id="room_1",
                            player_id=player_id,
                            question_id=q_id,
                        )
                        res = await self._select_question.execute(dto)

                        # Вопрос объявляем в группе
                        await self._tg.send_message(
                            room.chat_id,
                            f"Выбран вопрос за {res.question_value}\n\n{res.question_text}",
                        )

                        if res.phase == Phase.READING.value:
                            kb = {
                                "inline_keyboard": [
                                    [
                                        {
                                            "text": "🔴 Ждите...",
                                            "callback_data": "btn_room_1",
                                        }
                                    ]
                                ]
                            }
                            # Кнопку отправляем в ГРУППУ, а не в чат откуда пришел каллбэк
                            sent_msg = await self._tg.send_message(
                                room.chat_id,
                                "Ожидайте активации кнопки...",
                                reply_markup=kb,
                            )
                            if "result" in sent_msg:
                                msg_id = sent_msg["result"]["message_id"]
                                import random

                                asyncio.create_task(
                                    self._activate_button(
                                        room.chat_id,
                                        msg_id,
                                        random.uniform(2.0, 5.0),
                                    )
                                )
                        elif res.phase == Phase.SPECIAL_EVENT.value:
                            await self._tg.send_message(
                                chat_id,
                                "Спец-ивент!\n(Заглушка для Кота в мешке / Аукциона)",
                            )
                        elif res.phase == Phase.FINAL_ROUND.value:
                            kb = {
                                "inline_keyboard": [
                                    [
                                        {
                                            "text": "🏁 Прием ставок",
                                            "callback_data": "final_start_stakes",
                                        }
                                    ]
                                ]
                            }
                            await self._tg.send_message(
                                chat_id,
                                "ФИНАЛЬНЫЙ РАУНД! Ведущий: откройте прием ставок.",
                                reply_markup=kb,
                            )

                    except Exception as e:
                        print(f"Ошибка при выборе вопроса: {e}")

                await self._tg.answer_callback_query(callback_query["id"])
                return

            if data == "final_start_stakes":
                if room and room.phase == Phase.FINAL_ROUND:
                    try:
                        await self._start_final_stake.execute("room_1")
                        kb = {
                            "inline_keyboard": [
                                [
                                    {
                                        "text": "🔒 Закрыть ставки",
                                        "callback_data": "final_close_stakes",
                                    }
                                ]
                            ]
                        }
                        await self._tg.send_message(
                            chat_id,
                            "📝 Прием ставок начат. Игроки могут делать ставки через `/stack <сумма>`. Ведущий: закройте прием, когда все ответят.",
                            reply_markup=kb,
                        )
                    except Exception as e:
                        print(f"Ошибка старта финальных ставок: {e}")
                await self._tg.answer_callback_query(callback_query["id"])
                return

            if data == "final_close_stakes":
                if room and room.phase == Phase.FINAL_STAKE:
                    try:
                        await self._close_final_stake.execute("room_1")
                        await self._tg.send_message(
                            chat_id,
                            "🔒 Ставки закрыты! Игроки: отправьте свой ответ в чат обычным сообщением.",
                        )
                    except Exception as e:
                        print(f"Ошибка закрытия финальных ставок: {e}")
                await self._tg.answer_callback_query(callback_query["id"])
                return

            if room and player_id not in room.players:
                room.players[player_id] = Player(
                    player_id=player_id,
                    telegram_id=user["id"],
                    username=username,
                    score=0,
                )
                await self._state_repo.save_room(room)

            # ── Логика гонки через Use Case ─────────────────────────────
            result = await self._press_button.execute("room_1", player_id)

            if result.captured:
                print(f"🏆 ПЕРВЫЙ нажал: @{username}")
                room_now = await self._state_repo.get_room("room_1")
                if room_now:
                    # Сохраняем telegram_id отвечающего для последующей отправки ЛС
                    room_now.answering_player_telegram_id = user["id"]
                    await self._state_repo.save_room(room_now)

                    q_text = (
                        room_now.current_question.text
                        if room_now.current_question
                        else "Вопрос"
                    )

                    # Обновляем кнопку в ГРУППЕ — сообщаем кто отвечает
                    await self._tg.edit_message_text(
                        chat_id=room_now.chat_id,
                        message_id=message_id,
                        text=f"🛑 Отвечает @{username}! Ждём ответа в личку...",
                    )

                    # Отправляем игроку ЛС с вопросом и просьбой ответить
                    await self._tg.send_message(
                        chat_id=user["id"],
                        text=(
                            f"❓ Ты первый! Вопрос:\n\n*{q_text}*\n\n"
                            f"Напиши ответ прямо в это личное сообщение."
                        ),
                    )

                await self._tg.answer_callback_query(
                    callback_query["id"], text="Твой ответ!"
                )
            else:
                print(f"⏳ Неудача: @{username} — причина: {result.error}")
                await self._tg.answer_callback_query(
                    callback_query_id=callback_query["id"],
                    text=result.error or "Кто-то успел раньше!",
                )


    async def _activate_button(
        self, chat_id: int, message_id: int, delay: float
    ) -> None:
        """Ждёт случайное время (2-5 сек), переводит комнату в состояние WAITING_FOR_PUSH."""
        await asyncio.sleep(delay)

        room = await self._state_repo.get_room("room_1")
        if not room or room.phase != Phase.READING:
            return

        try:
            room.activate_buzzer()
            await self._state_repo.save_room(room)
        except Exception:
            return

        green_markup = {
            "inline_keyboard": [
                [{"text": "🟢 Ответить", "callback_data": "btn_room_1"}]
            ]
        }

        await self._tg.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Жмите кнопку!",
            reply_markup=green_markup,
        )

    async def _handle_document(self, message: dict) -> None:
        chat_id = message["chat"]["id"]
        document = message["document"]
        caption = message.get("caption", "").strip()

        if not caption.startswith("/upload_pack"):
            return

        file_name = document.get("file_name", "")

        if not file_name.endswith(".siq"):
            return

        file_id = document["file_id"]

        try:
            # Получаем информацию о файле
            file_info = await self._tg.get_file(file_id)
            if not file_info.get("ok"):
                await self._tg.send_message(
                    chat_id, "Ошибка получения файла от Telegram."
                )
                return

            file_path = file_info["result"]["file_path"]

            # Скачиваем файл во временную директорию
            os.makedirs("data/uploads", exist_ok=True)
            local_path = os.path.abspath(f"data/uploads/{file_id}.siq")

            await self._tg.send_message(
                chat_id, f"Скачиваю сик-пак '{file_name}'..."
            )
            await self._tg.download_file(file_path, local_path)

            # Публикуем задачу на парсинг в RabbitMQ
            # Мы используем routing_key для передачи в соответствующую очередь
            await self._rabbit.publish(
                "siq_parse_tasks", {"file_path": local_path}
            )

            await self._tg.send_message(
                chat_id,
                f"Пакет '{file_name}' успешно загружен и отправлен в очередь на обработку!",
            )
        except Exception as e:
            await self._tg.send_message(
                chat_id, f"Ошибка при скачивании/обработке пакета: {e}"
            )
            print(f"Ошибка загрузки SIQ: {e}")


    async def _render_board(self, chat_id: int, room: Room) -> None:
        """Отрисовывает актуальное табло команде через Inline Keyboard.
        
        Каждая строка — это тема, первая кнопка — название темы (не кликабельна),
        остальные кнопки — доступные стоимости вопросов. Сыгранные заменяются на ❌.
        """
        if not room.current_round_id:
            await self._tg.send_message(chat_id, "❌ Раунд не назначен. Свяжитесь с ведущим.")
            return

        board_data = await self._game_repo.get_board_for_round(room.current_round_id)

        if not board_data:
            await self._tg.send_message(chat_id, "⚠️ Табло пустое. Возможно, пакет не содержит вопросов.")
            return

        keyboard = []
        for theme in board_data:
            row = []
            # Укорачиваем название темы если оно слишком длинное
            name = theme["theme"]
            theme_name = (name[:15] + "..") if len(name) > 17 else name
            row.append({"text": theme_name, "callback_data": "ignore"})

            for q in theme["questions"]:
                if q["id"] in room.closed_questions:
                    row.append({"text": "❌", "callback_data": "ignore"})
                else:
                    row.append({"text": str(q["value"]), "callback_data": f"select_question:{q['id']}"})
            keyboard.append(row)

        await self._tg.send_message(
            chat_id,
            "🎮 **Выберите вопрос:**",
            reply_markup={"inline_keyboard": keyboard},
        )


class WebSocketRouter:
    """Обработчик WebSocket-соединений."""

    async def handle_connection(self, ws: object) -> None:
        raise NotImplementedError
