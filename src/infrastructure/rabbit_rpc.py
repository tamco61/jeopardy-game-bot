import asyncio
import json
import uuid
from typing import Any, Dict, Optional

import aio_pika
from src.shared.interfaces import MessageGateway
from src.shared.messages import OutgoingTelegramCommand

class RabbitMQMessageGateway(MessageGateway):
    """Реализация MessageGateway через RPC поверх RabbitMQ."""

    def __init__(self, rabbitmq_url: str):
        self._url = rabbitmq_url
        self._connection: Optional[aio_pika.Connection] = None
        self._channel: Optional[aio_pika.Channel] = None
        self._callback_queue: Optional[aio_pika.Queue] = None
        self._futures: Dict[str, asyncio.Future] = {}

    async def connect(self):
        """Установить соединение и запустить consumer для RPC-ответов."""
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        
        # Эксклюзивная очередь для ответов на RPC вызовы
        self._callback_queue = await self._channel.declare_queue(
            exclusive=True, auto_delete=True
        )
        
        # Запуск консьюмера для получения ответов
        await self._callback_queue.consume(self._on_response, no_ack=True)

    async def disconnect(self):
        """Закрыть соединения."""
        if self._channel:
            await self._channel.close()
        if self._connection:
            await self._connection.close()

    async def _on_response(self, message: aio_pika.IncomingMessage):
        """Callback для обработки ответов от Worker-а."""
        if message.correlation_id in self._futures:
            future = self._futures[message.correlation_id]
            if not future.done():
                try:
                    body = json.loads(message.body.decode())
                    future.set_result(body)
                except Exception as e:
                    future.set_exception(e)

    async def _call(self, method: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Отправляет RPC-запрос и ждёт ответа."""
        if not self._channel or not self._callback_queue:
            raise RuntimeError("Gateway is not connected")

        corr_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._futures[corr_id] = future

        cmd = OutgoingTelegramCommand(
            method=method,
            kwargs=kwargs,
            reply_to=self._callback_queue.name,
            correlation_id=corr_id
        )

        await self._channel.default_exchange.publish(
            aio_pika.Message(
                body=cmd.model_dump_json().encode(),
                correlation_id=corr_id,
                reply_to=self._callback_queue.name,
            ),
            routing_key="tg_commands",
        )

        try:
            # Ждём ответ (можно добавить таймаут asyncio.wait_for)
            return await future
        finally:
            self._futures.pop(corr_id, None)

    # --- MessageGateway Protocol Implementation ---

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await self._call("send_message", kwargs={
            "chat_id": chat_id, "text": text, "reply_markup": reply_markup
        })

    async def send_media(
            self,
            chat_id: int | str,
            media_type: str,
            media: str,  # Сюда прилетит наш telegram_file_id
            caption: Optional[str] = None,
            reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Отправить RPC-запрос на публикацию медиафайла."""
        return await self._call("send_media", kwargs={
            "chat_id": chat_id,
            "media_type": media_type,
            "media": media,
            "caption": caption,
            "reply_markup": reply_markup
        })

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await self._call("edit_message_text", kwargs={
            "chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup
        })

    async def edit_message_caption(
            self,
            chat_id: int,
            message_id: int,
            caption: str,
            reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Редактировать подпись к медиафайлу."""
        return await self._call("edit_message_caption", kwargs={
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": caption,
            "reply_markup": reply_markup
        })

    async def edit_message_reply_markup(
            self,
            chat_id: int,
            message_id: int,
            reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Редактировать ТОЛЬКО клавиатуру (подходит и для текста, и для медиа)."""
        return await self._call("edit_message_reply_markup", kwargs={
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": reply_markup
        })

    async def answer_callback_query(
        self, callback_query_id: str, text: str = "", show_alert: bool = False
    ) -> Dict[str, Any]:
        return await self._call("answer_callback_query", kwargs={
            "callback_query_id": callback_query_id, "text": text, "show_alert": show_alert
        })

    async def get_file(self, file_id: str) -> Dict[str, Any]:
        return await self._call("get_file", kwargs={"file_id": file_id})

    async def download_file(self, file_path: str, destination: str) -> None:
        await self._call("download_file", kwargs={"file_path": file_path, "destination": destination})

    async def delete_message(self, chat_id: int, message_id: int) -> Dict[str, Any]:
        return await self._call("delete_message", kwargs={"chat_id": chat_id, "message_id": message_id})
