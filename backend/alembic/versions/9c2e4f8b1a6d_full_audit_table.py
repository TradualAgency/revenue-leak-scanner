"""add full_audits table

Revision ID: 9c2e4f8b1a6d
Revises: bff4d118bed5
Create Date: 2026-05-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9c2e4f8b1a6d"
down_revision: Union[str, None] = "bff4d118bed5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "full_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_url", sa.String(length=2048), nullable=False),
        sa.Column("company_name", sa.String(length=500), nullable=True),
        sa.Column("industry", sa.String(length=200), nullable=True),
        sa.Column("contact_email", sa.String(length=500), nullable=True),
        sa.Column("contact_person", sa.String(length=500), nullable=True),
        sa.Column("scan_level", sa.String(length=20), nullable=False, server_default="outside-only"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("audit_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("full_audits")
