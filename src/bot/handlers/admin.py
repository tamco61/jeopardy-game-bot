import os

from src.application.game_process import PauseGameUseCase, UnpauseGameUseCase
from src.infrastructure.rabbit import RabbitMQPublisher
from src.infrastructure.telegram import TelegramHttpClient


class AdminHandler:
    """Обработчик административных команд (пауза, загрузка пакетов)."""

    def __init__(
        self,
        tg_client: TelegramHttpClient,
        pause_uc: PauseGameUseCase,
        unpause_uc: UnpauseGameUseCase,
        rabbit_publisher: RabbitMQPublisher,
    ) -> None:
        self._tg = tg_client
        self._pause = pause_uc
        self._unpause = unpause_uc
        self._rabbit = rabbit_publisher

    async def handle_pause(self, chat_id: int, room_id: str, player_id: str) -> None:
        try:
            await self._pause.execute(room_id, player_id)
            await self._tg.send_message(chat_id, "⏸ Игра поставлена на паузу.")
        except Exception as e:
            await self._tg.send_message(chat_id, f"Ошибка: {e}")

    async def handle_unpause(self, chat_id: int, room_id: str, player_id: str) -> None:
        try:
            phase_name = await self._unpause.execute(room_id, player_id)
            await self._tg.send_message(chat_id, f"▶️ Снята с паузы. Возврат в: {phase_name}")
        except Exception as e:
            await self._tg.send_message(chat_id, f"Ошибка: {e}")

    async def handle_document(self, message: dict) -> None:
        chat_id = message["chat"]["id"]
        document = message["document"]
        caption = message.get("caption", "").strip()

        if not caption.startswith("/upload_pack") or not document.get("file_name", "").endswith(".siq"):
            return

        file_id = document["file_id"]
        try:
            file_info = await self._tg.get_file(file_id)
            if not file_info.get("ok"):
                await self._tg.send_message(chat_id, "Ошибка получения файла от Telegram.")
                return

            file_path = file_info["result"]["file_path"]
            os.makedirs("data/uploads", exist_ok=True)
            local_path = os.path.abspath(f"data/uploads/{file_id}.siq")

            await self._tg.send_message(chat_id, f"Скачиваю пакет...")
            await self._tg.download_file(file_path, local_path)

            await self._rabbit.publish("siq_parse_tasks", {"file_path": local_path})
            await self._tg.send_message(chat_id, "Пакет успешно загружен и отправлен на обработку!")
        except Exception as e:
            await self._tg.send_message(chat_id, f"Ошибка при загрузке: {e}")
