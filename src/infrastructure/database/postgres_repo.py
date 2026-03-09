"""ORM-модели «Своей Игры» (SQLAlchemy 2.0 Declarative).

Эти таблицы хранят СТАТИЧЕСКИЙ контент (пакеты, вопросы, пользователи)
и ИСТОРИЮ ИГР (cold state).

Микро-состояния FSM (LOBBY, ANSWERING, и т.д.) живут в Redis —
в эти таблицы пишется только старт матча и итоговые результаты.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.parser.dto import PackageDTO
from src.domain.question import Question, QuestionType
from src.infrastructure.database.models import (
    PackageModel,
    QuestionModel,
    RoundModel,
    ThemeModel,
)


class PostgresGameRepository:
    """Работа с игровыми данными через Postgres."""

    def __init__(
            self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory

    # ── Пакеты ──────────────────────────────────────

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
                        )
                        theme_model.questions.append(question_model)

            session.add(package_model)
            await session.commit()

            # После коммита id пакета обновится благодаря возврату из базы
            return package_model.id

    # ── Вопросы ─────────────────────────────────────

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

    # ── Темы ────────────────────────────────────────

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
        from sqlalchemy.orm import selectinload
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

    # ── Раунды ──────────────────────────────────────

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

    # ── Маппинг ORM → Domain Entity ────────────────

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

