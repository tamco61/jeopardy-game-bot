import asyncio
import json
import logging
from typing import Dict, List, Set

import aio_pika
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from src.shared.config import AppSettings
from src.shared.domain_events import ButtonClickEvent
from src.shared.logger import get_logger
from src.shared.messages import WebUIUpdate

logger = get_logger(__name__)

class ConnectionManager:
    """Управление активными WebSocket-соединениями."""
    def __init__(self):
        # room_id -> list of websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)
        logger.info("📡 Новое соединение в комнате %s. Всего: %d", room_id, len(self.active_connections[room_id]))

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
        logger.info("🔌 Отключение в комнате %s", room_id)

    async def broadcast(self, room_id: str, message: dict):
        """Отправить сообщение всем участникам комнаты."""
        if room_id in self.active_connections:
            # Делаем копию списка, чтобы избежать ошибок при отключении во время итерации
            targets = list(self.active_connections[room_id])
            for connection in targets:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error("❌ Ошибка отправки в WS: %s", e)

manager = ConnectionManager()
app = FastAPI(title="Jeopardy API Gateway (Proxy)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = AppSettings()
rabbit_connection = None
rabbit_channel = None

@app.on_event("startup")
async def startup_event():
    global rabbit_connection, rabbit_channel
    logger.info("🚀 Запуск API Gateway...")
    
    try:
        rabbit_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        rabbit_channel = await rabbit_connection.channel()
        
        # Очередь для получения обновлений UI от Core
        queue = await rabbit_channel.declare_queue("ui_updates", auto_delete=False)
        
        async def process_ui_update(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    update = WebUIUpdate.model_validate_json(message.body)
                    logger.debug("📤 Трансляция обновления %s в комнату %s", update.event_type, update.room_id)
                    await manager.broadcast(update.room_id, update.model_dump())
                except ValidationError as e:
                    logger.error("❌ Неверный формат WebUIUpdate: %s", e)
                except Exception as e:
                    logger.exception("❌ Ошибка при трансляции обновления: %s", e)

        await queue.consume(process_ui_update)
        logger.info("✅ Подключено к RabbitMQ (ui_updates)")
        
    except Exception as e:
        logger.error("❌ Ошибка подключения к RabbitMQ: %s", e)

@app.on_event("shutdown")
async def shutdown_event():
    if rabbit_connection:
        await rabbit_connection.close()
    logger.info("👋 API Gateway остановлен.")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
    await manager.connect(websocket, room_id)
    try:
        while True:
            # Ожидаем действия от веб-клиента (например, нажатие кнопки)
            data = await websocket.receive_json()
            logger.info("📥 Сообщение от веб-клиента %s: %s", player_id, data)
            
            # Если это нажатие кнопки (buzzer)
            if data.get("type") == "buzzer_press":
                # Создаем доменное событие
                event = ButtonClickEvent(
                    source="web",
                    chat_id=0, # Для веба нет chat_id в смысле телеграма
                    room_id=room_id,
                    player_id=player_id,
                    username=data.get("username", "Web Player"),
                    callback_id=f"web_{room_id}_{player_id}",
                    data="press_button", # Соответствует логике в ядре
                    message_id=0
                )
                
                # Публикуем в основную очередь входящих событий
                if rabbit_channel:
                    await rabbit_channel.default_exchange.publish(
                        aio_pika.Message(body=event.model_dump_json().encode()),
                        routing_key="tg_updates", # Core слушает эту очередь
                    )
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
    except Exception as e:
        logger.error("❌ Ошибка WebSocket: %s", e)
        manager.disconnect(websocket, room_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
