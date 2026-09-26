"""add ocf, capex, guidance, commentary columns to quarterly_financials

Revision ID: e89a1b2c3d4e
Revises: 6b81522c5e05
Create Date: 2026-09-25 23:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e89a1b2c3d4e'
down_revision: Union[str, Sequence[str], None] = '6b81522c5e05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('quarterly_financials', sa.Column('operating_cash_flow', sa.Float(), nullable=True))
    op.add_column('quarterly_financials', sa.Column('capex', sa.Float(), nullable=True))
    op.add_column('quarterly_financials', sa.Column('guidance', sa.Text(), nullable=True))
    op.add_column('quarterly_financials', sa.Column('executive_commentary', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('quarterly_financials', 'executive_commentary')
    op.drop_column('quarterly_financials', 'guidance')
    op.drop_column('quarterly_financials', 'capex')
    op.drop_column('quarterly_financials', 'operating_cash_flow')
