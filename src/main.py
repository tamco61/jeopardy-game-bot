"""
Jeopardy Game Bot — MVP (Long Polling).
Мультиплеерная игра на реакцию в Telegram-чате.

Стек: Python 3.11+, aiohttp (HTTP-клиент), redis.
"""

import asyncio
import json
import os
import random

import redis.asyncio as aioredis
from aiohttp import ClientSession

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.use_cases.press_button import PressButtonUseCase
from src.domain.entities.player import Player
from src.domain.entities.question import Question, QuestionType
from src.domain.entities.room import Phase, Room
from src.domain.exception.invalid_transition import InvalidTransitionError
from src.domain.exception.player_blocked import PlayerBlockedError
from src.shared.config import AppSettings
from src.infrastructure.cache.redis_state_repo import RedisStateRepository

# ───────────────────────── Telegram Bot Token ─────────────────────────
settings = AppSettings()
BOT_TOKEN: str = settings.telegram_bot_token
API_BASE: str = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ──────────────────── Telegram API helper wrappers ────────────────────
async def send_message(
    session: ClientSession,
    chat_id: int,
    text: str,
    reply_markup: dict | None = None,
) -> dict:
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup)

    async with session.post(f"{API_BASE}/sendMessage", data=payload) as resp:
        return await resp.json()

async def edit_message_text(
    session: ClientSession,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: dict | None = None,
) -> dict:
    payload: dict = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup)

    async with session.post(f"{API_BASE}/editMessageText", data=payload) as resp:
        return await resp.json()

async def answer_callback_query(
    session: ClientSession,
    callback_query_id: str,
    text: str = "",
    show_alert: bool = False,
) -> dict:
    payload: dict = {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert,
    }

    async with session.post(f"{API_BASE}/answerCallbackQuery", data=payload) as resp:
        return await resp.json()

async def get_updates(
    session: ClientSession,
    offset: int | None = None,
    timeout: int = 30,
) -> dict:
    payload: dict = {
        "timeout": timeout,
        "allowed_updates": json.dumps(["message", "callback_query"]),
    }
    if offset is not None:
        payload["offset"] = offset

    async with session.post(f"{API_BASE}/getUpdates", data=payload) as resp:
        return await resp.json()

async def delete_webhook(session: ClientSession) -> None:
    async with session.post(f"{API_BASE}/deleteWebhook") as resp:
        result = await resp.json()
        print(f"deleteWebhook: {result}")

# ───────────────── Timer: активация кнопки ────────────────────────────
async def activate_button(
    session: ClientSession,
    chat_id: int,
    message_id: int,
    state_repo: RedisStateRepository,
) -> None:
    """Ждёт случайное время (2-5 сек), переводит комнату в состояние ANSWERING."""
    delay = random.uniform(2.0, 5.0)
    print(f"⏱️  Таймер: кнопка станет зелёной через {delay:.1f} сек...")
    await asyncio.sleep(delay)

    room = await state_repo.get_room("room_1")
    if not room or room.phase != Phase.READING:
        print("Отмена таймера: комната не в состоянии READING.")
        return

    # Активируем кнопку в FSM
    try:
        room.activate_buzzer()
        await state_repo.save_room(room)
        print("🟢 FSM: Кнопка активна! Phase =", room.phase)
    except Exception as e:
        print(f"Ошибка активации: {e}")
        return

    green_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "🟢 Ответить",
                    "callback_data": "btn_room_1",
                }
            ]
        ]
    }

    await edit_message_text(
        session,
        chat_id,
        message_id,
        f"Вопрос за {room.current_question.value}: {room.current_question.text}",
        reply_markup=green_markup,
    )

# ─────────────────────── Update handler ───────────────────────────────
async def handle_update(
    session: ClientSession,
    update: dict,
    state_repo: RedisStateRepository,
    press_uc: PressButtonUseCase,
) -> None:
    print(f"📩 Получен update: {update.get('update_id')}")

    message: dict | None = update.get("message")
    if message is not None:
        text: str = (message.get("text") or "").strip()
        chat_id: int = message["chat"]["id"]

        if text == "/start_game":
            # Имитация StartGameUseCase: очищаем старое и создаём новое
            await state_repo.delete_room("room_1")
            await state_repo.release_button("room_1")

            room = Room(room_id="room_1", chat_id=chat_id, phase=Phase.READING)
            room.current_question = Question(
                question_id=1,
                theme_name="Загадки",
                text="Зимой и летом одним цветом?",
                answer="елка",
                value=300,
                question_type=QuestionType.NORMAL,
            )
            await state_repo.save_room(room)
            print(f"🎮 /start_game от chat_id={chat_id}. Комната в БД.")

            reply_markup = {
                "inline_keyboard": [[{"text": "🔴 Ждите...", "callback_data": "btn_room_1"}]]
            }

            result = await send_message(
                session,
                chat_id,
                f"Вопрос за {room.current_question.value}: {room.current_question.text}",
                reply_markup=reply_markup,
            )

            if not result.get("ok"):
                print(f"Ошибка отправки: {result}")
                return

            sent_message_id = result["result"]["message_id"]
            asyncio.create_task(activate_button(session, chat_id, sent_message_id, state_repo))

        return

    callback_query: dict | None = update.get("callback_query")
    if callback_query is not None:
        user: dict = callback_query["from"]
        player_id = str(user["id"])
        username: str = user.get("username") or user.get("first_name", "unknown")
        
        callback_message: dict = callback_query["message"]
        chat_id = callback_message["chat"]["id"]
        message_id: int = callback_message["message_id"]

        # Хак для MVP: автоматически добавляем юзера в комнату, если он кликнул
        room = await state_repo.get_room("room_1")
        if room and player_id not in room.players:
            # Обходим проверку LOBBY
            room.players[player_id] = Player(
                player_id=player_id, telegram_id=user["id"], username=username, score=0
            )
            await state_repo.save_room(room)

        # ── Логика гонки через Use Case ─────────────────────────────
        result = await press_uc.execute("room_1", player_id)

        if result.captured:
            print(f"🏆 ПЕРВЫЙ нажал: @{username}")
            await edit_message_text(
                session,
                chat_id,
                message_id,
                f"Вопрос: {room.current_question.text}\n\n🛑 Отвечает @{username}! Ждем ответ в чат.",
            )
            await answer_callback_query(session, callback_query["id"], text="Твой ответ!")
        else:
            print(f"⏳ Неудача: @{username} — причина: {result.error}")
            await answer_callback_query(
                session,
                callback_query["id"],
                text=result.error or "Кто-то успел раньше!",
            )

# ──────────────────── Main polling loop ───────────────────────────────
async def main() -> None:
    print("🚀 Запуск бота (long polling)...")

    # Инициализация зависимостей
    redis_client = aioredis.from_url(settings.redis_url)
    state_repo = RedisStateRepository(redis_client)
    press_uc = PressButtonUseCase(state_repo)

    async with ClientSession() as session:
        await delete_webhook(session)
        offset: int | None = None
        print("✅ Бот запущен. Ожидаю сообщения...\n")

        while True:
            try:
                data = await get_updates(session, offset=offset)

                if not data or not data.get("ok"):
                    print(f"❌ Ошибка от Telegram: {data}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    await handle_update(session, update, state_repo, press_uc)

            except asyncio.CancelledError:
                print("\n🛑 Остановка...")
                break
            except Exception as e:
                print(f"❌ Критическая Ошибка: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен.")
