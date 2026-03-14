from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database.models import RoundModel


class RoundRepository:
    """Работа с раундами игры через Postgres."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_rounds_by_package(self, package_id: int) -> list[dict]:
        async with self._session_factory() as session:
            stmt = (
                select(RoundModel.id, RoundModel.name, RoundModel.is_final)
                .where(RoundModel.package_id == package_id)
                .order_by(RoundModel.order_index)
            )
            result = await session.execute(stmt)
            return [
                {"id": row[0], "name": row[1], "is_final": row[2]}
                for row in result.all()
            ]

    async def get_first_round_id(self, package_id: int) -> int | None:
        """Получить ID первого раунда пакета."""
        async with self._session_factory() as session:
            stmt = (
                select(RoundModel.id)
                .where(RoundModel.package_id == package_id)
                .order_by(RoundModel.order_index)
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.first()
            return row[0] if row else None
