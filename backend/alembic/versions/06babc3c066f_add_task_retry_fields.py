"""add task retry fields

Revision ID: 06babc3c066f
Revises: ca2310e2a69a
Create Date: 2026-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "06babc3c066f"
down_revision: Union[str, None] = "ca2310e2a69a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))

    # optional: remove server defaults after backfill (keeps schema cleaner)
    op.alter_column("tasks", "attempts", server_default=None)
    op.alter_column("tasks", "max_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("tasks", "max_attempts")
    op.drop_column("tasks", "attempts")
