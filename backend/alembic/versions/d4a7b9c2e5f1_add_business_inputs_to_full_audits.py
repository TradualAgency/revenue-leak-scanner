"""add aov/sessions/conversion-rate/ad-spend inputs to full_audits

Revision ID: d4a7b9c2e5f1
Revises: c3f6a4e1d8b2
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4a7b9c2e5f1"
down_revision: Union[str, None] = "c3f6a4e1d8b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("full_audits", sa.Column("aov_eur", sa.Float(), nullable=True))
    op.add_column("full_audits", sa.Column("monthly_sessions", sa.Integer(), nullable=True))
    op.add_column("full_audits", sa.Column("conversion_rate_pct", sa.Float(), nullable=True))
    op.add_column("full_audits", sa.Column("monthly_ad_spend_eur", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("full_audits", "monthly_ad_spend_eur")
    op.drop_column("full_audits", "conversion_rate_pct")
    op.drop_column("full_audits", "monthly_sessions")
    op.drop_column("full_audits", "aov_eur")
