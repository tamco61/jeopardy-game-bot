from typing import Any, Protocol


class MessageGateway(Protocol):
    """Шлюз для отправки сообщений в Telegram (через HTTP или RPC)."""

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    async def send_media(
            self,
            chat_id: int | str,
            media_type: str,
            media: str,  # Сюда прилетит наш telegram_file_id
            caption: str | None = None,
            reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    async def edit_message_caption(
            self,
            chat_id: int,
            message_id: int,
            caption: str,
            reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    async def edit_message_reply_markup(
            self,
            chat_id: int,
            message_id: int,
            reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
        show_alert: bool = False,
    ) -> dict[str, Any]:
        ...

    async def get_file(self, file_id: str) -> dict[str, Any]:
        ...

    async def download_file(self, file_path: str, destination: str) -> None:
        ...

    async def delete_message(self, chat_id: int, message_id: int) -> dict[str, Any]:
        ...
