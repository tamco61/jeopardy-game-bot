# Своя Игра — Telegram Bot

Многопользовательская викторина «Своя Игра» через Telegram, построенная по принципам **Clean Architecture** и **Domain-Driven Design (DDD)**.

---

## 📦 Стек технологий

| Компонент | Технология |
|---|---|
| Язык | Python 3.11+ |
| Архитектура | Simplified Clean Architecture, FSM (Конечный автомат) |
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
uv run python src/main.py
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
| `Room` FSM | ✅ Готов | Полный конечный автомат с фазами LOBBY → BOARD_VIEW → READING → WAITING_FOR_PUSH → ANSWERING ↔ FINAL_ROUND, пауза |
| `Player` | ✅ Готов | Баллы, блокировка на вопрос, статус готовности |
| `Question` | ✅ Готов | Обычный / Кот в мешке / Аукцион, проверка ответа |
| `LobbyManagement` | ✅ Готов | `Create / Join / Ready / Leave` Use Cases |
| `StartGameUseCase` | ✅ Готов | Старт раунда: лобби → игра (MVP-заглушка для вопросов) |
| `SelectQuestionUseCase` | ✅ Готов | Выбор вопроса из табло, таймер на чтение |
| `PressButtonUseCase` | ✅ Готов | Атомарная гонка через Redis `SETNX`, откат при ошибке |
| `SubmitAnswerUseCase` | ✅ Готов | Ввод текста игроком, проверка ведущим |
| `GameProcessUseCase` | ✅ Готов | Пауза (`PauseGameUseCase`) / Снятие с паузы (`UnpauseGameUseCase`) |
| `SpecialEventsUseCase` | ✅ Готов | Аукцион `PlaceStakeUseCase`, ставки в финале |
| `RedisStateRepository` | ✅ Готов | Сериализация Room ↔ JSON, блокировки кнопок |
| `PostgresGameRepository` | ✅ Готов | CRUD вопросов/тем/раундов через SQLAlchemy |
| `TelegramHttpClient` | ✅ Готов | Обёртка над aiohttp для Telegram Bot API |
| `TelegramRouter` | ✅ Готов | Маршрутизация текстовых обновлений и CallbackQuery по UseCase'ам |
| `main.py` (Long Polling) | ✅ Готов | Рабочий сборщик (Pure DI) для всех UseCases и обработка потери связи с БД |
| Юнит-тесты | ✅ 24 теста | FSM-переходы, пауза, финал, PressButtonUseCase |

### Что в планах (TODO)

| Компонент | Статус | Описание |
|---|---|---|
| Аутентификация / Роли | 🔲 Заглушка | Нормальная проверка `HOST` и `PLAYER` в Router'е |
| RabbitMQPublisher | ⚙️ Каркас | Подключение к RabbitMQ, publish сообщений |
| TelegramSenderWorker | 🔲 Заглушка | Потребитель очереди для отправки в Telegram |
| Сидер базы данных | 🔲 Заглушка | Парсинг и сохранение реальных пакетов (SIG) в Postgres |

---

## 📂 Структура проекта

```text
jeopardy-game-bot/
├── src/
│   ├── domain/                            # 🟢 ЯДРО — Чистая бизнес-логика
│   │   ├── room.py                        # Room FSM (11 фаз, все переходы)
│   │   ├── player.py                      # Player (очки, блокировка, ready)
│   │   ├── question.py                    # Question (текст, ответ, тип)
│   │   └── errors.py                      # Бизнес-ошибки (DomainError и др.)
│   │
│   ├── application/                       # 🟡 USE CASES — Оркестрация
│   │   ├── game_process.py                # ✅ PauseGameUseCase, UnpauseGameUseCase
│   │   ├── lobby_management.py            # ✅ Create/Join/Ready/LeaveLobbyUseCase
│   │   ├── press_button.py                # ✅ PressButtonUseCase
│   │   ├── select_question.py             # ✅ SelectQuestionUseCase
│   │   ├── special_events.py              # ✅ PlaceStakeUseCase, FinalStakeUseCase
│   │   ├── start_game.py                  # ✅ StartGameUseCase (MVP)
│   │   └── submit_answer.py               # ✅ SubmitAnswerUseCase
│   │
│   ├── infrastructure/                    # 🔵 ВНЕШНИЕ СЕРВИСЫ
│   │   ├── redis_repo.py                  # ✅ RedisStateRepository
│   │   ├── postgres_repo.py               # ✅ PostgresGameRepository + Models
│   │   ├── rabbit.py                      # ⚙️ RabbitMQPublisher
│   │   └── telegram.py                    # ✅ TelegramHttpClient
│   │
│   ├── bot/                               # 🟣 ВХОДНЫЕ ТОЧКИ (Telegram)
│   │   ├── handlers.py                    # ✅ TelegramRouter / WS Роутер
│   │   ├── schemas.py                     # DTO (IncomingTelegramUpdateDTO)
│   │   └── worker.py                      # 🔲 TelegramSenderWorker (TODO)
│   │
│   ├── shared/                            # 🔧 УТИЛИТЫ
│   │   ├── config.py                      # AppSettings (pydantic-settings)
│   │   └── logger.py                      # JSONLogger
│   │
│   └── main.py                            # ✅ Composition Root (Long Polling)
│
├── tests/
│   └── test_game_domain.py                # ✅ 24 юнит-теста
├── migrations/                            # Alembic миграции
├── alembic.ini
├── docker-compose.yml                     # Postgres + Redis + RabbitMQ
├── pyproject.toml
└── .env                                   # Конфигурация окружения
```

---

## 🏗 Архитектура (Simplified Clean Architecture)

```
┌─────────────────────────────────────────┐
│  Bot (main.py, TelegramRouter)          │  ← Входящие запросы
├─────────────────────────────────────────┤
│  Application (Use Cases)                │  ← Оркестрация
├─────────────────────────────────────────┤
│  Domain (Room FSM, Player, Question)    │  ← Чистая бизнес-логика
├─────────────────────────────────────────┤
│  Infrastructure (Redis, Postgres, TG)   │  ← Конкретные реализации
└─────────────────────────────────────────┘
```

**Правило зависимостей:** внутренние слои не знают о внешних. `Domain` не импортирует ничего из `Application` или `Infrastructure`. Код максимально упрощён: `Application` напрямую работает с конкретными классами `Infrastructure` без использования абстрактных интерфейсов. Передача зависимостей происходит в `main.py` (Pure DI).

---

## 🧪 Тесты

24 юнит-теста покрывают:
- **FSM-переходы** Room (LOBBY → BOARD_VIEW → READING → ANSWERING и обратно)
- **Правила игры** (блокировка игрока после неверного ответа, начисление/списание очков)
- **Финальный раунд** (ставки, проверка ответов, подсчёт итогов)
- **Пауза/возобновление** из любой фазы
- **PressButtonUseCase** (гонка, откат, комната не найдена)

```bash
uv run pytest tests/ -v
```

---

## 🔜 Следующие шаги

1. **Реализация ролевой модели** — полноценная проверка HOST/PLAYER в `TelegramRouter`.
2. **Система парсинга SIG пакетов** — загрузка реальных пакетов «Своей Игры» в базу PostgreSQL.
3. **Улучшение UI/UX в Telegram** — красивые инлайн-клавиатуры для табло (BOARD_VIEW), обновление сообщений.
4. **Интеграция с RabbitMQ Worker** — для надежной рассылки сообщений через брокер.
