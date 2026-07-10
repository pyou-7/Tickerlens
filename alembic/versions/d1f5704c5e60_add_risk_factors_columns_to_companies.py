"""add risk_factors columns to companies

Revision ID: d1f5704c5e60
Revises: 017aee7df1c1
Create Date: 2026-07-04 15:26:05.482642

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1f5704c5e60'
down_revision: Union[str, Sequence[str], None] = '017aee7df1c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('companies', sa.Column('risk_factors', sa.Text(), nullable=True))
    op.add_column('companies', sa.Column('risk_factors_source', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('companies', 'risk_factors_source')
    op.drop_column('companies', 'risk_factors')
