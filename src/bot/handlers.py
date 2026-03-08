import asyncio

import os

from src.application.lobby_management import (
    BaseLobbyDTO,
    CreateLobbyUseCase,
    JoinLobbyUseCase,
    ReadyUseCase,
    LeaveLobbyUseCase,
)
from src.application.game_process import PauseGameUseCase, UnpauseGameUseCase
from src.application.press_button import PressButtonUseCase
from src.application.select_question import SelectQuestionUseCase, SelectQuestionDTO
from src.application.special_events import (
    PlaceStakeUseCase,
    StartFinalStakeUseCase,
    CloseFinalStakeUseCase,
)
from src.application.start_game import StartGameUseCase, StartGameDTO
from src.application.submit_answer import SubmitAnswerUseCase, SubmitAnswerDTO
from src.domain.player import Player
from src.domain.room import Phase
from src.infrastructure.redis_repo import RedisStateRepository
from src.infrastructure.telegram import TelegramHttpClient
from src.infrastructure.rabbit import RabbitMQPublisher


class TelegramRouter:
    """Диспетчер входящих Telegram-обновлений."""

    def __init__(
        self,
        telegram_client: TelegramHttpClient,
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

            user = message.get("from", {})
            player_id = str(user.get("id", ""))
            username = user.get("username") or user.get("first_name", "unknown")

            # Базовое DTO для команд лобби
            lobby_dto = BaseLobbyDTO(
                room_id="room_1",
                player_id=player_id,
                telegram_id=chat_id,
                username=username,
                first_name=user.get("first_name", "")
            )

            if text == "/upload_pack":
                await self._tg.send_message(
                    chat_id, 
                    "📂 Чтобы загрузить свой пакет вопросов, отправьте файл `.siq` и в поле подписи (caption) напишите `/upload_pack`."
                )
                return

            if text == "/create_lobby":
                try:
                    await self._create_lobby.execute(lobby_dto)
                    await self._tg.send_message(chat_id, "Лобби создано! Вы ведущий (HOST). Игроки могут писать /join.")
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/join":
                try:
                    await self._join_lobby.execute(lobby_dto)
                    await self._tg.send_message(chat_id, f"Игрок @{username} присоединился к лобби!")
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/ready":
                try:
                    await self._ready.execute("room_1", player_id, is_ready=True)
                    await self._tg.send_message(chat_id, f"Игрок @{username} готов!")
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/notready":
                try:
                    await self._ready.execute("room_1", player_id, is_ready=False)
                    await self._tg.send_message(chat_id, f"Игрок @{username} не готов.")
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/leave":
                try:
                    await self._leave_lobby.execute("room_1", player_id)
                    await self._tg.send_message(chat_id, f"Игрок @{username} покинул лобби.")
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/start_game":
                # Временно хардкодим pack_id=1, потом это будет выбираться
                start_dto = StartGameDTO(
                    lobby_id="room_1",
                    chat_id=chat_id,
                    host_player_id=player_id,
                    pack_id=1
                )
                try:
                    result = await self._start_game.execute(start_dto)
                    await self._tg.send_message(chat_id, result.message)
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка старта игры: {e}")
                return

            if text == "/pause":
                try:
                    await self._pause.execute("room_1", player_id)
                    await self._tg.send_message(chat_id, "⏸ Игра поставлена на паузу.")
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text == "/unpause":
                try:
                    phase_name = await self._unpause.execute("room_1", player_id)
                    await self._tg.send_message(chat_id, f"▶️ Игра снята с паузы. Возврат в: {phase_name}")
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text.startswith("/stack "):
                try:
                    stake_val = int(text.split(" ")[1])
                    await self._place_stake.execute("room_1", player_id, stake_val)
                    await self._tg.send_message(chat_id, f"Игрок @{username} поставил {stake_val} очков!")
                except ValueError:
                    await self._tg.send_message(chat_id, "Использование: /stack <сумма>")
                except Exception as e:
                    await self._tg.send_message(chat_id, f"Ошибка: {e}")
                return

            if text and not text.startswith("/"):

                room = await self._state_repo.get_room("room_1")
                if room and room.phase in (Phase.ANSWERING, Phase.FINAL_ANSWER):
                    if room.phase == Phase.ANSWERING and room.answering_player_id != player_id:
                        return

                    dto = SubmitAnswerDTO(
                        room_id="room_1",
                        player_id=player_id,
                        answer=text,
                    )
                    try:
                        await self._submit_answer.execute(dto)

                        if room.phase == Phase.ANSWERING:
                            keyboard = {
                                "inline_keyboard": [
                                    [
                                        {"text": "✅ Верно", "callback_data": f"verdict:yes:{player_id}"},
                                        {"text": "❌ Неверно", "callback_data": f"verdict:no:{player_id}"}
                                    ]
                                ]
                            }
                            await self._tg.send_message(
                                chat_id=chat_id,
                                text=f"Игрок @{username} ответил: {text}\nВердикт ведущего?",
                                reply_markup=keyboard,
                            )
                        elif room.phase == Phase.FINAL_ANSWER:
                            await self._tg.send_message(
                                chat_id=chat_id,
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
                        await self._tg.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=f"Ведущий вынес вердикт: {'✅ Верно' if is_correct else '❌ Неверно'}",
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
                        dto = SelectQuestionDTO(room_id="room_1", player_id=player_id, question_id=q_id)
                        res = await self._select_question.execute(dto)
                        
                        await self._tg.send_message(
                            chat_id, 
                            f"Выбран вопрос за {res.question_value}\n\n{res.question_text}"
                        )
                        
                        if res.phase == Phase.READING.value:
                            kb = {"inline_keyboard": [[{"text": "🔴 Ждите...", "callback_data": "btn_room_1"}]]}
                            sent_msg = await self._tg.send_message(
                                chat_id, "Ожидайте активации кнопки...", reply_markup=kb
                            )
                            if "result" in sent_msg:
                                msg_id = sent_msg["result"]["message_id"]
                                import random
                                asyncio.create_task(self._activate_button(chat_id, msg_id, random.uniform(2.0, 5.0)))
                        elif res.phase == Phase.SPECIAL_EVENT.value:
                            await self._tg.send_message(
                                chat_id, "Спец-ивент!\n(Заглушка для Кота в мешке / Аукциона)"
                            )
                        elif res.phase == Phase.FINAL_ROUND.value:
                            kb = {"inline_keyboard": [[{"text": "🏁 Прием ставок", "callback_data": "final_start_stakes"}]]}
                            await self._tg.send_message(
                                chat_id, "ФИНАЛЬНЫЙ РАУНД! Ведущий: откройте прием ставок.", reply_markup=kb
                            )
                            
                    except Exception as e:
                        print(f"Ошибка при выборе вопроса: {e}")
                
                await self._tg.answer_callback_query(callback_query["id"])
                return

            if data == "final_start_stakes":
                if room and room.phase == Phase.FINAL_ROUND:
                    try:
                        await self._start_final_stake.execute("room_1")
                        kb = {"inline_keyboard": [[{"text": "🔒 Закрыть ставки", "callback_data": "final_close_stakes"}]]}
                        await self._tg.send_message(
                            chat_id, "📝 Прием ставок начат. Игроки могут делать ставки через `/stack <сумма>`. Ведущий: закройте прием, когда все ответят.", reply_markup=kb
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
                            chat_id, "🔒 Ставки закрыты! Игроки: отправьте свой ответ в чат обычным сообщением."
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
                # Fetch room again to get current_question text safely
                room_now = await self._state_repo.get_room("room_1")
                q_text = (
                    room_now.current_question.text
                    if room_now and room_now.current_question
                    else "Вопрос"
                )
                await self._tg.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"Вопрос: {q_text}\n\n🛑 Отвечает @{username}! Ждем ответ в чат.",
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

    async def _activate_button(self, chat_id: int, message_id: int, delay: float) -> None:
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

        green_markup = {"inline_keyboard": [[{"text": "🟢 Ответить", "callback_data": "btn_room_1"}]]}

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
                await self._tg.send_message(chat_id, "Ошибка получения файла от Telegram.")
                return

            file_path = file_info["result"]["file_path"]

            # Скачиваем файл во временную директорию
            os.makedirs("data/uploads", exist_ok=True)
            local_path = os.path.abspath(f"data/uploads/{file_id}.siq")

            await self._tg.send_message(chat_id, f"Скачиваю сик-пак '{file_name}'...")
            await self._tg.download_file(file_path, local_path)

            # Публикуем задачу на парсинг в RabbitMQ
            # Мы используем routing_key для передачи в соответствующую очередь
            await self._rabbit.publish("siq_parse_tasks", {"file_path": local_path})

            await self._tg.send_message(chat_id, f"Пакет '{file_name}' успешно загружен и отправлен в очередь на обработку!")
        except Exception as e:
            await self._tg.send_message(chat_id, f"Ошибка при скачивании/обработке пакета: {e}")
            print(f"Ошибка загрузки SIQ: {e}")


class WebSocketRouter:
    """Обработчик WebSocket-соединений."""

    async def handle_connection(self, ws: object) -> None:
        raise NotImplementedError
