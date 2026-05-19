"""add estimated_annual_revenue_eur to full_audits

Revision ID: a1f3e2c9b7d4
Revises: 9c2e4f8b1a6d
Create Date: 2026-05-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1f3e2c9b7d4"
down_revision: Union[str, None] = "9c2e4f8b1a6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "full_audits",
        sa.Column("estimated_annual_revenue_eur", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("full_audits", "estimated_annual_revenue_eur")
