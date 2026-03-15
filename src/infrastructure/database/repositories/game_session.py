"""Репозиторий для чтения/записи игровых сессий в PostgreSQL."""

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.domain.player import Player
from src.domain.room import Phase, Room
from src.infrastructure.database.models import GamePlayerModel, GameSessionModel
from src.shared.logger import get_logger

logger = get_logger(__name__)


class GameSessionRepository:
    """CRUD для game_sessions / game_players.

    Используется Core-сервисом для:
    - создания записи при старте игры (create_session),
    - чекпоинта после каждого вердикта (update_session),
    - финализации при конце игры (mark_finished),
    - чтения незавершённых сессий при старте Core для восстановления (get_active_sessions).
    """

    def __init__(self, session_factory) -> None:
        self._factory = session_factory

    # ── Создание ────────────────────────────────────────────────────────────

    async def create_session(self, room: Room) -> int:
        """Создаёт запись в БД при старте игры. Возвращает session_id."""
        async with self._factory() as session:
            model = GameSessionModel(
                package_id=room.package_id,
                chat_id=room.chat_id,
                room_id=room.room_id,
                status="in_progress",
                phase=room.phase.value,
                host_id=room.host_id or None,
                host_telegram_id=room.host_telegram_id or None,
                current_round_id=room.current_round_id,
                current_round_name=room.current_round_name or None,
                round_number=room.round_number,
                total_rounds=room.total_rounds,
                selecting_player_id=room.selecting_player_id,
                last_board_message_id=room.last_board_message_id,
                closed_questions=json.dumps(list(room.closed_questions)),
            )
            session.add(model)
            await session.flush()  # получаем id до commit

            for player in room.players.values():
                gp = GamePlayerModel(
                    session_id=model.id,
                    player_id=player.player_id,
                    username=player.username,
                    telegram_id=player.telegram_id or None,
                    score=player.score,
                )
                session.add(gp)

            await session.commit()
            logger.info(
                "✅ Сессия создана: id=%d room_id=%s", model.id, room.room_id
            )
            return model.id

    # ── Чекпоинт ────────────────────────────────────────────────────────────

    async def update_session(self, room: Room) -> None:
        """Обновляет состояние сессии (чекпоинт после вердикта/перехода раунда)."""
        async with self._factory() as session:
            result = await session.execute(
                select(GameSessionModel)
                .where(GameSessionModel.room_id == room.room_id)
                .options(selectinload(GameSessionModel.players))
            )
            model = result.scalar_one_or_none()
            if not model:
                logger.warning(
                    "update_session: сессия не найдена для room_id=%s",
                    room.room_id,
                )
                return

            model.phase = room.phase.value
            model.current_round_id = room.current_round_id
            model.current_round_name = room.current_round_name or None
            model.round_number = room.round_number
            model.selecting_player_id = room.selecting_player_id
            model.last_board_message_id = room.last_board_message_id
            model.closed_questions = json.dumps(list(room.closed_questions))

            # Обновляем / добавляем игроков
            existing = {p.player_id: p for p in model.players}
            for player in room.players.values():
                if player.player_id in existing:
                    existing[player.player_id].score = player.score
                else:
                    gp = GamePlayerModel(
                        session_id=model.id,
                        player_id=player.player_id,
                        username=player.username,
                        telegram_id=player.telegram_id or None,
                        score=player.score,
                    )
                    session.add(gp)

            await session.commit()
            logger.debug("💾 Чекпоинт сохранён: room_id=%s", room.room_id)

    # ── Финализация ─────────────────────────────────────────────────────────

    async def mark_finished(self, room: Room) -> None:
        """Помечает сессию как завершённую и фиксирует итоговые очки."""
        async with self._factory() as session:
            result = await session.execute(
                select(GameSessionModel)
                .where(GameSessionModel.room_id == room.room_id)
                .options(selectinload(GameSessionModel.players))
            )
            model = result.scalar_one_or_none()
            if not model:
                logger.warning(
                    "mark_finished: сессия не найдена для room_id=%s",
                    room.room_id,
                )
                return

            model.status = "finished"
            model.phase = room.phase.value
            model.finished_at = datetime.now(timezone.utc)

            existing = {p.player_id: p for p in model.players}
            for player in room.players.values():
                if player.player_id in existing:
                    existing[player.player_id].score = player.score
                    existing[player.player_id].final_score = player.score
                else:
                    gp = GamePlayerModel(
                        session_id=model.id,
                        player_id=player.player_id,
                        username=player.username,
                        telegram_id=player.telegram_id or None,
                        score=player.score,
                        final_score=player.score,
                    )
                    session.add(gp)

            await session.commit()
            logger.info("🏁 Сессия завершена: room_id=%s", room.room_id)

    # ── Восстановление ──────────────────────────────────────────────────────

    async def get_active_sessions(self) -> list[GameSessionModel]:
        """Возвращает все незавершённые сессии с room_id для восстановления."""
        async with self._factory() as session:
            result = await session.execute(
                select(GameSessionModel)
                .where(GameSessionModel.status == "in_progress")
                .where(GameSessionModel.room_id.isnot(None))
                .options(selectinload(GameSessionModel.players))
            )
            return list(result.scalars().all())

    async def get_all_chat_players(self, chat_id: int) -> list[str]:
        """Возвращает список уникальных имен всех ИЗВЕСТНЫХ Telegram-игроков в этом чате.
        Игроки с веб-интерфейса (telegram_id == 0) не учитываются, чтобы их ники можно было занимать снова.
        """
        async with self._factory() as session:
            result = await session.execute(
                select(GamePlayerModel.username)
                .join(GameSessionModel)
                .where(GameSessionModel.chat_id == chat_id)
                .where(GamePlayerModel.telegram_id > 0)
                .distinct()
            )
            return [row[0] for row in result.all() if row[0]]

    @staticmethod
    def rebuild_room(sess: GameSessionModel) -> Room:
        """Восстанавливает объект Room из записи в БД.

        Фаза принудительно переводится в BOARD_VIEW — безопасная точка
        восстановления (детали текущего вопроса теряются, но
        счёт и закрытые вопросы сохраняются).
        """
        closed: list[int] = json.loads(sess.closed_questions or "[]")

        players: dict[str, Player] = {}
        for gp in sess.players:
            if not gp.player_id:
                continue
            players[gp.player_id] = Player(
                player_id=gp.player_id,
                telegram_id=gp.telegram_id or 0,
                username=gp.username or gp.player_id,
                score=gp.score,
                is_ready=True,
            )

        room = Room(
            room_id=sess.room_id,
            chat_id=sess.chat_id,
            phase=Phase.BOARD_VIEW,
            host_id=sess.host_id or "",
            host_telegram_id=sess.host_telegram_id or 0,
            package_id=sess.package_id,
            current_round_id=sess.current_round_id,
            current_round_name=sess.current_round_name or "",
            round_number=sess.round_number,
            total_rounds=sess.total_rounds,
            closed_questions=closed,
            selecting_player_id=sess.selecting_player_id,
            last_board_message_id=sess.last_board_message_id,
            players=players,
        )
        return room
