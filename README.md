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
│   ├── domain/                # Бизнес-логика (DDD)
│   │   ├── room.py            # FSM комнаты и фазы игры
│   │   ├── player.py          # Модель игрока
│   │   ├── question.py        # Модель вопроса
│   │   └── errors.py          # Бизнес-ошибки
│   │
│   ├── application/           # Cases (Сценарии использования)
│   │   ├── lobby_management.py # Логика лобби (join/ready)
│   │   ├── game_process.py    # Управление игровым процессом
│   │   ├── press_button.py    # Логика нажатия на кнопку
│   │   ├── select_question.py # Выбор вопроса
│   │   ├── submit_answer.py   # Обработка ответов
│   │   ├── special_events.py  # Аукционы и финал
│   │   ├── start_game.py      # Инициализация игры
│   │   ├── media_uploader.py  # Загрузка медиафайлов
│   │   └── parser/            # Логика парсинга SIQ
│   │
│   ├── infrastructure/        # Инфраструктурный слой
│   │   ├── database/          # SQLAlchemy модели и репозитории
│   │   │   ├── models.py      # Описание таблиц БД
│   │   │   └── repositories/  # Репозитории (game_session, package, question, round, theme)
│   │   ├── redis_repo.py      # Хранилище состояний в Redis
│   │   ├── telegram.py        # Интеграция с Telegram
│   │   ├── rabbit.py          # Работа с RabbitMQ
│   │   ├── rabbit_rpc.py      # RPC через RabbitMQ
│   │   └── llm_verifier.py    # Проверка ответов через AI
│   │
│   ├── bot/                   # Слой Telegram бота
│   │   ├── handlers/          # Обработчики (admin, game, lobby)
│   │   ├── router.py          # Роутинг событий
│   │   ├── ui.py              # Генерация UI сообщений
│   │   └── callback.py        # Обработка callback-кнопок
│   │
│   ├── apps/                  # Микросервисы (точки входа)
│   │   ├── core/              # Центральный сервис логики
│   │   ├── poller/            # Получение обновлений (main, mapper)
│   │   ├── worker/            # Воркер для тяжелых задач
│   │   ├── proxy/             # Прокси для Web-интерфейса (+ static)
│   │   ├── admin/             # Панель управления (+ static)
│   │   └── parser/            # Сервис парсинга паков
│   │
│   ├── shared/                # Общие утилиты
│   │   ├── config.py          # Настройки приложения
│   │   ├── logger.py          # Логирование
│   │   └── messages.py        # Текстовые константы
│   │
│   └── workers/               # Реализации воркеров (base, siq, telegram)
│
├── tests/                     # Тесты (test_game_domain, test_parser, verify_admin_auth)
├── migrations/                # Миграции базы данных (Alembic)
├── data/                      # Локальное хранилище данных (паки, медиа)
├── docker-compose.yml         # Конфигурация Docker
├── Dockerfile                 # Инструкции сборки
├── alembic.ini                # Настройки миграций
├── pyproject.toml             # Зависимости и настройки проекта
└── .env                       # Переменные окружения
```
```
by
ahatovtemur@yandex.ru
Ахатов Тимур Ильдарович
@brnthsk
```
