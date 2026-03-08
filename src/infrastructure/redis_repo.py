"""Реализация RedisStateRepository поверх Redis.

Микро-состояния FSM (LOBBY, ANSWERING и т.д.) живут здесь.
В Postgres пишется только старт матча и итоговые результаты.

Требует установки пакета ``redis``: pip install redis.
"""

from __future__ import annotations

import json
from typing import Any

from src.domain.player import Player
from src.domain.question import Question, QuestionType
from src.domain.room import Phase, Room


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
        return self._deserialize(json.loads(raw))

    async def save_room(self, room: Room) -> None:
        data = self._serialize(room)
        await self._redis.set(
            self._key(room.room_id), json.dumps(data, ensure_ascii=False)
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

    # ── Ключ Redis ─────────────────────────────────

    def _key(self, room_id: str) -> str:
        return f"{self._KEY_PREFIX}{room_id}"

    # ── Сериализация Room → dict ───────────────────

    @staticmethod
    def _serialize(room: Room) -> dict:
        return {
            "room_id": room.room_id,
            "chat_id": room.chat_id,
            "phase": room.phase.value,
            "package_id": room.package_id,
            "current_round_id": room.current_round_id,
            "closed_questions": room.closed_questions,
            "answering_player_id": room.answering_player_id,
            "paused_from": room.paused_from.value if room.paused_from else None,
            "current_question": (
                {
                    "question_id": room.current_question.question_id,
                    "theme_name": room.current_question.theme_name,
                    "text": room.current_question.text,
                    "answer": room.current_question.answer,
                    "value": room.current_question.value,
                    "question_type": room.current_question.question_type.value,
                }
                if room.current_question
                else None
            ),
            "final_question": (
                {
                    "question_id": room.final_question.question_id,
                    "theme_name": room.final_question.theme_name,
                    "text": room.final_question.text,
                    "answer": room.final_question.answer,
                    "value": room.final_question.value,
                    "question_type": room.final_question.question_type.value,
                }
                if room.final_question
                else None
            ),
            "final_stakes": room.final_stakes,
            "final_answers": room.final_answers,
            "players": {
                pid: {
                    "player_id": p.player_id,
                    "telegram_id": p.telegram_id,
                    "username": p.username,
                    "first_name": p.first_name,
                    "score": p.score,
                    "is_ready": p.is_ready,
                    "is_blocked_this_question": p.is_blocked_this_question,
                }
                for pid, p in room.players.items()
            },
        }

    # ── Десериализация dict → Room ──────────────────

    @staticmethod
    def _deserialize(data: dict) -> Room:
        players: dict[str, Player] = {}
        for pid, pdata in data.get("players", {}).items():
            players[pid] = Player(
                player_id=pdata["player_id"],
                telegram_id=pdata["telegram_id"],
                username=pdata["username"],
                first_name=pdata.get("first_name", ""),
                score=pdata.get("score", 0),
                is_ready=pdata.get("is_ready", False),
                is_blocked_this_question=pdata.get(
                    "is_blocked_this_question", False
                ),
            )

        current_question = RedisStateRepository._deserialize_question(
            data.get("current_question"),
        )
        final_question = RedisStateRepository._deserialize_question(
            data.get("final_question"),
        )

        paused_value = data.get("paused_from")

        room = Room(
            room_id=data["room_id"],
            chat_id=data["chat_id"],
            phase=Phase(data.get("phase", "lobby")),
            players=players,
            package_id=data.get("package_id"),
            current_round_id=data.get("current_round_id"),
            closed_questions=data.get("closed_questions", []),
            current_question=current_question,
            answering_player_id=data.get("answering_player_id"),
            final_question=final_question,
            final_stakes=data.get("final_stakes", {}),
            final_answers=data.get("final_answers", {}),
        )
        room.paused_from = Phase(paused_value) if paused_value else None
        return room

    @staticmethod
    def _deserialize_question(q_data: dict | None) -> Question | None:
        if q_data is None:
            return None
        return Question(
            question_id=q_data.get("question_id"),
            theme_name=q_data["theme_name"],
            text=q_data["text"],
            answer=q_data["answer"],
            value=q_data.get("value", 100),
            question_type=QuestionType(q_data.get("question_type", "normal")),
        )
