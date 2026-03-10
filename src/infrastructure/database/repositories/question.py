from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.question import Question, QuestionType
from src.infrastructure.database.models import QuestionModel, ThemeModel


class QuestionRepository:
    """Работа с вопросами через Postgres."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_question_by_id(self, question_id: int) -> Question | None:
        async with self._session_factory() as session:
            stmt = (
                select(QuestionModel, ThemeModel.name)
                .join(ThemeModel, QuestionModel.theme_id == ThemeModel.id)
                .where(QuestionModel.id == question_id)
            )
            result = await session.execute(stmt)
            row = result.one_or_none()
            if row is None:
                return None
            return self._to_entity(row[0], theme_name=row[1])

    async def get_questions_by_theme(self, theme_id: int) -> list[Question]:
        async with self._session_factory() as session:
            stmt = (
                select(QuestionModel, ThemeModel.name)
                .join(ThemeModel, QuestionModel.theme_id == ThemeModel.id)
                .where(QuestionModel.theme_id == theme_id)
                .order_by(QuestionModel.order_index)
            )
            result = await session.execute(stmt)
            return [
                self._to_entity(row[0], theme_name=row[1])
                for row in result.all()
            ]

    async def get_random_question(
            self, theme_id: int | None = None
    ) -> Question | None:
        async with self._session_factory() as session:
            stmt = (
                select(QuestionModel, ThemeModel.name)
                .join(ThemeModel, QuestionModel.theme_id == ThemeModel.id)
                .order_by(func.random())
                .limit(1)
            )
            if theme_id is not None:
                stmt = stmt.where(QuestionModel.theme_id == theme_id)

            result = await session.execute(stmt)
            row = result.one_or_none()
            if row is None:
                return None
            return self._to_entity(row[0], theme_name=row[1])

    @staticmethod
    def _to_entity(model: QuestionModel, *, theme_name: str) -> Question:
        return Question(
            question_id=model.id,
            theme_name=theme_name,
            text=model.text,
            answer=model.answer,
            value=model.value,
            question_type=QuestionType(model.question_type),
        )
