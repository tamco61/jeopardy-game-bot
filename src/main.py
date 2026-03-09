import asyncio
import os
import sys

import aio_pika
import aiohttp
import redis.asyncio as aioredis
from sqlalchemy.exc import SQLAlchemyError

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
from src.bot.handler import TelegramRouter
from src.bot.handlers.admin import AdminHandler
from src.bot.handlers.game import GameHandler
from src.bot.handlers.lobby import LobbyHandler
from src.bot.ui import JeopardyUI
from src.infrastructure.database.base import build_engine, build_session_factory
from src.infrastructure.database.postgres_repo import PostgresGameRepository
from src.infrastructure.rabbit import RabbitMQPublisher
from src.infrastructure.redis_repo import RedisStateRepository
from src.infrastructure.telegram import TelegramHttpClient
from src.shared.config import AppSettings
from src.shared.logger import get_logger

logger = get_logger(__name__)


# ──────────────────── Main polling loop ───────────────────────────────
async def main() -> None:
    logger.info("🚀 Запуск бота (long polling)...")

    settings = AppSettings()

    # Инициализация БД
    try:
        engine = build_engine(settings.database_url)
        session_factory = build_session_factory(engine)
        game_repo = PostgresGameRepository(session_factory)
        logger.info("✅ Подключено к PostgreSQL")
    except SQLAlchemyError:
        logger.error("❌ Критическая ошибка подключения к PostgreSQL")
        raise

    # Инициализация Redis
    try:
        redis_client = aioredis.from_url(settings.redis_url)
        await redis_client.ping()
        state_repo = RedisStateRepository(redis_client)
        logger.info("✅ Подключено к Redis")
    except aioredis.RedisError:
        logger.error("❌ Критическая ошибка подключения к Redis")
        raise

    # Инициализация RabbitMQ
    try:
        rabbitmq = RabbitMQPublisher(settings.rabbitmq_url)
        await rabbitmq.connect()
        logger.info("✅ Подключено к RabbitMQ")
    except aio_pika.AMQPException:
        logger.error("❌ Критическая ошибка подключения к RabbitMQ")
        raise

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

    # Handlers & UI
    ui = JeopardyUI(telegram_client)
    
    lobby_handler = LobbyHandler(
        tg_client=telegram_client,
        create_lobby_uc=create_lobby_uc,
        join_lobby_uc=join_lobby_uc,
        ready_uc=ready_uc,
        leave_lobby_uc=leave_lobby_uc,
        state_repo=state_repo,
    )

    game_handler = GameHandler(
        ui=ui,
        game_repo=game_repo,
        state_repo=state_repo,
        start_game_uc=start_game_uc,
        press_button_uc=press_uc,
        submit_answer_uc=submit_answer_uc,
        select_question_uc=select_question_uc,
        start_final_stake_uc=start_final_stake_uc,
        place_stake_uc=place_stake_uc,
        close_final_stake_uc=close_final_stake_uc,
    )

    admin_handler = AdminHandler(
        tg_client=telegram_client,
        pause_uc=pause_uc,
        unpause_uc=unpause_uc,
        rabbit_publisher=rabbitmq,
    )

    router = TelegramRouter(
        state_repo=state_repo,
        lobby_handler=lobby_handler,
        game_handler=game_handler,
        admin_handler=admin_handler,
    )

    await telegram_client.start()

    try:
        await telegram_client.delete_webhook()
        offset: int | None = None
        logger.info("✅ Бот запущен. Ожидаю сообщения...")

        while True:
            try:
                data = await telegram_client.get_updates(offset=offset)

                if not data or not data.get("ok"):
                    logger.error(f"❌ Ошибка от Telegram: {data}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    await router.handle_update(update)

            except aiohttp.ClientError as e:
                logger.error(f"❌ Сетевая ошибка при получении обновлений: {e}")
                await asyncio.sleep(5)
                continue

            except asyncio.CancelledError:
                logger.info("🛑 Остановка...")
                break
            except Exception as e:  # noqa: BLE001
                logger.exception(f"❌ Критическая Ошибка: {e}")
                await asyncio.sleep(5)
    finally:
        await telegram_client.close()
        await rabbitmq.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен.")
