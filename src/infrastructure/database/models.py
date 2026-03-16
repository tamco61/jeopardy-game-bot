from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    BigInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base

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
        BigInteger, unique=True, nullable=False, index=True
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

    media_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    telegram_file_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )

    theme: Mapped[ThemeModel] = relationship(back_populates="questions")


# ────────────────────────────────────────────────────
#  ИСТОРИЯ ИГР
# ────────────────────────────────────────────────────
# Пишется при:
#   1. Старте матча (create_session, status=in_progress).
#   2. После каждого вердикта (update_session — чекпоинт для восстановления).
#   3. Окончании игры (mark_finished, status=finished, final_score).
# При полном блэкауте Core читает in_progress-сессии из Postgres
# и восстанавливает Room в Redis в фазе BOARD_VIEW.


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
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    # Идентификатор Redis-комнаты (для сверки при восстановлении)
    room_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="in_progress",
    )  # in_progress | finished

    # ── Поля чекпоинта (восстановление после блэкаута) ──
    phase: Mapped[str] = mapped_column(
        String(50), nullable=False, default="lobby"
    )
    host_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    is_private: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    current_round_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    current_round_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    round_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    total_rounds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    selecting_player_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    last_board_message_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # JSON-массив ID закрытых вопросов: "[1, 2, 3]"
    closed_questions: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    """Связь «игрок ↔ сессия» с текущим и итоговым счётом."""

    __tablename__ = "game_players"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # FK на users (nullable — для веб-игроков без Telegram-аккаунта)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Строковый player_id (= telegram_id.str или произвольный веб-ID)
    player_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Текущий счёт (обновляется на каждом чекпоинте)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Финальный счёт (заполняется при mark_finished)
    final_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped[GameSessionModel] = relationship(back_populates="players")
    user: Mapped[UserModel | None] = relationship(
        back_populates="game_participations"
    )
