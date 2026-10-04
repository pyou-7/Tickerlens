"""add management guidance and transcript excerpts to quarterly_financials

Revision ID: 04ce7a6b3d14
Revises: 8b2d4f6a1c93
Create Date: 2026-10-03 23:26:03.588109

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04ce7a6b3d14'
down_revision: Union[str, Sequence[str], None] = '8b2d4f6a1c93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('quarterly_financials', sa.Column('management_guidance', sa.Text(), nullable=True))
    op.add_column('quarterly_financials', sa.Column('management_guidance_source', sa.String(length=64), nullable=True))
    op.add_column('quarterly_financials', sa.Column('transcript_excerpts', sa.Text(), nullable=True))
    op.add_column('quarterly_financials', sa.Column('transcript_source', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('quarterly_financials', 'transcript_source')
    op.drop_column('quarterly_financials', 'transcript_excerpts')
    op.drop_column('quarterly_financials', 'management_guidance_source')
    op.drop_column('quarterly_financials', 'management_guidance')
