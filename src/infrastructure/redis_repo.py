"""Реализация RedisStateRepository поверх Redis.

Микро-состояния FSM (LOBBY, ANSWERING и т.д.) живут здесь.
"""

from __future__ import annotations

from typing import Any

from src.domain.room import Room


class RedisStateRepository:
    """Хранение игрового состояния комнат в Redis (JSON-сериализация)."""

    _KEY_PREFIX = "room:"
    _BUTTON_PREFIX = "button_lock:"

    def __init__(self, redis_client: Any) -> None:
        """Args: redis_client — экземпляр ``redis.asyncio.Redis``."""
        self._redis = redis_client

    # ── CRUD ────────────────────────────────────────

    async def get_room(self, room_id: str) -> Room | None:
        raw: bytes | None = await self._redis.get(self._key(room_id))
        if raw is None:
            return None
        return Room.model_validate_json(raw)

    async def save_room(self, room: Room) -> None:
        data_json = room.model_dump_json()
        await self._redis.set(
            self._key(room.room_id), data_json, ex=86400  # 24 ч
        )

    async def delete_room(self, room_id: str) -> None:
        await self._redis.delete(self._key(room_id))

    # ── Атомарная гонка (кнопка) ───────────────────

    async def try_capture_button(self, room_id: str, player_id: str) -> bool:
        """Redis SETNX: только первый вызов вернёт True."""
        key = f"{self._BUTTON_PREFIX}{room_id}"
        return bool(await self._redis.set(key, player_id, nx=True, ex=30))

    async def release_button(self, room_id: str) -> None:
        """Удалить лок кнопки (для нового вопроса или отката)."""
        await self._redis.delete(f"{self._BUTTON_PREFIX}{room_id}")

    async def set_active_room(self, user_telegram_id: int, room_id: str) -> None:
        """Запомнить, в какой комнате сейчас 'активен' пользователь."""
        key = f"active_room:{user_telegram_id}"
        await self._redis.set(key, room_id, ex=3600)  # 1 час таймаут

    async def get_active_room(self, user_telegram_id: int) -> str | None:
        """Получить ID текущей комнаты пользователя."""
        key = f"active_room:{user_telegram_id}"
        val = await self._redis.get(key)
        return val.decode() if val else None

    async def save_last_results(self, chat_id: int, results_text: str) -> None:
        """Сохранить финальный счет последней игры в чате."""
        key = f"last_results:{chat_id}"
        await self._redis.set(key, results_text, ex=604800)  # Храним неделю

    async def get_last_results(self, chat_id: int) -> str | None:
        """Получить результаты последней игры в чате."""
        key = f"last_results:{chat_id}"
        val = await self._redis.get(key)
        return val.decode() if val else None

    async def get_all_rooms(self) -> list[Room]:
        """Получить все активные комнаты (для восстановления таймеров при старте)."""
        keys = await self._redis.keys(f"{self._KEY_PREFIX}*")
        rooms = []
        for key in keys:
            raw = await self._redis.get(key)
            if raw:
                rooms.append(Room.model_validate_json(raw))
        return rooms

    # ── Ключ Redis ─────────────────────────────────

    def _key(self, room_id: str) -> str:
        return f"{self._KEY_PREFIX}{room_id}"
