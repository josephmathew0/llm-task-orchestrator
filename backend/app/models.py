# backend/app/models.py
"""
SQLAlchemy ORM models for the LLM task system.

Why this file matters:
- This defines the database schema (via SQLAlchemy) and is the single source of truth
  for what a "Task" is in the system.
- The `TaskStatus` enum is persisted in Postgres via a native ENUM type.

Production notes:
- Keep timestamps timezone-aware (UTC end-to-end).
- `cancelled` is a terminal state and must be respected by:
  - scheduler (should not enqueue cancelled tasks)
  - worker (should no-op and not overwrite status)
- We explicitly name the Postgres enum type (`task_status`) to avoid drift across
  migrations/environments.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class TaskStatus(str, enum.Enum):
    """
    Task lifecycle states.

    Convention:
    - scheduled: created with a future scheduled_for time (not runnable yet)
    - queued: ready to run (either immediate or released from scheduled)
    - running: actively being processed by a worker
    - completed: terminal success state
    - failed: terminal failure state (after retries exhausted)
    - cancelled: terminal user-cancelled state (should not be executed)
    """

    scheduled = "scheduled"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class Task(Base):
    """
    Represents one unit of work to be executed by the worker.

    Columns overview:
    - id: UUID primary key.
    - name/prompt: display + instruction text.
    - status: TaskStatus enum; indexed for scheduler/worker queries.
    - scheduled_for: optional UTC timestamp for delayed execution.
    - created_at/started_at/finished_at: lifecycle timestamps.
    - output/error: execution result / error message.
    - attempts/max_attempts: retry bookkeeping.
    - parent_task_id: optional link to previous task for chaining.
    - llm_provider/llm_model/latency_ms: execution metadata.
    """

    __tablename__ = "tasks"

    # Primary key: generated UUID for stable identifiers across services.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # User-visible metadata.
    name: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str] = mapped_column(Text)

    # Current state of the task. Indexed for efficient polling/scheduling queries.
    #
    # IMPORTANT:
    # - We name the DB enum type explicitly (`task_status`) so Postgres has a stable type name.
    # - This prevents Alembic from generating different enum type names across environments,
    #   and makes follow-up migrations (like "add cancelled") straightforward.
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",          # <- Postgres enum type name
            native_enum=True,            # use Postgres ENUM (not a CHECK constraint)
            create_constraint=False,     # keep explicit, avoids surprise CHECK constraints
        ),
        default=TaskStatus.scheduled,
        index=True,
    )

    # Scheduling + timestamps (timezone-aware).
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # created_at uses server_default so DB is the source of truth even across multiple services.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # started_at/finished_at are set by worker logic (or cancellation logic).
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Execution result.
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Retry fields.
    # attempts: number of execution attempts already performed.
    # max_attempts: maximum number of attempts allowed before marking failed.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Task chaining support.
    # parent_task_id is a self-referential FK to tasks.id.
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    parent: Mapped["Task | None"] = relationship(remote_side="Task.id")

    # LLM execution metadata (useful for observability and debugging).
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
