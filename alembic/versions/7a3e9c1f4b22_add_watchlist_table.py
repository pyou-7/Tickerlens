"""add watchlist table

Revision ID: 7a3e9c1f4b22
Revises: 3049fff86581
Create Date: 2026-09-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a3e9c1f4b22'
down_revision: Union[str, Sequence[str], None] = '3049fff86581'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'watchlist',
        sa.Column('cik', sa.String(length=10), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('cik'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('watchlist')
