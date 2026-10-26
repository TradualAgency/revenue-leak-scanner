"""add fix_agent_runs table and Shopify Admin token columns on full_audits

Revision ID: j2a6b3c8e5f7
Revises: i1f5a2b7d4e6
Create Date: 2026-10-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "j2a6b3c8e5f7"
down_revision: Union[str, None] = "i1f5a2b7d4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("full_audits", sa.Column("shopify_shop_domain", sa.String(length=255), nullable=True))
    op.add_column("full_audits", sa.Column("shopify_admin_token_enc", sa.String(length=1000), nullable=True))
    op.create_table(
        "fix_agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("full_audit_id", sa.Uuid(), nullable=False),
        sa.Column("agent", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["full_audit_id"], ["full_audits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fix_agent_runs_full_audit_id"), "fix_agent_runs", ["full_audit_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_fix_agent_runs_full_audit_id"), table_name="fix_agent_runs")
    op.drop_table("fix_agent_runs")
    op.drop_column("full_audits", "shopify_admin_token_enc")
    op.drop_column("full_audits", "shopify_shop_domain")
