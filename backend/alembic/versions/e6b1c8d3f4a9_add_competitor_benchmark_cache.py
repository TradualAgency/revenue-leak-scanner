"""add competitor_benchmark_json and competitor_benchmark_fetched_at to full_audits

Revision ID: e6b1c8d3f4a9
Revises: d4a7b9c2e5f1
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "e6b1c8d3f4a9"
down_revision: Union[str, None] = "d4a7b9c2e5f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("full_audits", sa.Column("competitor_benchmark_json", JSONB(), nullable=True))
    op.add_column(
        "full_audits",
        sa.Column("competitor_benchmark_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("full_audits", "competitor_benchmark_fetched_at")
    op.drop_column("full_audits", "competitor_benchmark_json")
