import asyncio
import json
import logging
import os
from typing import Dict, List, Set

import aio_pika
import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from src.shared.config import AppSettings
from src.shared.domain_events import ButtonClickEvent, CommandEvent, TextEvent
from src.shared.logger import get_logger
from src.shared.messages import WebUIUpdate
from src.infrastructure.redis_repo import RedisStateRepository

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
            if websocket in self.active_connections[room_id]:
                self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
        logger.info("🔌 Отключение в комнате %s", room_id)

    async def broadcast(self, room_id: str, message: dict):
        """Отправить сообщение всем участникам комнаты."""
        if room_id in self.active_connections:
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
redis_client = None
state_repo = None

@app.on_event("startup")
async def startup_event():
    global rabbit_connection, rabbit_channel, redis_client, state_repo
    logger.info("🚀 Запуск API Gateway...")
    
    try:
        # RabbitMQ
        rabbit_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        rabbit_channel = await rabbit_connection.channel()
        
        # Redis
        redis_client = aioredis.from_url(settings.redis_url)
        state_repo = RedisStateRepository(redis_client)
        
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
        logger.info("✅ Подключено к RabbitMQ и Redis")
        
    except Exception as e:
        logger.error("❌ Ошибка подключения: %s", e)

@app.on_event("shutdown")
async def shutdown_event():
    if rabbit_connection:
        await rabbit_connection.close()
    if redis_client:
        await redis_client.close()
    logger.info("👋 API Gateway остановлен.")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/rooms")
async def list_rooms():
    """Получить список всех активных комнат."""
    if not state_repo:
        return []
    rooms = await state_repo.get_all_rooms()
    return [
        {
            "room_id": r.room_id,
            "chat_id": r.chat_id,
            "phase": r.phase,
            "player_count": len(r.players),
            "current_round": r.round_number
        }
        for r in rooms
    ]

@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
    await manager.connect(websocket, room_id)
    
    # Автоматически отправляем событие /join в ядро
    if state_repo and rabbit_channel:
        try:
            room = await state_repo.get_room(room_id)
            if room:
                join_event = CommandEvent(
                    source="web",
                    chat_id=room.chat_id,
                    room_id=room_id,
                    player_id=player_id,
                    username=player_id,
                    command="/join",
                    args=""
                )
                await rabbit_channel.default_exchange.publish(
                    aio_pika.Message(body=join_event.model_dump_json().encode()),
                    routing_key="tg_updates",
                )
                logger.info("📢 Отправлено событие /join для %s", player_id)
        except Exception as e:
            logger.error("❌ Ошибка при отправке /join: %s", e)

    try:
        while True:
            data = await websocket.receive_json()
            logger.info("📥 Сообщение от веб-клиента %s: %s", player_id, data)
            
            event = None
            if data.get("type") == "buzzer_press":
                room = await state_repo.get_room(room_id)
                chat_id = room.chat_id if room else 0
                event = ButtonClickEvent(
                    source="web",
                    chat_id=chat_id,
                    room_id=room_id,
                    player_id=player_id,
                    username=data.get("username", "Web Player"),
                    callback_id=f"web_buzzer_{room_id}",
                    data=f"btn:{chat_id}",
                    message_id=0
                )
            elif data.get("type") == "select_question":
                q_id = data.get("question_id")
                event = ButtonClickEvent(
                    source="web",
                    chat_id=0,
                    room_id=room_id,
                    player_id=player_id,
                    username=data.get("username", "Web Player"),
                    callback_id=f"web_select_{room_id}",
                    data=f"sq:{room_id}:{q_id}", # Формат SelectQuestionCallback
                    message_id=0
                )
            elif data.get("type") == "submit_answer":
                text = data.get("text", "")
                event = TextEvent(
                    source="web",
                    chat_id=0, # Will be filled from room state later if needed, but TextEvent is handled by EventRouter
                    room_id=room_id,
                    player_id=player_id,
                    username=data.get("username", player_id),
                    text=text,
                    is_private=True
                )
            elif data.get("type") == "command":
                cmd = data.get("command")
                room = await state_repo.get_room(room_id)
                if room:
                    event = CommandEvent(
                        source="web",
                        chat_id=room.chat_id,
                        room_id=room_id,
                        player_id=player_id,
                        username=data.get("username", player_id),
                        command=cmd,
                        args=data.get("args", "")
                    )
            
            if event and rabbit_channel:
                await rabbit_channel.default_exchange.publish(
                    aio_pika.Message(body=event.model_dump_json().encode()),
                    routing_key="tg_updates",
                )
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
    except Exception as e:
        logger.error("❌ Ошибка WebSocket: %s", e)
        manager.disconnect(websocket, room_id)

# Раздача статики (всегда в конце, чтобы не мешать API/WS)
static_path = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_path):
    os.makedirs(static_path, exist_ok=True)

app.mount("/", StaticFiles(directory=static_path, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.apps.proxy.main:app", host="0.0.0.0", port=8000, reload=True)
