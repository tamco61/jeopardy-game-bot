import asyncio

from src.application.press_button import PressButtonUseCase
from src.application.start_game import StartGameUseCase
from src.application.submit_answer import SubmitAnswerUseCase
from src.domain.player import Player
from src.infrastructure.redis_repo import RedisStateRepository
from src.infrastructure.telegram import TelegramHttpClient


class TelegramRouter:
    """Диспетчер входящих Telegram-обновлений."""

    def __init__(
        self,
        telegram_client: TelegramHttpClient,
        start_game_uc: StartGameUseCase,
        press_button_uc: PressButtonUseCase,
        submit_answer_uc: SubmitAnswerUseCase,
        state_repo: RedisStateRepository,
    ) -> None:
        self._tg = telegram_client
        self._start_game = start_game_uc
        self._press_button = press_button_uc
        self._submit_answer = submit_answer_uc
        self._state_repo = state_repo

    async def handle_update(self, update: dict) -> None:
        print(f"📩 Получен update: {update.get('update_id')}")

        message: dict | None = update.get("message")
        if message is not None:
            text: str = (message.get("text") or "").strip()
            chat_id: int = message["chat"]["id"]

            if text == "/start_game":
                await self._start_game.execute(chat_id)
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

            # Хак для MVP: автоматически добавляем юзера в комнату, если он кликнул
            room = await self._state_repo.get_room("room_1")
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


class WebSocketRouter:
    """Обработчик WebSocket-соединений."""

    async def handle_connection(self, ws: object) -> None:
        raise NotImplementedError
