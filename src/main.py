"""
Jeopardy Game Bot — MVP (Long Polling).
Мультиплеерная игра на реакцию в Telegram-чате.

Стек: Python 3.11+, aiohttp (HTTP-клиент), redis.
"""

import asyncio
import os
import sys

import redis.asyncio as aioredis

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.press_button import PressButtonUseCase
from src.application.start_game import StartGameUseCase
from src.application.submit_answer import SubmitAnswerUseCase
from src.bot.handlers import TelegramRouter
from src.infrastructure.redis_repo import RedisStateRepository
from src.infrastructure.telegram import TelegramHttpClient
from src.shared.config import AppSettings


# ──────────────────── Main polling loop ───────────────────────────────
async def main() -> None:
    print("🚀 Запуск бота (long polling)...")

    settings = AppSettings()
    
    # Инициализация зависимостей
    redis_client = aioredis.from_url(settings.redis_url)
    state_repo = RedisStateRepository(redis_client)
    
    telegram_client = TelegramHttpClient(settings.telegram_bot_token)
    
    press_uc = PressButtonUseCase(state_repo)
    start_game_uc = StartGameUseCase(
        game_repo=None,  # MVP заглушка, вопросы зашиты в коде
        state_repo=state_repo,
        telegram_client=telegram_client
    )
    submit_answer_uc = SubmitAnswerUseCase(state_repo)
    
    router = TelegramRouter(
        telegram_client=telegram_client,
        start_game_uc=start_game_uc,
        press_button_uc=press_uc,
        submit_answer_uc=submit_answer_uc,
        state_repo=state_repo,
    )

    await telegram_client.start()

    try:
        await telegram_client.delete_webhook()
        offset: int | None = None
        print("✅ Бот запущен. Ожидаю сообщения...\n")

        while True:
            try:
                data = await telegram_client.get_updates(offset=offset)

                if not data or not data.get("ok"):
                    print(f"❌ Ошибка от Telegram: {data}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    await router.handle_update(update)

            except asyncio.CancelledError:
                print("\n🛑 Остановка...")
                break
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"❌ Критическая Ошибка: {e}")
                await asyncio.sleep(5)
    finally:
        await telegram_client.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен.")
