from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from src.infrastructure.database.models import ThemeModel


class ThemeRepository:
    """Работа с темами и табло через Postgres."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_themes_by_round(self, round_id: int) -> list[dict]:
        async with self._session_factory() as session:
            stmt = (
                select(ThemeModel.id, ThemeModel.name)
                .where(ThemeModel.round_id == round_id)
                .order_by(ThemeModel.order_index)
            )
            result = await session.execute(stmt)
            return [{"id": row[0], "name": row[1]} for row in result.all()]

    async def get_board_for_round(self, round_id: int) -> list[dict]:
        """Получает структуру табло для раунда (темы и вопросы).

        Returns:
            list[dict]: [{'theme': 'Имя', 'questions': [{'id': 1, 'value': 100}, ...]}]
        """
        async with self._session_factory() as session:
            stmt = (
                select(ThemeModel)
                .options(selectinload(ThemeModel.questions))
                .where(ThemeModel.round_id == round_id)
                .order_by(ThemeModel.order_index)
            )
            result = await session.execute(stmt)
            themes = result.scalars().all()

            board = []
            for t in themes:
                sorted_qs = sorted(t.questions, key=lambda q: q.order_index)
                qs = [{"id": q.id, "value": q.value} for q in sorted_qs]
                board.append({"theme": t.name, "questions": qs})
            return board
