"""Add game state persistence columns for blackout recovery

Revision ID: a1b2c3d4e5f6
Revises: 1f4e62303dc7
Create Date: 2026-03-12 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "1f4e62303dc7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── game_sessions: добавляем поля чекпоинта ─────────────────────────────
    op.add_column(
        "game_sessions",
        sa.Column("room_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_game_sessions_room_id", "game_sessions", ["room_id"]
    )
    op.create_index(
        "ix_game_sessions_room_id", "game_sessions", ["room_id"], unique=True
    )
    op.add_column(
        "game_sessions",
        sa.Column(
            "phase", sa.String(length=50), nullable=False, server_default="lobby"
        ),
    )
    op.add_column(
        "game_sessions",
        sa.Column("host_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "game_sessions",
        sa.Column("host_telegram_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "game_sessions",
        sa.Column("current_round_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "game_sessions",
        sa.Column("current_round_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "game_sessions",
        sa.Column(
            "round_number", sa.Integer(), nullable=False, server_default="1"
        ),
    )
    op.add_column(
        "game_sessions",
        sa.Column(
            "total_rounds", sa.Integer(), nullable=False, server_default="1"
        ),
    )
    op.add_column(
        "game_sessions",
        sa.Column("selecting_player_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "game_sessions",
        sa.Column("last_board_message_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "game_sessions",
        sa.Column("closed_questions", sa.Text(), nullable=True),
    )

    # ── game_players: делаем user_id nullable + добавляем поля ──────────────
    op.alter_column(
        "game_players",
        "user_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.add_column(
        "game_players",
        sa.Column("player_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "game_players",
        sa.Column(
            "username", sa.String(length=255), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "game_players",
        sa.Column("telegram_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "game_players",
        sa.Column(
            "score", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    # game_players
    op.drop_column("game_players", "score")
    op.drop_column("game_players", "telegram_id")
    op.drop_column("game_players", "username")
    op.drop_column("game_players", "player_id")
    op.alter_column(
        "game_players",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # game_sessions
    op.drop_column("game_sessions", "closed_questions")
    op.drop_column("game_sessions", "last_board_message_id")
    op.drop_column("game_sessions", "selecting_player_id")
    op.drop_column("game_sessions", "total_rounds")
    op.drop_column("game_sessions", "round_number")
    op.drop_column("game_sessions", "current_round_name")
    op.drop_column("game_sessions", "current_round_id")
    op.drop_column("game_sessions", "host_telegram_id")
    op.drop_column("game_sessions", "host_id")
    op.drop_column("game_sessions", "phase")
    op.drop_index("ix_game_sessions_room_id", table_name="game_sessions")
    op.drop_constraint(
        "uq_game_sessions_room_id", "game_sessions", type_="unique"
    )
    op.drop_column("game_sessions", "room_id")
