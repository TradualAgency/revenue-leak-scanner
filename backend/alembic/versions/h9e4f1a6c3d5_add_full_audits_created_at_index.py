"""add ix_full_audits_created_at for the operator scan list

`full_audits` had no index at all beyond the primary key, and the new
`GET /api/v1/full-audit` list orders every page by `created_at DESC`.

Be honest about what this buys today: at 46 rows Postgres will pick a sequential
scan and sort in memory regardless, so this index changes nothing measurable now.
It is here so the ordering stays cheap as the table grows.

Deliberately *not* a composite `(status, created_at)`: every row currently shares
one status, so it would lead with a cardinality-1 column, and the list does not
filter on status anyway — strictly worse than this. And no index for the `q`
search: a b-tree cannot serve `ILIKE '%term%'`.

Revision ID: h9e4f1a6c3d5
Revises: g8d3e0f5b2c4
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h9e4f1a6c3d5"
down_revision: Union[str, None] = "g8d3e0f5b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Declared as an expression index so the stored order matches the query's
    # `ORDER BY created_at DESC`. It is intentionally not mirrored on the model,
    # so `alembic revision --autogenerate` may offer to drop it — keep it.
    op.create_index("ix_full_audits_created_at", "full_audits", [sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_full_audits_created_at", table_name="full_audits")
