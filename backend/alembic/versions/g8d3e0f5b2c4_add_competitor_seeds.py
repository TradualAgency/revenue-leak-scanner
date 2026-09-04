"""add seed_domains, seed_outcomes and measure_limit to competitor_benchmark_runs

Lets an operator name competitors up-front instead of only correcting the
auto-discovered set afterwards. `seed_domains` is deliberately separate from the
existing `operator_added`: seeds are known before discovery and must be re-applied
when a run is re-discovered (e.g. after a market change), whereas `operator_added` is
the after-the-fact correction list.

Revision ID: g8d3e0f5b2c4
Revises: f7c2d9e4a1b3
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "g8d3e0f5b2c4"
down_revision: Union[str, None] = "f7c2d9e4a1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("competitor_benchmark_runs", sa.Column("seed_domains", JSONB(), nullable=True))
    op.add_column("competitor_benchmark_runs", sa.Column("seed_outcomes", JSONB(), nullable=True))
    op.add_column(
        "competitor_benchmark_runs",
        sa.Column("measure_limit", sa.Integer(), nullable=False, server_default="8"),
    )


def downgrade() -> None:
    op.drop_column("competitor_benchmark_runs", "measure_limit")
    op.drop_column("competitor_benchmark_runs", "seed_outcomes")
    op.drop_column("competitor_benchmark_runs", "seed_domains")
