"""
Jeopardy Game Bot — MVP (Long Polling).
Мультиплеерная игра на реакцию в Telegram-чате.

Стек: Python 3.11+, aiohttp (HTTP-клиент), redis.
"""

import asyncio
import os
import sys

import redis.asyncio as aioredis

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.game_process import PauseGameUseCase, UnpauseGameUseCase
from src.application.lobby_management import (
    CreateLobbyUseCase,
    JoinLobbyUseCase,
    LeaveLobbyUseCase,
    ReadyUseCase,
)
from src.application.press_button import PressButtonUseCase
from src.application.select_question import SelectQuestionUseCase
from src.application.special_events import (
    CloseFinalStakeUseCase,
    PlaceStakeUseCase,
    StartFinalStakeUseCase,
)
from src.application.start_game import StartGameUseCase
from src.application.submit_answer import SubmitAnswerUseCase
from src.bot.handlers import TelegramRouter
from src.infrastructure.database.postgres_repo import PostgresGameRepository
from src.infrastructure.database.base import build_engine, build_session_factory
from src.infrastructure.rabbit import RabbitMQPublisher
from src.infrastructure.redis_repo import RedisStateRepository
from src.infrastructure.telegram import TelegramHttpClient
from src.shared.config import AppSettings


# ──────────────────── Main polling loop ───────────────────────────────
async def main() -> None:
    print("🚀 Запуск бота (long polling)...")

    settings = AppSettings()

    # Инициализация БД
    try:
        engine = build_engine(settings.database_url)
        session_factory = build_session_factory(engine)
        game_repo = PostgresGameRepository(session_factory)
        print("✅ Подключено к PostgreSQL")
    except Exception as e:
        print(f"⚠️ Ошибка подключения к PostgreSQL (используем заглушку): {e}")
        game_repo = None

    try:
        redis_client = aioredis.from_url(settings.redis_url)
        # Проверка соединения с redis
        await redis_client.ping()
        state_repo = RedisStateRepository(redis_client)
        print("✅ Подключено к Redis")
    except Exception as e:
        print(f"⚠️ Ошибка подключения к Redis: {e}")

        # Создадим dummy repo если нет редиса, чтобы код хоть как-то не падал сразу при сборке DI
        class DummyRedisRepo(RedisStateRepository):
            def __init__(self):
                pass

            async def get_room(self, *args, **kwargs):
                return None

            async def save_room(self, *args, **kwargs):
                pass

            async def delete_room(self, *args, **kwargs):
                pass

            async def try_capture_button(self, *args, **kwargs):
                return False

            async def release_button(self, *args, **kwargs):
                pass

        state_repo = DummyRedisRepo()

    try:
        rabbitmq = RabbitMQPublisher(settings.rabbitmq_url)
        await rabbitmq.connect()
        print("✅ Подключено к RabbitMQ")
    except Exception as e:
        print(f"⚠️ Ошибка подключения к RabbitMQ: {e}")

        class DummyRabbit:
            async def publish(self, *args, **kwargs):
                pass

            async def connect(self):
                pass

            async def disconnect(self):
                pass

        rabbitmq = DummyRabbit()

    telegram_client = TelegramHttpClient(settings.telegram_bot_token)

    # Use Cases
    create_lobby_uc = CreateLobbyUseCase(state_repo)
    join_lobby_uc = JoinLobbyUseCase(state_repo)
    ready_uc = ReadyUseCase(state_repo)
    leave_lobby_uc = LeaveLobbyUseCase(state_repo)

    pause_uc = PauseGameUseCase(state_repo)
    unpause_uc = UnpauseGameUseCase(state_repo)

    press_uc = PressButtonUseCase(state_repo)
    start_game_uc = StartGameUseCase(
        game_repo=game_repo,
        state_repo=state_repo,
    )
    submit_answer_uc = SubmitAnswerUseCase(state_repo)
    select_question_uc = SelectQuestionUseCase(
        game_repo=game_repo, state_repo=state_repo
    )

    place_stake_uc = PlaceStakeUseCase(state_repo)
    start_final_stake_uc = StartFinalStakeUseCase(state_repo)
    close_final_stake_uc = CloseFinalStakeUseCase(state_repo)

    router = TelegramRouter(
        telegram_client=telegram_client,
        start_game_uc=start_game_uc,
        press_button_uc=press_uc,
        submit_answer_uc=submit_answer_uc,
        create_lobby_uc=create_lobby_uc,
        join_lobby_uc=join_lobby_uc,
        ready_uc=ready_uc,
        leave_lobby_uc=leave_lobby_uc,
        pause_game_uc=pause_uc,
        unpause_game_uc=unpause_uc,
        select_question_uc=select_question_uc,
        place_stake_uc=place_stake_uc,
        start_final_stake_uc=start_final_stake_uc,
        close_final_stake_uc=close_final_stake_uc,
        state_repo=state_repo,
        rabbit_publisher=rabbitmq,
    )

    await telegram_client.start()

    try:
        await telegram_client.delete_webhook()
        offset: int | None = None
        print("✅ Бот запущен. Ожидаю сообщения...\n")

        while True:
            try:
                data = await telegram_client.get_updates(offset=offset)

                if not data or not data.get("ok"):
                    print(f"❌ Ошибка от Telegram: {data}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    await router.handle_update(update)

            except asyncio.CancelledError:
                print("\n🛑 Остановка...")
                break
            except Exception as e:
                import traceback

                traceback.print_exc()
                print(f"❌ Критическая Ошибка: {e}")
                await asyncio.sleep(5)
    finally:
        await telegram_client.close()
        await rabbitmq.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен.")
