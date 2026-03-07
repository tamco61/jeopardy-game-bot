from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def build_engine(database_url) -> AsyncEngine:
    return create_async_engine(database_url, echo=False)


def build_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )


"""ORM-модели «Своей Игры» (SQLAlchemy 2.0 Declarative).

Эти таблицы хранят СТАТИЧЕСКИЙ контент (пакеты, вопросы, пользователи)
и ИСТОРИЮ ИГР (cold state).

Микро-состояния FSM (LOBBY, ANSWERING, и т.д.) живут в Redis —
в эти таблицы пишется только старт матча и итоговые результаты.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.postgres_repo import Base

# ────────────────────────────────────────────────────
#  ПОЛЬЗОВАТЕЛИ
# ────────────────────────────────────────────────────


class UserModel(Base):
    """Telegram-пользователь (игрок)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    telegram_id: Mapped[int] = mapped_column(
        Integer, unique=True, nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    first_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Связь: участие в сессиях
    game_participations: Mapped[list[GamePlayerModel]] = relationship(
        back_populates="user",
    )


# ────────────────────────────────────────────────────
#  ПАКЕТЫ ВОПРОСОВ
# ────────────────────────────────────────────────────


class PackageModel(Base):
    """Пакет вопросов «Своей Игры»."""

    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    rounds: Mapped[list[RoundModel]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
    )


class RoundModel(Base):
    """Раунд внутри пакета (1-й раунд, 2-й, финальный)."""

    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    package_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_final: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    package: Mapped[PackageModel] = relationship(back_populates="rounds")
    themes: Mapped[list[ThemeModel]] = relationship(
        back_populates="round",
        cascade="all, delete-orphan",
    )


class ThemeModel(Base):
    """Тема (категория) внутри раунда."""

    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    round_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rounds.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    round: Mapped[RoundModel] = relationship(back_populates="themes")
    questions: Mapped[list[QuestionModel]] = relationship(
        back_populates="theme",
        cascade="all, delete-orphan",
    )


class QuestionModel(Base):
    """Вопрос внутри темы."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    theme_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("themes.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="normal",
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    theme: Mapped[ThemeModel] = relationship(back_populates="questions")


# ────────────────────────────────────────────────────
#  ИСТОРИЯ ИГР (Холодный стейт — итоги матчей)
# ────────────────────────────────────────────────────
# Сюда записывается:
#   1. Старт матча (game_sessions со статусом in_progress).
#   2. Итоговые результаты (game_players с final_score).
# Всё промежуточное (FSM-состояние, кто нажал кнопку и т.д.)
# живёт ТОЛЬКО в Redis и НЕ пишется в Postgres.


class GameSessionModel(Base):
    """Сессия (матч) одной игры."""

    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    package_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("packages.id", ondelete="SET NULL"),
        nullable=True,
    )
    chat_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="in_progress",
    )  # in_progress | finished
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    package: Mapped[PackageModel | None] = relationship()
    players: Mapped[list[GamePlayerModel]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class GamePlayerModel(Base):
    """Связь «игрок ↔ сессия» с итоговым счётом."""

    __tablename__ = "game_players"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    final_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped[GameSessionModel] = relationship(back_populates="players")
    user: Mapped[UserModel] = relationship(back_populates="game_participations")


from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.question import Question, QuestionType


class PostgresGameRepository:
    """Работа с игровыми данными через Postgres."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory

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
