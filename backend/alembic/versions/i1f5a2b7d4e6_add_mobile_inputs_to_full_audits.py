"""add mobile share / mobile conversion-rate inputs to full_audits

Revision ID: i1f5a2b7d4e6
Revises: h9e4f1a6c3d5
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i1f5a2b7d4e6"
down_revision: Union[str, None] = "h9e4f1a6c3d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("full_audits", sa.Column("mobile_share_pct", sa.Float(), nullable=True))
    op.add_column("full_audits", sa.Column("mobile_conversion_rate_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("full_audits", "mobile_conversion_rate_pct")
    op.drop_column("full_audits", "mobile_share_pct")
