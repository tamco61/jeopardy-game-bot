"""DTO для WebSocket-сообщений (фронтенд ↔ бэкенд)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class WSEventType(StrEnum):
    """Типы событий WebSocket."""

    # Клиент → Сервер
    JOIN_ROOM = "join_room"
    PRESS_BUTTON = "press_button"
    SUBMIT_ANSWER = "submit_answer"

    # Сервер → Клиент
    ROOM_STATE = "room_state"
    BUTTON_PRESSED = "button_pressed"
    ANSWER_RESULT = "answer_result"
    ROUND_STARTED = "round_started"
    TIMER_TICK = "timer_tick"
    ERROR = "error"


class WebSocketMessageDTO(BaseModel):
    """Единый формат WebSocket-сообщения."""

    event: WSEventType
    room_id: str | None = None
    payload: dict = {}
