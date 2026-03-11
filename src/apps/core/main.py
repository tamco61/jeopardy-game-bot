import asyncio
import aio_pika
import redis.asyncio as aioredis
from pydantic import ValidationError

from src.application.game_process import PauseGameUseCase, UnpauseGameUseCase
from src.application.lobby_management import (
    CreateLobbyUseCase, JoinLobbyUseCase, LeaveLobbyUseCase, ReadyUseCase,
)
from src.application.press_button import PressButtonUseCase
from src.application.select_question import SelectQuestionUseCase
from src.application.special_events import (
    CloseFinalStakeUseCase, PlaceStakeUseCase, StartFinalStakeUseCase,
)
from src.application.start_game import StartGameUseCase
from src.application.submit_answer import SubmitAnswerUseCase
from src.bot.handler import TelegramRouter
from src.bot.handlers.admin import AdminHandler
from src.bot.handlers.game import GameHandler
from src.bot.handlers.lobby import LobbyHandler
from src.bot.ui import JeopardyUI
from src.infrastructure.database.base import build_engine, build_session_factory
from src.infrastructure.database.repositories.package import PackageRepository
from src.infrastructure.database.repositories.question import QuestionRepository
from src.infrastructure.database.repositories.round import RoundRepository
from src.infrastructure.database.repositories.theme import ThemeRepository
from src.infrastructure.rabbit import RabbitMQPublisher
from src.infrastructure.rabbit_rpc import RabbitMQMessageGateway
from src.infrastructure.redis_repo import RedisStateRepository
from src.shared.config import AppSettings
from src.shared.logger import get_logger
from src.shared.messages import IncomingTelegramEvent

logger = get_logger(__name__)

async def main() -> None:
    settings = AppSettings()

    logger.info("🚀 Запуск Core сервиса...")

    # Инициализация БД
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    package_repo = PackageRepository(session_factory)
    question_repo = QuestionRepository(session_factory)
    round_repo = RoundRepository(session_factory)
    theme_repo = ThemeRepository(session_factory)
    logger.info("✅ Подключено к PostgreSQL")

    # Инициализация Redis
    try:
        redis_client = aioredis.from_url(settings.redis_url)
        await redis_client.ping()
        state_repo = RedisStateRepository(redis_client)
        logger.info("✅ Подключено к Redis")
    except aioredis.RedisError:
        logger.error("❌ Критическая ошибка подключения к Redis")
        raise

    # Инициализация RabbitMQ Publisher (для siq_parse_tasks)
    try:
        rabbitmq = RabbitMQPublisher(settings.rabbitmq_url)
        await rabbitmq.connect()
    except aio_pika.AMQPException:
        logger.error("❌ Критическая ошибка подключения к RabbitMQ (Publisher)")
        raise

    # Инициализация RPC Gateway
    gateway = RabbitMQMessageGateway(settings.rabbitmq_url)
    await gateway.connect()
    logger.info("✅ RPC Gateway подключен к RabbitMQ")

    # Use Cases
    create_lobby_uc = CreateLobbyUseCase(state_repo)
    join_lobby_uc = JoinLobbyUseCase(state_repo)
    ready_uc = ReadyUseCase(state_repo)
    leave_lobby_uc = LeaveLobbyUseCase(state_repo)

    pause_uc = PauseGameUseCase(state_repo)
    unpause_uc = UnpauseGameUseCase(state_repo)

    press_uc = PressButtonUseCase(state_repo)
    start_game_uc = StartGameUseCase(
        package_repo=package_repo, round_repo=round_repo, state_repo=state_repo,
    )
    submit_answer_uc = SubmitAnswerUseCase(state_repo)
    select_question_uc = SelectQuestionUseCase(
        question_repo=question_repo, state_repo=state_repo
    )

    place_stake_uc = PlaceStakeUseCase(state_repo)
    start_final_stake_uc = StartFinalStakeUseCase(state_repo)
    close_final_stake_uc = CloseFinalStakeUseCase(state_repo)

    # Handlers & UI (внедряем RPC Gateway вместо TelegramHttpClient)
    ui = JeopardyUI(gateway)

    lobby_handler = LobbyHandler(
        tg_client=gateway,
        create_lobby_uc=create_lobby_uc,
        join_lobby_uc=join_lobby_uc,
        ready_uc=ready_uc,
        leave_lobby_uc=leave_lobby_uc,
        state_repo=state_repo,
    )

    game_handler = GameHandler(
        ui=ui,
        package_repo=package_repo,
        question_repo=question_repo,
        theme_repo=theme_repo,
        round_repo=round_repo,
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
        tg_client=gateway,
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

    # Восстанавливаем таймеры
    await game_handler.restore_timers()

    # Подключаем консьюмер для tg_updates
    connection = None
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()
        queue = await channel.declare_queue("tg_updates", auto_delete=False)
        
        logger.info("📡 Core запущен. Ожидание событий Telegram...")

        async def process_update(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    event = IncomingTelegramEvent.model_validate_json(message.body)
                    # Вызываем роутер с "сырыми" данными Telegram, как это было раньше
                    await router.handle_update(event.data)
                except ValidationError as e:
                    logger.error("❌ Неверный формат события: %s", e)
                except Exception as e:
                    logger.exception("❌ Ошибка при обработке события: %s", e)

        await queue.consume(process_update)
        
        await asyncio.Event().wait()

    except Exception as e:
        logger.exception("❌ Критическая Ошибка в Core: %s", e)
    finally:
        await gateway.disconnect()
        await rabbitmq.disconnect()
        if connection:
            await connection.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Core остановлен.")
