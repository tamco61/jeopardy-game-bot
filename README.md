# Своя Игра — Telegram Bot

Многопользовательская викторина «Своя Игра» через Telegram, построенная по принципам **Clean Architecture** и **Domain-Driven Design (DDD)**.

---

## 📦 Стек технологий

| Компонент | Технология |
|---|---|
| Язык | Python 3.11+ |
| Архитектура | Clean Architecture, FSM (Конечный автомат) |
| Telegram API | Long Polling через `aiohttp` |
| Кэш / Состояние | Redis (`redis.asyncio`, атомарный `SETNX`) |
| База данных | PostgreSQL + SQLAlchemy 2.0 (async) |
| Очередь сообщений | RabbitMQ (`aio-pika`) |
| Миграции БД | Alembic (async) |
| Валидация | Pydantic v2 / pydantic-settings |
| Тесты | pytest + pytest-asyncio |
| Контейнеризация | Docker Compose |

---

## 🚀 Как запустить локально

### 1. Подготовка
Убедитесь, что у вас есть файл `.env` в корне проекта (уже поставляется с проектом). В нём указаны `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL` и `TELEGRAM_BOT_TOKEN`.

### 2. Запуск инфраструктуры
```bash
docker compose up -d
```
Поднимутся три контейнера: **Postgres 16**, **Redis 7** и **RabbitMQ 3** (Management UI на `http://localhost:15672`).

### 3. Миграции БД (Alembic)

**Сгенерировать миграцию** (после изменения моделей):
```bash
uv run alembic revision --autogenerate -m "описание"
```
**Применить миграции:**
```bash
uv run alembic upgrade head
```

### 4. Запуск бота
```bash
python src/main.py
```
Бот запустится в режиме long polling. Напишите боту `/start_game` в Telegram-чате — он отправит вопрос с кнопкой «🔴 Ждите...», через 2–5 секунд кнопка станет зелёной «🟢 Ответить», и начнётся гонка на реакцию.

### 5. Запуск тестов
```bash
uv run pytest tests/ -v
```

---

## ✅ Текущее состояние (MVP)

Реализован и обкатан **самый сложный механизм**: конечный автомат (FSM) игровой комнаты и атомарная **«гонка нажатий»** за право отвечать на вопрос.

### Что работает

| Компонент | Статус | Описание |
|---|---|---|
| `Room` FSM | ✅ Готов | Полный конечный автомат с фазами LOBBY → BOARD_VIEW → READING → WAITING_FOR_PUSH → ANSWERING → BOARD_VIEW, финальный раунд, пауза |
| `Player` | ✅ Готов | Баллы, блокировка на вопрос, статус готовности |
| `Question` | ✅ Готов | Обычный / Кот в мешке / Аукцион, проверка ответа |
| `PressButtonUseCase` | ✅ Готов | Атомарная гонка через Redis `SETNX`, откат при ошибке |
| `RedisStateRepository` | ✅ Готов | Сериализация Room ↔ JSON, блокировки кнопок |
| `PostgresGameRepository` | ✅ Готов | CRUD вопросов/тем/раундов через SQLAlchemy |
| `TelegramHttpClient` | ✅ Готов | Обёртка над aiohttp для Telegram Bot API |
| `main.py` (Long Polling) | ✅ Готов | Рабочий MVP: `/start_game`, таймер кнопки, гонка |
| Юнит-тесты | ✅ 14 тестов | FSM-переходы, пауза, финал, PressButtonUseCase с моками |

### Что в заглушках (TODO)

| Компонент | Статус | Описание |
|---|---|---|
| `SubmitAnswerUseCase` | 🔲 Заглушка | Проверка текстового ответа игрока |
| `StartGameUseCase` | 🔲 Заглушка | Старт раунда: вопрос из БД + создание комнаты |
| `TelegramRouter` | 🔲 Заглушка | Маршрутизация обновлений по Use Case'ам |
| `di_container.py` | 🔲 Заглушка | DI-контейнер (пока только псевдокод-пример) |
| `RabbitMQPublisher` | ⚙️ Каркас | Подключение к RabbitMQ, publish сообщений |
| `TelegramSenderWorker` | 🔲 Заглушка | Потребитель очереди для отправки в Telegram |

---

## 📂 Структура проекта

```text
jeopardy-game-bot/
├── src/
│   ├── domain/                            # 🟢 ЯДРО — Чистая бизнес-логика
│   │   ├── entities/
│   │   │   ├── room.py                    # Room FSM (11 фаз, все переходы)
│   │   │   ├── player.py                  # Player (очки, блокировка, ready)
│   │   │   └── question.py               # Question (текст, ответ, тип)
│   │   └── exception/
│   │       ├── base.py                    # DomainError
│   │       ├── invalid_transition.py      # InvalidTransitionError
│   │       ├── player_blocked.py          # PlayerBlockedError
│   │       └── player_not_found.py        # PlayerNotFoundError
│   │
│   ├── application/                       # 🟡 USE CASES — Оркестрация
│   │   ├── interfaces/                    # Порты (абстракции)
│   │   │   ├── state_repository.py        # IStateRepository (Redis)
│   │   │   ├── game_repository.py         # IGameRepository (Postgres)
│   │   │   └── message_publisher.py       # IMessagePublisher (RabbitMQ)
│   │   └── use_cases/
│   │       ├── press_button.py            # ✅ PressButtonUseCase
│   │       ├── submit_answer.py           # 🔲 SubmitAnswerUseCase (TODO)
│   │       └── start_game.py              # 🔲 StartGameUseCase (TODO)
│   │
│   ├── infrastructure/                    # 🔵 ВНЕШНИЕ СЕРВИСЫ
│   │   ├── cache/
│   │   │   └── redis_state_repo.py        # ✅ RedisStateRepository
│   │   ├── database/
│   │   │   ├── base.py                    # SQLAlchemy Base
│   │   │   ├── models.py                  # ORM-модели (7 таблиц)
│   │   │   └── postgres_game_repo.py      # ✅ PostgresGameRepository
│   │   ├── messaging/
│   │   │   └── rabbit_publisher.py        # ⚙️ RabbitMQPublisher
│   │   └── telegram/
│   │       └── http_client.py             # ✅ TelegramHttpClient
│   │
│   ├── presentation/                      # 🟣 ВХОДНЫЕ ТОЧКИ
│   │   ├── api/
│   │   │   ├── telegram_router.py         # 🔲 TelegramRouter (TODO)
│   │   │   └── websocket_router.py        # 🔲 WebSocket роутер
│   │   └── schemas/
│   │       ├── incoming_update.py         # IncomingTelegramUpdateDTO
│   │       └── ws_message.py              # WebSocketMessageDTO
│   │
│   ├── workers/                           # ⚙️ ФОНОВЫЕ ВОРКЕРЫ
│   │   ├── base_worker.py                 # BaseWorker
│   │   └── telegram_sender.py             # 🔲 TelegramSenderWorker
│   │
│   ├── shared/                            # 🔧 УТИЛИТЫ
│   │   ├── config.py                      # AppSettings (pydantic-settings)
│   │   ├── di_container.py                # 🔲 DI-контейнер (TODO)
│   │   └── logger.py                      # JSONLogger
│   │
│   └── main.py                            # ✅ Точка входа (Long Polling MVP)
│
├── tests/
│   ├── test_game_domain.py                # ✅ 14 юнит-тестов (FSM + UseCase)
│   ├── conftest.py
│   ├── unit/                              # (будущие юнит-тесты)
│   └── integration/                       # (будущие интеграционные тесты)
│
├── migrations/                            # Alembic миграции
├── alembic.ini
├── docker-compose.yml                     # Postgres + Redis + RabbitMQ
├── pyproject.toml
├── requirements.txt
└── .env                                   # Конфигурация окружения
```

---

## 🏗 Архитектура (Clean Architecture)

```
┌─────────────────────────────────────────┐
│  Presentation (main.py, TelegramRouter) │  ← Входящие запросы
├─────────────────────────────────────────┤
│  Application (Use Cases, Interfaces)    │  ← Оркестрация
├─────────────────────────────────────────┤
│  Domain (Room FSM, Player, Question)    │  ← Чистая бизнес-логика
├─────────────────────────────────────────┤
│  Infrastructure (Redis, Postgres, TG)   │  ← Реализация интерфейсов
└─────────────────────────────────────────┘
```

**Правило зависимостей:** внутренние слои не знают о внешних. `Domain` не импортирует ничего из `Infrastructure`. `Application` работает через абстрактные интерфейсы (`IStateRepository`, `IGameRepository`), а конкретные реализации (`RedisStateRepository`, `PostgresGameRepository`) подключаются снаружи.

---

## 🧪 Тесты

14 юнит-тестов покрывают:
- **FSM-переходы** Room (LOBBY → BOARD_VIEW → READING → ANSWERING и обратно)
- **Правила игры** (блокировка игрока после неверного ответа, начисление/списание очков)
- **Финальный раунд** (ставки, проверка ответов, подсчёт итогов)
- **Пауза/возобновление** из любой фазы
- **PressButtonUseCase** с моком `IStateRepository` (гонка, откат, комната не найдена)

```bash
uv run pytest tests/ -v
```

---

## 🔜 Следующие шаги

1. **`SubmitAnswerUseCase`** — проверка текстового ответа и продвижение FSM.
2. **`StartGameUseCase`** — выбор вопроса из БД, создание комнаты.
3. **`TelegramRouter`** — маршрутизация обновлений по Use Case'ам.
4. **DI-контейнер** — нормальная сборка зависимостей.
5. **Сидер вопросов** — загрузка паков «Своей Игры» в Postgres.
