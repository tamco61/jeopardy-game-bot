# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Package manager:** `uv` (not pip). Always prefix Python commands with `uv run`.

```bash
# Start the bot (long polling)
uv run python src/main.py

# Start background workers (SIQ parser + Telegram sender)
uv run python src/run_workers.py

# Run all tests
uv run pytest tests/ -v

# Run a single test
uv run pytest tests/test_game_domain.py::test_name -v

# Lint & format
uv run ruff check src/
uv run ruff format src/

# Start infrastructure (Postgres, Redis, RabbitMQ)
docker compose up -d

# Generate a DB migration (after changing ORM models)
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head
```

## Architecture

Multiplayer Jeopardy-style Telegram bot built with simplified **Clean Architecture**. Dependencies point strictly inward.

```
Bot           (src/bot/, src/main.py)             ← Telegram updates in (Entrypoint)
Application   (src/application/)                  ← Use case orchestration
Domain        (src/domain/)                       ← Pure business logic, no I/O
Infrastructure(src/infrastructure/)               ← Redis, Postgres, Telegram, RabbitMQ
Workers       (src/workers/, src/run_workers.py)  ← Background RabbitMQ consumers
```

### Domain layer (`src/domain/`)

The core is `Room` — a pure-Python FSM Pydantic model with 11 phases defined in `Phase` enum:

```
LOBBY → BOARD_VIEW → READING / SPECIAL_EVENT → WAITING_FOR_PUSH → ANSWERING → BOARD_VIEW
BOARD_VIEW → FINAL_ROUND → FINAL_STAKE → FINAL_ANSWER → RESULTS
Any (except LOBBY) ↔ PAUSE
```

All transitions validated by `_assert_phase()`; invalid ones raise errors from `src/domain/errors.py`. Domain never imports from Application, Bot, or Infrastructure.

### Application layer (`src/application/`)

Use Cases directly depend on concrete infrastructure (no abstract ports). Key use cases:
- `StartGameUseCase` — validates package, sets up first round, saves `Room` to Redis.
- `PressButtonUseCase` — atomic button race via `SETNX` in `RedisStateRepository`.
- `SelectQuestionUseCase` — fetches question from Postgres, transitions room FSM.
- `SubmitAnswerUseCase` — host verdict flow (correct/incorrect answer handling).
- `LobbyManagement` — `CreateLobbyUseCase`, `JoinLobbyUseCase`, `ReadyUseCase`, `LeaveLobbyUseCase`.
- `SpecialEvents` — stake placement and final round management.
- `SiqParser` (`src/application/parser/`) — parses `.siq` zip archives (SIGame format) into `PackageDTO` hierarchy.

### Infrastructure layer (`src/infrastructure/`)

- `redis_repo.py` (`RedisStateRepository`) — serializes `Room` to/from JSON in Redis. Keys: `room:{id}`, `button_lock:{id}`, `active_room:{telegram_id}`, `last_results:{chat_id}`. Button lock uses `SETNX` with 30-second TTL.
- `database/models.py` — 7 SQLAlchemy 2.0 async ORM tables: `users`, `packages`, `rounds`, `themes`, `questions`, `game_sessions`, `game_players`. Hot game state lives in Redis only; Postgres stores package content and final match results.
- `database/repositories/` — separate repo class per entity (`PackageRepository`, `RoundRepository`, `ThemeRepository`, `QuestionRepository`).
- `telegram.py` (`TelegramHttpClient`) — thin aiohttp wrapper for Telegram Bot API.
- `rabbit.py` (`RabbitMQPublisher`) — publishes tasks to RabbitMQ queues.

### Bot layer (`src/bot/`)

- `router.py` — lightweight `Router` with decorators `@command`, `@callback`, `@message`, `@document`. Methods are registered via `router.include_class(instance)`. Dependency injection by matching parameter names at call time (`execute_handler`).
- `handler.py` (`TelegramRouter`) — top-level dispatcher, routes to `LobbyHandler`, `GameHandler`, `AdminHandler`. For private messages, looks up the user's active room via Redis.
- `handlers/game.py` — game process callbacks and commands.
- `handlers/lobby.py` — lobby join/ready/leave commands.
- `handlers/admin.py` — pause/unpause and `.siq` file upload via document handler.
- `ui.py` (`JeopardyUI`) — builds inline keyboard boards, formats scoreboards, renders questions.

### Workers (`src/workers/`)

Separate process (`src/run_workers.py`). Two concurrent RabbitMQ consumers:
- `SiqParserWorker` — consumes `.siq` file bytes, parses via `SiqParser`, saves to Postgres.
- `TelegramSenderWorker` — consumes `{chat_id, text}` messages and sends via Telegram API.

### Configuration

`AppSettings` (`src/shared/config.py`) uses `pydantic-settings`. Required env vars: `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`.

## Code style

- Line length: 80, double quotes (ruff enforced with Google docstring convention).
- Russian is used in docstrings, comments, and all user-facing strings.
- `asyncio_mode = "auto"` in pytest — no need to mark tests with `@pytest.mark.asyncio`.
