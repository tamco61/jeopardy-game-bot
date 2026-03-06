"""Порт для работы с игровым состоянием (Redis).

Микро-состояния FSM (LOBBY, ANSWERING и т.д.) живут в Redis.
В Postgres пишется только старт матча и итоговые результаты.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.room import Room


class IStateRepository(ABC):
    """Абстракция хранилища мгновенного состояния комнат (Redis)."""

    @abstractmethod
    async def get_room(self, room_id: str) -> Room | None:
        """Получить комнату по ID."""
        ...

    @abstractmethod
    async def save_room(self, room: Room) -> None:
        """Сохранить / обновить состояние комнаты."""
        ...

    @abstractmethod
    async def delete_room(self, room_id: str) -> None:
        """Удалить комнату (конец игры)."""
        ...

    @abstractmethod
    async def try_capture_button(self, room_id: str, player_id: str) -> bool:
        """Атомарная гонка: попытка захватить кнопку.

        Реализация должна использовать Redis SETNX (SET ... NX)
        для гарантии, что только один игрок выиграет гонку.

        Args:
            room_id: ID комнаты.
            player_id: ID игрока, нажавшего кнопку.

        Returns:
            True — игрок первый (захватил лок), False — опоздал.
        """
        ...

    @abstractmethod
    async def release_button(self, room_id: str) -> None:
        """Снять лок кнопки (для нового вопроса)."""
        ...
