"""Alembic env.py — async-миграции для «Своей Игры».

Конфигурация:
- DATABASE_URL читается из .env через pydantic-settings.
- Используется asyncpg (async engine).
- target_metadata берётся из ORM-моделей.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

# Добавляем корень проекта в sys.path, чтобы Python видел пакет src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Наши модели и конфиг ──────────────────────────
# Импорт ВСЕХ моделей, чтобы Alembic видел их metadata
from src.infrastructure.database.base import Base
from src.infrastructure.database.models import (  # noqa: F401
    GamePlayerModel,
    GameSessionModel,
    PackageModel,
    QuestionModel,
    RoundModel,
    ThemeModel,
    UserModel,
)
from src.shared.config import AppSettings

# ─────────────────────────────────────────────────

config = context.config
settings = AppSettings()

# Подставляем URL из .env (asyncpg для async-миграций)
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Миграции в offline-режиме (генерация SQL без подключения к БД)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Запуск миграций с уже готовым connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Async-миграции через asyncpg."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Миграции в online-режиме (с подключением к БД)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
