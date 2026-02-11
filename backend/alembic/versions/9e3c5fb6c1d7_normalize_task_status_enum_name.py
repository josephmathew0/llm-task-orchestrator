"""normalize task status enum name

Revision ID: 9e3c5fb6c1d7
Revises: 7670f727fabd
Create Date: 2026-02-11

Why this migration exists:
- Older environments may use enum type name `taskstatus`.
- Current model code expects enum type name `task_status`.
- We normalize to `task_status` and ensure `cancelled` value exists.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e3c5fb6c1d7"
down_revision: Union[str, None] = "7670f727fabd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            -- If both types exist, move tasks.status to task_status and drop taskstatus.
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskstatus')
               AND EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_status') THEN
                IF EXISTS (
                    SELECT 1
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    JOIN pg_type t ON t.oid = a.atttypid
                    WHERE c.relname = 'tasks'
                      AND a.attname = 'status'
                      AND t.typname = 'taskstatus'
                ) THEN
                    ALTER TABLE tasks
                    ALTER COLUMN status TYPE task_status
                    USING status::text::task_status;
                END IF;

                DROP TYPE IF EXISTS taskstatus;
            END IF;

            -- If only legacy taskstatus exists, rename it to task_status.
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskstatus')
               AND NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_status') THEN
                ALTER TYPE taskstatus RENAME TO task_status;
            END IF;

            -- Ensure cancelled value exists on the normalized type.
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_status')
               AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON t.oid = e.enumtypid
                    WHERE t.typname = 'task_status'
                      AND e.enumlabel = 'cancelled'
               ) THEN
                ALTER TYPE task_status ADD VALUE 'cancelled';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # No-op: renaming enum types/values is not safely reversible for existing data.
    pass
