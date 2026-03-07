"""Use Case: Нажатие кнопки (гонка на реакцию).

Основной сценарий «Своей Игры» — атомарная гонка
за право ответить первым.
"""

from __future__ import annotations

from src.domain.errors import (
    InvalidTransitionError,
    PlayerBlockedError,
    PlayerNotFoundError,
)
from src.infrastructure.redis_repo import RedisStateRepository


class PressButtonResult:
    """Результат попытки нажать кнопку."""

    def __init__(
        self,
        *,
        captured: bool,
        player_id: str,
        error: str | None = None,
    ) -> None:
        self.captured = captured
        self.player_id = player_id
        self.error = error


class PressButtonUseCase:
    """Сценарий нажатия кнопки «Ответить».

    Оркестрация:
    1. Атомарно пытаемся захватить кнопку (Redis SETNX).
    2. Если захватили — загружаем Room, вызываем room.press_button().
    3. Сохраняем обновлённое состояние.
    """

    def __init__(self, state_repo: RedisStateRepository) -> None:
        self._state_repo = state_repo

    async def execute(self, room_id: str, player_id: str) -> PressButtonResult:
        """Попытка нажать кнопку.

        Returns:
            PressButtonResult с результатом гонки.
        """
        # Шаг 1: атомарная гонка (Redis SETNX)
        captured = await self._state_repo.try_capture_button(
            room_id, player_id,
        )

        if not captured:
            return PressButtonResult(
                captured=False,
                player_id=player_id,
                error="Кнопку уже нажал другой игрок",
            )

        # Шаг 2: загрузить комнату и перевести FSM
        room = await self._state_repo.get_room(room_id)
        if room is None:
            return PressButtonResult(
                captured=False,
                player_id=player_id,
                error="Комната не найдена",
            )

        try:
            room.press_button(player_id)
        except (
            InvalidTransitionError,
            PlayerBlockedError,
            PlayerNotFoundError,
        ) as exc:
            # Откат: освобождаем кнопку
            await self._state_repo.release_button(room_id)
            return PressButtonResult(
                captured=False,
                player_id=player_id,
                error=exc.message,
            )

        # Шаг 3: сохранить обновлённое состояние
        await self._state_repo.save_room(room)

        return PressButtonResult(captured=True, player_id=player_id)
