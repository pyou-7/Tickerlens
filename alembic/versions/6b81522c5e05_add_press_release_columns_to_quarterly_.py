"""add press release columns to quarterly_financials

Revision ID: 6b81522c5e05
Revises: d1f5704c5e60
Create Date: 2026-07-10 15:05:45.503020

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b81522c5e05'
down_revision: Union[str, Sequence[str], None] = 'd1f5704c5e60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('quarterly_financials', sa.Column('press_release_highlights', sa.Text(), nullable=True))
    op.add_column('quarterly_financials', sa.Column('press_release_source', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('quarterly_financials', 'press_release_source')
    op.drop_column('quarterly_financials', 'press_release_highlights')
