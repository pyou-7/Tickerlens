"""add tags to watchlist

Revision ID: 8b2d4f6a1c93
Revises: 5f1c9a2b7d34
Create Date: 2026-09-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b2d4f6a1c93'
down_revision: Union[str, Sequence[str], None] = '5f1c9a2b7d34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('watchlist', sa.Column('tags', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('watchlist', 'tags')
