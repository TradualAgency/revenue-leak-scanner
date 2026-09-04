"""add competitor_benchmark_runs and competitor_snapshots tables

Revision ID: f7c2d9e4a1b3
Revises: e6b1c8d3f4a9
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "f7c2d9e4a1b3"
down_revision: Union[str, None] = "e6b1c8d3f4a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "competitor_benchmark_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("full_audit_id", sa.Uuid(), sa.ForeignKey("full_audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_domain", sa.String(253), nullable=False),
        sa.Column("location_code", sa.Integer(), nullable=False),
        sa.Column("language_code", sa.String(10), nullable=False),
        sa.Column("market_source", sa.String(30), nullable=False, server_default="tld"),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("include_checkout_probe", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("discovery_json", JSONB(), nullable=True),
        sa.Column("selected_domains", JSONB(), nullable=True),
        sa.Column("operator_added", JSONB(), nullable=True),
        sa.Column("operator_removed", JSONB(), nullable=True),
        sa.Column("benchmark_data", JSONB(), nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_competitor_benchmark_runs_full_audit_id", "competitor_benchmark_runs", ["full_audit_id"],
    )

    op.create_table(
        "competitor_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("location_code", sa.Integer(), nullable=True),
        sa.Column("language_code", sa.String(10), nullable=True),
        sa.Column("snapshot_json", JSONB(), nullable=False),
        sa.Column("measure_status", sa.String(20), nullable=False),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("checkout_probed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("measured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("domain", "schema_version", name="uq_competitor_snapshot_domain_version"),
    )
    op.create_index("ix_competitor_snapshots_domain", "competitor_snapshots", ["domain"])
    op.create_index("ix_competitor_snapshots_measured_at", "competitor_snapshots", ["measured_at"])


def downgrade() -> None:
    op.drop_index("ix_competitor_snapshots_measured_at", table_name="competitor_snapshots")
    op.drop_index("ix_competitor_snapshots_domain", table_name="competitor_snapshots")
    op.drop_table("competitor_snapshots")
    op.drop_index("ix_competitor_benchmark_runs_full_audit_id", table_name="competitor_benchmark_runs")
    op.drop_table("competitor_benchmark_runs")
