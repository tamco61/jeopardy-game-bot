# 🎮 Своя Игра — Telegram Bot

Многопользовательская викторина «Своя Игра» для Telegram. Бот поддерживает игру в групповых чатах с гонками на реакцию, автоматической проверкой ответов через ИИ и финальным раундом со ставками.

---

## 🚀 Запуск

### 1. Настройка окружения

Создайте файл `.env` в корне проекта:

```env
# Telegram
TELEGRAM_BOT_TOKEN=your-bot-token-here

# Database
POSTGRES_USER=jeopardy
POSTGRES_PASSWORD=supersecret
POSTGRES_DB=jeopardy_db
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}

# Redis
REDIS_URL=redis://redis:6379/0

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

# OpenRouter API (для авто-режима проверки ответов)
OPENROUTER_API_KEY=sk-or-v1-your-api-key-here
OPENROUTER_MODEL=openai/gpt-4o-mini
```

> **Получить API ключ OpenRouter:** [openrouter.ai/keys](https://openrouter.ai/keys)

### 2. Запуск

```bash
docker compose up -d
```


---

## 📂 Структура проекта

```
jeopardy-game-bot/
├── src/
│   ├── domain/
│   │   ├── room.py                # Room FSM (фазы игры)
│   │   ├── player.py              # Игрок (очки, блокировки)
│   │   ├── question.py            # Вопрос (тип, ответ)
│   │   └── errors.py              # Бизнес-ошибки
│   │
│   ├── application/
│   │   ├── lobby_management.py    # Create/Join/Ready/Leave
│   │   ├── game_process.py        # Pause/Unpause
│   │   ├── press_button.py        # Гонка на реакцию
│   │   ├── select_question.py     # Выбор вопроса
│   │   ├── submit_answer.py       # Отправка ответа
│   │   ├── special_events.py      # Аукцион, финал
│   │   ├── start_game.py          # Старт игры
│   │   └── parser/                # Парсер SIQ
│   │
│   ├── infrastructure/
│   │   ├── database/              # PostgreSQL модели и репозитории
│   │   ├── redis_repo.py          # Redis состояние
│   │   ├── telegram.py            # Telegram клиент
│   │   ├── rabbit.py              # RabbitMQ publisher
│   │   ├── rabbit_rpc.py          # RPC Gateway
│   │   └── llm_verifier.py        # OpenRouter API
│   │
│   ├── bot/
│   │   ├── handlers/
│   │   │   ├── game.py            # Игровой процесс
│   │   │   ├── lobby.py           # Лобби
│   │   │   └── admin.py           # Админка
│   │   ├── router.py              # Маршрутизация событий
│   │   ├── ui.py                  # UI презентации
│   │   └── callback.py            # Callback данные
│   │
│   ├── apps/
│   │   ├── core/                  # Основной бот
│   │   ├── poller/                # Telegram poller
│   │   ├── worker/                # Telegram worker
│   │   ├── proxy/                 # WebSocket прокси
│   │   ├── admin/                 # Админ панель
│   │   └── parser/                # SIQ парсер
│   │
│   ├── shared/
│   │   ├── config.py              # Настройки
│   │   ├── logger.py              # Логгер
│   │   └── messages.py            # Сообщения
│   │
│   └── workers/
│       ├── base.py                # Базовый воркер
│       ├── siq_parser_worker.py   # Парсер SIQ
│       └── telegram_sender_worker.py # Отправка сообщений
│
├── tests/
│   ├── test_game_domain.py        # Тесты домена
│   └── test_parser.py             # Тесты парсера
│
├── migrations/                    # Alembic миграции
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── pyproject.toml
└── .env
```
