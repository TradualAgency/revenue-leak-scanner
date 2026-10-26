"""add audit_screenshots table (funnel agent evidence)

Revision ID: k3b7c4d9f6a8
Revises: j2a6b3c8e5f7
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k3b7c4d9f6a8"
down_revision: Union[str, None] = "j2a6b3c8e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_screenshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("full_audit_id", sa.Uuid(), nullable=False),
        sa.Column("image", sa.LargeBinary(), nullable=False),
        sa.Column("caption", sa.String(length=500), nullable=True),
        sa.Column("page_url", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["full_audit_id"], ["full_audits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_screenshots_full_audit_id"), "audit_screenshots", ["full_audit_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_screenshots_full_audit_id"), table_name="audit_screenshots")
    op.drop_table("audit_screenshots")
