"""add game_mode to game_sessions

Revision ID: 2026_03_16_def456789012
Revises: 2026_03_16_abc123456789
Create Date: 2026-03-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2026_03_16_def456789012'
down_revision: Union[str, None] = '2026_03_16_abc123456789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляет поле game_mode в таблицу game_sessions."""
    op.add_column(
        'game_sessions',
        sa.Column('game_mode', sa.String(20), nullable=False, server_default='manual')
    )


def downgrade() -> None:
    """Удаляет поле game_mode из таблицы game_sessions."""
    op.drop_column('game_sessions', 'game_mode')
