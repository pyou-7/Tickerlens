"""add note to watchlist

Revision ID: 5f1c9a2b7d34
Revises: 7a3e9c1f4b22
Create Date: 2026-09-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f1c9a2b7d34'
down_revision: Union[str, Sequence[str], None] = '7a3e9c1f4b22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('watchlist', sa.Column('note', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('watchlist', 'note')
