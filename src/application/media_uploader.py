import asyncio
import logging
from src.application.parser.dto import PackageDTO, QuestionDTO
from src.infrastructure.telegram import TelegramHttpClient


class TelegramMediaUploader:
    """Сервис для загрузки медиафайлов пакета в скрытый чат Telegram."""

    PHOTO_SIZE_LIMIT = 10 * 1024 * 1024
    FILE_SIZE_LIMIT = 50 * 1024 * 1024

    def __init__(self, tg_client: TelegramHttpClient, storage_chat_id: str | int):
        self._tg_client = tg_client
        self._storage_chat_id = storage_chat_id
        self._log = logging.getLogger(self.__class__.__name__)

    async def upload_package_media(self, package: PackageDTO) -> PackageDTO:
        total_uploaded = 0

        for round_dto in package.rounds:
            for theme_dto in round_dto.themes:
                for question in theme_dto.questions:
                    if not question.media_bytes:
                        continue

                    file_id = await self._upload_single_media(question)
                    if file_id:
                        question.telegram_file_id = file_id
                        total_uploaded += 1

                    # Очищаем память
                    question.media_bytes = None

        return package

    async def _upload_single_media(self, question: QuestionDTO) -> str | None:
        media_bytes = question.media_bytes
        media_type = question.media_type
        filename = question.media_filename
        size_bytes = len(media_bytes)

        if media_type == "photo" and size_bytes > self.PHOTO_SIZE_LIMIT:
            return None
        elif media_type in ["video", "audio"] and size_bytes > self.FILE_SIZE_LIMIT:
            return None

        max_retries = 3
        for _ in range(max_retries):
            result = await self._tg_client.send_media(
                chat_id=self._storage_chat_id,
                media_type=media_type,
                media=media_bytes,
                filename=filename
            )

            if result.get("ok"):
                await asyncio.sleep(3.2)  # Защита от спам-блока (20 сообщений в минуту)
                return self._extract_file_id(result, media_type)

            elif result.get("error_code") == 429:
                retry_after = result.get("parameters", {}).get("retry_after", 5)
                self._log.warning(f"Flood limit! Ждем {retry_after} сек...")
                await asyncio.sleep(retry_after)
                continue
            else:
                self._log.error(f"Ошибка Telegram API: {result}")
                return None

        return None

    def _extract_file_id(self, tg_response: dict, media_type: str) -> str | None:
        try:
            msg = tg_response.get("result", {})

            # 1. Если Telegram честно вернул массив фото
            if "photo" in msg:
                return msg["photo"][-1]["file_id"]

            # 2. Если Telegram переделал .webp в документ
            if "document" in msg:
                return msg["document"]["file_id"]

            # 3. Если Telegram переделал .webp в стикер
            if "sticker" in msg:
                return msg["sticker"]["file_id"]

            # 4. Для видео, аудио и голосовых
            if media_type in msg:
                return msg[media_type]["file_id"]

            # Если Telegram прислал что-то вообще неожиданное
            self._log.error(f"Неизвестный формат ответа Telegram. Не могу найти file_id: {tg_response}")
            return None

        except Exception as e:
            self._log.error(f"Ошибка при извлечении file_id: {e}. Ответ Telegram: {tg_response}")
            return None