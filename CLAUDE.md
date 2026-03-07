# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Package manager:** `uv` (not pip). Always prefix Python commands with `uv run`.

```bash
# Start the bot (long polling MVP)
uv run python src/main.py

# Run all tests
uv run pytest tests/ -v

# Run a single test
uv run pytest tests/test_game_domain.py::test_name -v

# Start infrastructure (Postgres, Redis, RabbitMQ)
docker compose up -d

# Generate a DB migration (after changing ORM models)
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head
```

## Architecture

The project is a multiplayer Jeopardy-style Telegram bot built with a simplified **Clean Architecture** approach. Dependencies point strictly inward.

```
Bot           (src/bot/, src/main.py)             ← Telegram updates in (Entrypoint)
Application   (src/application/)                  ← Use case orchestration
Domain        (src/domain/)                       ← Pure business logic, no I/O
Infrastructure(src/infrastructure/)               ← Redis, Postgres, Telegram HTTP implementations
```

### Domain layer (`src/domain/`)

The core is `Room` — a pure-Python FSM (Finite State Machine) dataclass with 11 phases.

All transitions are validated; invalid ones raise business errors from `src/domain/errors.py`. **Domain never imports from Application, Bot, or Infrastructure.**
It also contains `Player` and `Question` dataclasses.

### Application layer (`src/application/`)

Use cases contain the core orchestration flow of the game. Due to a simplified structure, Use Cases directly depend on concrete infrastructure implementations (no abstract interfaces/ports used):

- `PressButtonUseCase` — implements the atomic button race with `SETNX` using `RedisStateRepository`.
- `StartGameUseCase` — initializes the game, handles delays, acts as the stub for pushing random questions.
- `SubmitAnswerUseCase` — a stub (TODO) for verifying typed answers.

### Infrastructure layer (`src/infrastructure/`)

External connections and technical implementations:

- `redis_repo.py` (`RedisStateRepository`) — serializes `Room` to/from JSON in Redis; handles atomic locking.
- `postgres_repo.py` (`PostgresGameRepository`) — SQLAlchemy 2.0 async ORM (7 tables) and game state persistence.
- `telegram.py` (`TelegramHttpClient`) — thin aiohttp wrapper for Telegram Bot API.
- `rabbit.py` — RabbitMQ integration stub.

### Bot layer & Entry point

- `src/bot/handlers.py` — Contains `TelegramRouter`, which parses Telegram incoming updates and delegates execution to Use Cases.
- `src/bot/schemas.py` — Pydantic models for incoming updates.
- `src/main.py` is the **Entrypoint Composition Root** — it wires dependencies manually (Pure DI, no containers used) and runs the long-polling loop over `TelegramHttpClient.get_updates`.

### Configuration

`AppSettings` (`src/shared/config.py`) uses `pydantic-settings` and reads from `.env`. Required env vars: `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`.

## Code style

- Line length: 80, double quotes.
- Russian is used in docstrings, comments, and user-facing strings.
- `asyncio_mode = "auto"` in pytest — no need to mark tests with `@pytest.mark.asyncio`.
