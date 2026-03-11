import asyncio
import os

from src.application.game_process import PauseGameUseCase, UnpauseGameUseCase
from src.bot.router import command, document
from src.infrastructure.rabbit import RabbitMQPublisher
from src.shared.interfaces import MessageGateway


class AdminHandler:
    """Обработчик административных команд (пауза, загрузка пакетов)."""

    def __init__(
        self,
        tg_client: MessageGateway,
        pause_uc: PauseGameUseCase,
        unpause_uc: UnpauseGameUseCase,
        rabbit_publisher: RabbitMQPublisher,
    ) -> None:
        self._tg = tg_client
        self._pause = pause_uc
        self._unpause = unpause_uc
        self._rabbit = rabbit_publisher

    @command("/pause")
    async def handle_pause(self, chat_id: int, room_id: str, player_id: str) -> None:
        try:
            await self._pause.execute(room_id, player_id)
            await self._tg.send_message(chat_id, "⏸ Игра поставлена на паузу.")
        except Exception as e:
            await self._tg.send_message(chat_id, f"Ошибка: {e}")

    @command("/unpause")
    async def handle_unpause(self, chat_id: int, room_id: str, player_id: str) -> None:
        try:
            phase_name = await self._unpause.execute(room_id, player_id)
            await self._tg.send_message(chat_id, f"▶️ Снята с паузы. Возврат в: {phase_name}")
        except Exception as e:
            await self._tg.send_message(chat_id, f"Ошибка: {e}")

    @document()
    async def handle_document(self, chat_id: int, message: dict) -> None:
        doc = message["document"]
        caption = message.get("caption", "").strip()

        if not caption.startswith("/upload_pack") or not doc.get("file_name", "").endswith(".siq"):
            return

        file_id = doc["file_id"]
        try:
            file_info = await self._tg.get_file(file_id)
            if not file_info.get("ok"):
                await self._tg.send_message(chat_id, "Ошибка получения файла от Telegram.")
                return

            file_path = file_info["result"]["file_path"]

            # todo: anyio
            # Создаём директорию асинхронно
            await asyncio.to_thread(os.makedirs, "data/uploads", exist_ok=True)

            # Защита от path traversal
            base_dir = os.path.abspath("data/uploads")
            local_path = os.path.abspath(os.path.join(base_dir, f"{file_id}.siq"))
            if not local_path.startswith(base_dir):
                await self._tg.send_message(chat_id, "Недопустимое имя файла.")
                return

            await self._tg.send_message(chat_id, "Скачиваю пакет...")
            await self._tg.download_file(file_path, local_path)

            await self._rabbit.publish("siq_parse_tasks", {"file_path": local_path})
            await self._tg.send_message(chat_id, "Пакет успешно загружен и отправлен на обработку!")
        except Exception as e:
            await self._tg.send_message(chat_id, f"Ошибка при загрузке: {e}")
