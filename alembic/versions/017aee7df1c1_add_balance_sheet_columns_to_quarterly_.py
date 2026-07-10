"""add balance sheet columns to quarterly_financials

Revision ID: 017aee7df1c1
Revises: 44892912880c
Create Date: 2026-07-01 00:07:28.119493

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '017aee7df1c1'
down_revision: Union[str, Sequence[str], None] = '44892912880c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('quarterly_financials', sa.Column('total_assets', sa.Float(), nullable=True))
    op.add_column('quarterly_financials', sa.Column('total_liabilities', sa.Float(), nullable=True))
    op.add_column('quarterly_financials', sa.Column('total_equity', sa.Float(), nullable=True))
    op.add_column('quarterly_financials', sa.Column('cash_and_equivalents', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('quarterly_financials', 'cash_and_equivalents')
    op.drop_column('quarterly_financials', 'total_equity')
    op.drop_column('quarterly_financials', 'total_liabilities')
    op.drop_column('quarterly_financials', 'total_assets')
