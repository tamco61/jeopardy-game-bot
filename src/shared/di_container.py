"""Dependency Injection — сборка зависимостей «Своей игры».

TODO: собрать все зависимости когда все компоненты будут реализованы.

Пример итогового вида::

    settings = AppSettings()

    # Database
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    game_repo = PostgresGameRepository(session_factory)

    # Redis
    redis_client = redis.asyncio.from_url(settings.redis_url)
    state_repo = RedisStateRepository(redis_client)

    # RabbitMQ
    publisher = RabbitMQPublisher(settings.rabbitmq_url)

    # Telegram
    tg_client = TelegramHttpClient(settings.telegram_bot_token)

    # Use Cases
    start_game_uc = StartGameUseCase(game_repo, state_repo, publisher)
    press_button_uc = PressButtonUseCase(state_repo)
    submit_answer_uc = SubmitAnswerUseCase(state_repo)

    # Router
    telegram_router = TelegramRouter(
        tg_client, start_game_uc, press_button_uc, submit_answer_uc,
    )
"""
