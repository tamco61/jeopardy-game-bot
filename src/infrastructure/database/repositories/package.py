from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.parser.dto import PackageDTO
from src.infrastructure.database.models import (
    PackageModel,
    QuestionModel,
    RoundModel,
    ThemeModel,
)


class PackageRepository:
    """Работа с пакетами вопросов через Postgres."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def check_package_exists(self, title: str, author: str) -> bool:
        """Проверяет, существует ли уже пакет с таким же названием и автором."""
        async with self._session_factory() as session:
            stmt = select(PackageModel.id).where(
                PackageModel.title == title,
                PackageModel.author == author
            ).limit(1)
            result = await session.execute(stmt)
            return result.first() is not None

    async def get_package_by_id(self, package_id: int) -> bool:
        """Проверяет существование пакета по ID."""
        async with self._session_factory() as session:
            stmt = select(PackageModel.id).where(PackageModel.id == package_id).limit(1)
            result = await session.execute(stmt)
            return result.first() is not None

    async def get_all_packages(self) -> list[dict]:
        """Возвращает список всех доступных пакетов (id и название)."""
        async with self._session_factory() as session:
            stmt = select(PackageModel.id, PackageModel.title).order_by(PackageModel.id)
            result = await session.execute(stmt)
            return [{"id": row[0], "title": row[1]} for row in result.all()]

    async def save_package(self, package_dto: PackageDTO) -> int:
        """Сохранить распарсенный пакет и все вложенные сущности."""
        async with self._session_factory() as session:
            package_model = PackageModel(
                title=package_dto.title,
                author=package_dto.author,
            )

            for r_idx, r_dto in enumerate(package_dto.rounds):
                round_model = RoundModel(
                    name=r_dto.name,
                    order_index=r_idx,
                    is_final=r_dto.is_final,
                )
                package_model.rounds.append(round_model)

                for t_idx, t_dto in enumerate(r_dto.themes):
                    theme_model = ThemeModel(
                        name=t_dto.name,
                        order_index=t_idx,
                    )
                    round_model.themes.append(theme_model)

                    for q_idx, q_dto in enumerate(t_dto.questions):
                        question_model = QuestionModel(
                            text=q_dto.text,
                            answer=q_dto.answer,
                            value=q_dto.value,
                            question_type=q_dto.question_type,
                            order_index=q_idx,
                            media_type=q_dto.media_type,
                            telegram_file_id=q_dto.telegram_file_id,
                        )
                        theme_model.questions.append(question_model)

            session.add(package_model)
            await session.commit()

            return package_model.id

    async def delete_package(self, package_id: int) -> bool:
        """Удалить пакет (rounds, themes, questions удалятся каскадно)."""
        async with self._session_factory() as session:
            stmt = delete(PackageModel).where(PackageModel.id == package_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
