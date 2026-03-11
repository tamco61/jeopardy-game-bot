from typing import Any, Dict, Optional, Protocol

class MessageGateway(Protocol):
    """Шлюз для отправки сообщений в Telegram (через HTTP или RPC)."""

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
        show_alert: bool = False,
    ) -> Dict[str, Any]:
        ...

    async def get_file(self, file_id: str) -> Dict[str, Any]:
        ...

    async def download_file(self, file_path: str, destination: str) -> None:
        ...
