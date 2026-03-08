"""HTTP-клиент Telegram Bot API (aiohttp)."""

from __future__ import annotations

import json
from typing import Any

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
            with open(destination, "wb") as f:
                async for chunk in resp.content.iter_chunked(8192):
                    f.write(chunk)

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
            return await resp.json()
