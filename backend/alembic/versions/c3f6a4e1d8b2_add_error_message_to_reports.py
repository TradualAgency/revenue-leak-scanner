"""add error_message to reports

Revision ID: c3f6a4e1d8b2
Revises: b2e5f3d8c9a1
Create Date: 2026-08-31 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3f6a4e1d8b2"
down_revision: Union[str, None] = "b2e5f3d8c9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column("error_message", sa.String(length=2000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reports", "error_message")
