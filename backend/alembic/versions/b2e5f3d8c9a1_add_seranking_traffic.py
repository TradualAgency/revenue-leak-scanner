"""add seranking_traffic_json and seranking_fetched_at to full_audits

Revision ID: b2e5f3d8c9a1
Revises: a1f3e2c9b7d4
Create Date: 2026-05-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "b2e5f3d8c9a1"
down_revision: Union[str, None] = "a1f3e2c9b7d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "full_audits",
        sa.Column("seranking_traffic_json", JSONB(), nullable=True),
    )
    op.add_column(
        "full_audits",
        sa.Column("seranking_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("full_audits", "seranking_fetched_at")
    op.drop_column("full_audits", "seranking_traffic_json")
