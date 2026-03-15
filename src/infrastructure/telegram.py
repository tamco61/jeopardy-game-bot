"""HTTP-клиент Telegram Bot API (aiohttp)."""

from __future__ import annotations

import json
from typing import Any

import anyio
from aiohttp import ClientSession


class TelegramHttpClient:
    """Тонкая обёртка над aiohttp для вызовов Telegram Bot API."""

    def __init__(self, bot_token: str) -> None:
        self._bot_token = bot_token
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._session: ClientSession | None = None

    # ── Жизненный цикл сессии ───────────────────────

    async def start(self) -> None:
        """Открыть HTTP-сессию."""
        if self._session is None or self._session.closed:
            self._session = ClientSession()

    async def close(self) -> None:
        """Закрыть HTTP-сессию."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Telegram API методы ─────────────────────────

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> dict:
        """Отправить сообщение в чат."""
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        return await self._post("sendMessage", payload)

    async def edit_message_caption(
            self,
            chat_id: int,
            message_id: int,
            caption: str,
            reply_markup: dict | None = None,
    ) -> dict:
        """Отредактировать подпись (caption) существующего медиа-сообщения."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": caption,
        }
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        return await self._post("editMessageCaption", payload)

    async def edit_message_reply_markup(
            self,
            chat_id: int,
            message_id: int,
            reply_markup: dict | None = None,
    ) -> dict:
        """Изменить только кнопки (reply_markup) сообщения (работает и для текста, и для медиа)."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        return await self._post("editMessageReplyMarkup", payload)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> dict:
        """Отредактировать текст существующего сообщения."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        return await self._post("editMessageText", payload)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
        show_alert: bool = False,
    ) -> dict:
        """Ответить на callback_query (убирает «часики» на кнопке)."""
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
        }
        return await self._post("answerCallbackQuery", payload)

    async def get_updates(
        self,
        offset: int | None = None,
        timeout: int = 30,
    ) -> dict:
        """Получить обновления через long polling."""
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": json.dumps(["message", "callback_query"]),
        }
        if offset is not None:
            payload["offset"] = offset
        return await self._post("getUpdates", payload)

    async def delete_webhook(self) -> dict:
        """Удалить webhook (нужно перед запуском long polling)."""
        return await self._post("deleteWebhook", {})

    async def set_my_commands(self, commands: list[dict]) -> dict:
        """Зарегистрировать меню команд бота."""
        return await self._post(
            "setMyCommands", {"commands": json.dumps(commands)}
        )

    async def delete_message(self, chat_id: int, message_id: int) -> dict:
        """Удалить сообщение из чата."""
        return await self._post(
            "deleteMessage", {"chat_id": chat_id, "message_id": message_id}
        )

    async def get_file(self, file_id: str) -> dict:
        """Получить информацию о файле."""
        return await self._post("getFile", {"file_id": file_id})

    async def download_file(self, file_path: str, destination: str) -> None:
        """Скачать файл."""
        if self._session is None or self._session.closed:
            raise RuntimeError("HTTP-сессия не открыта. Вызовите start().")

        url = f"https://api.telegram.org/file/bot{self._bot_token}/{file_path}"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            async with await anyio.open_file(destination, "wb") as f:
                async for chunk in resp.content.iter_chunked(8192):
                    await f.write(chunk)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def get_file_stream(self, file_id: str):
        """
        Предоставляет асинхронный поток данных файла из Telegram.
        Сначала получает file_path через getFile, затем возвращает ответ от скачивания.
        """
        if self._session is None or self._session.closed:
            raise RuntimeError("HTTP-сессия не открыта. Вызовите start().")

        # 1. Получаем путь к файлу
        file_info = await self.get_file(file_id)
        if not file_info.get("ok"):
            raise ValueError(f"Telegram error: {file_info.get('description', 'Unknown error')}")

        file_path = file_info["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{self._bot_token}/{file_path}"

        # 2. Делаем запрос на скачивание (без вычитки в память)
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            yield resp

    async def send_media(
            self,
            chat_id: int | str,
            media_type: str,
            media: str | bytes,
            filename: str | None = None,
            caption: str | None = None,
            reply_markup: dict | None = None,
    ) -> dict:
        """Отправить медиафайл в чат."""
        import logging
        logger = logging.getLogger(__name__)

        if self._session is None or self._session.closed:
            raise RuntimeError("HTTP-сессия не открыта. Вызовите start().")

        method_name = f"send{media_type.capitalize()}"
        url = f"{self._base_url}/{method_name}"

        logger.info(
            f"🚀 Подготовка send_media: type={media_type}, method={method_name}, is_str={isinstance(media, str)}")

        # 1. СЦЕНАРИЙ: Отправка по file_id (мгновенная)
        if isinstance(media, str):
            payload = {"chat_id": chat_id, media_type: media}

            if caption:
                payload["caption"] = caption

            if reply_markup:
                # Если уже строка - оставляем, если словарь - дампим
                import json
                payload["reply_markup"] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup

            logger.info(f"📡 Отправляем JSON-запрос на {url} с payload: {payload}")

            try:
                # ВОТ ЗДЕСЬ ОБЯЗАТЕЛЬНО ДОЛЖЕН БЫТЬ RETURN!
                async with self._session.post(url, json=payload) as resp:
                    result = await resp.json()
                    logger.info(f"✅ Ответ от Telegram API: {result}")
                    return result
            except Exception as e:
                logger.error(f"❌ Ошибка aiohttp при отправке file_id: {e}")
                return {"ok": False, "error": str(e)}

        # 2. СЦЕНАРИЙ: Загрузка нового файла (байты)
        from aiohttp import FormData
        logger.info("📦 Загрузка физического файла (байт)...")

        data = FormData()
        data.add_field("chat_id", str(chat_id))

        safe_filename = filename or f"file.{media_type}"
        data.add_field(media_type, media, filename=safe_filename)

        if caption:
            data.add_field("caption", caption)
        if reply_markup:
            import json
            data.add_field("reply_markup", json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup)

        try:
            async with self._session.post(url, data=data) as resp:
                result = await resp.json()
                logger.info(f"✅ Ответ от Telegram API (загрузка): {result}")
                return result
        except Exception as e:
            logger.error(f"❌ Ошибка aiohttp при загрузке файла: {e}")
            return {"ok": False, "error": str(e)}
    # ── Внутренний HTTP-метод ───────────────────────

    async def _post(self, method: str, payload: dict) -> dict:
        if self._session is None or self._session.closed:
            msg = (
                "HTTP-сессия не открыта. Вызовите start() перед использованием."
            )
            raise RuntimeError(msg)
        async with self._session.post(
            f"{self._base_url}/{method}",
            data=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
