"""Add observation acknowledgment columns

Revision ID: 002
Revises: 001
Create Date: 2026-08-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "observations",
        sa.Column("acknowledged", sa.Boolean(), server_default="0", nullable=False),
    )
    op.add_column(
        "observations",
        sa.Column("acknowledged_by", sa.Integer(), nullable=True),
    )
    op.add_column(
        "observations",
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("observations", "acknowledged_at")
    op.drop_column("observations", "acknowledged_by")
    op.drop_column("observations", "acknowledged")
