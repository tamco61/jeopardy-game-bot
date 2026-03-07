import asyncio
import random

from src.domain.question import Question, QuestionType
from src.domain.room import Phase, Room
from src.infrastructure.postgres_repo import PostgresGameRepository
from src.infrastructure.redis_repo import RedisStateRepository
from src.infrastructure.telegram import TelegramHttpClient


class StartGameUseCase:
    """Сценарий запуска нового раунда."""

    def __init__(
        self,
        game_repo: PostgresGameRepository,
        state_repo: RedisStateRepository,
        telegram_client: TelegramHttpClient,
    ) -> None:
        self._game_repo = game_repo
        self._state_repo = state_repo
        self._tg = telegram_client

    async def execute(self, chat_id: int) -> None:
        """Имитация старта игры из main.py."""
        await self._state_repo.delete_room("room_1")
        await self._state_repo.release_button("room_1")

        room = Room(room_id="room_1", chat_id=chat_id, phase=Phase.READING)
        room.current_question = Question(
            question_id=1,
            theme_name="Загадки",
            text="Зимой и летом одним цветом?",
            answer="елка",
            value=300,
            question_type=QuestionType.NORMAL,
        )
        await self._state_repo.save_room(room)
        print(f"🎮 /start_game от chat_id={chat_id}. Комната в БД.")

        reply_markup = {
            "inline_keyboard": [[{"text": "🔴 Ждите...", "callback_data": "btn_room_1"}]]
        }

        result = await self._tg.send_message(
            chat_id=chat_id,
            text=f"Вопрос за {room.current_question.value}: {room.current_question.text}",
            reply_markup=reply_markup,
        )

        if not result.get("ok"):
            print(f"Ошибка отправки: {result}")
            return

        sent_message_id = result["result"]["message_id"]
        asyncio.create_task(self._activate_button(chat_id, sent_message_id))

    async def _activate_button(self, chat_id: int, message_id: int) -> None:
        """Ждёт случайное время (2-5 сек), переводит комнату в состояние ANSWERING."""
        delay = random.uniform(2.0, 5.0)
        print(f"⏱️ Таймер: кнопка станет зелёной через {delay:.1f} сек...")
        await asyncio.sleep(delay)

        room = await self._state_repo.get_room("room_1")
        if not room or room.phase != Phase.READING:
            print("Отмена таймера: комната не в состоянии READING.")
            return

        try:
            room.activate_buzzer()
            await self._state_repo.save_room(room)
            print("🟢 FSM: Кнопка активна! Phase =", room.phase)
        except Exception as e:
            print(f"Ошибка активации: {e}")
            return

        green_markup = {
            "inline_keyboard": [[{"text": "🟢 Ответить", "callback_data": "btn_room_1"}]]
        }

        await self._tg.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"Вопрос за {room.current_question.value}: {room.current_question.text}",
            reply_markup=green_markup,
        )
