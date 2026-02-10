# backend/app/crud.py

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task, TaskStatus


def _utcnow() -> datetime:
    """Return timezone-aware UTC 'now'."""
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    """
    Normalize incoming datetimes to timezone-aware UTC.

    Why this exists:
    - The API may receive naive datetimes (no tzinfo) from user input or tests.
    - The DB columns are timezone-aware; mixing naive/aware datetimes causes subtle bugs.

    Rules:
    - If dt is None: return None
    - If dt is naive: treat it as UTC (minimal + safe; avoids runtime errors)
    - If dt is aware: convert it to UTC
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _initial_status(scheduled_for: datetime | None) -> TaskStatus:
    """
    Determine initial status for a newly created task.

    Rule:
      - scheduled if scheduled_for is in the future
      - queued if scheduled_for is None or <= now
    """
    now = _utcnow()
    if scheduled_for is None:
        return TaskStatus.queued
    return TaskStatus.scheduled if scheduled_for > now else TaskStatus.queued


def create_task(db: Session, name: str, prompt: str, scheduled_for: datetime | None) -> Task:
    """
    Create a new task.

    Notes:
    - We normalize scheduled_for to UTC.
    - We select initial status based on whether the task is due immediately.
    """
    scheduled_for_utc = _as_utc(scheduled_for)

    task = Task(
        name=name,
        prompt=prompt,
        scheduled_for=scheduled_for_utc,
        status=_initial_status(scheduled_for_utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    parent_task_id: UUID | None = None,
) -> list[Task]:
    """
    List tasks in reverse chronological order.

    Args:
      - limit/offset: basic pagination
      - parent_task_id: filter to a chain
    """
    stmt = select(Task)

    if parent_task_id is not None:
        stmt = stmt.where(Task.parent_task_id == parent_task_id)

    stmt = stmt.order_by(Task.created_at.desc()).limit(limit).offset(offset)

    return list(db.execute(stmt).scalars().all())


def get_task(db: Session, task_id) -> Task | None:
    """Fetch a task by id (UUID)."""
    return db.get(Task, task_id)


def is_due(task: Task) -> bool:
    """
    Used by scheduler/queueing logic:
      - only scheduled tasks can become due
      - due if scheduled_for is None OR scheduled_for <= now (UTC)

    Note: after our create_task() rules, scheduled_for=None will generally mean 'queued',
    but we keep the None check for safety/backwards compatibility.
    """
    if task.status != TaskStatus.scheduled:
        return False
    if task.scheduled_for is None:
        return True
    return _as_utc(task.scheduled_for) <= _utcnow()


def create_chained_task(
    db: Session,
    parent: Task,
    name: str,
    instruction: str,
    scheduled_for: datetime | None,
) -> Task:
    """
    Create a new task whose prompt is derived from a parent task's output.

    Production note:
    - In real systems you may want stricter prompt formatting, truncation,
      or separate 'input' fields instead of concatenating strings.
    """
    prompt = (
        "Parent output:\n"
        "<<<\n"
        f"{parent.output}\n"
        ">>>\n\n"
        f"Instruction:\n{instruction}\n"
    )

    scheduled_for_utc = _as_utc(scheduled_for)

    task = Task(
        name=name,
        prompt=prompt,
        scheduled_for=scheduled_for_utc,
        status=_initial_status(scheduled_for_utc),
        parent_task_id=parent.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def cancel_task(db: Session, task_id) -> Task | None:
    """
    Cancel a task.

    Semantics:
    - scheduled/queued: cancellation prevents the task from being picked up by
      the scheduler/worker.
    - running: cancellation is "best effort". The worker may already be executing.
      We mark cancelled in DB; the worker should periodically check status and stop.

    Returns:
      - Task if found (updated or unchanged)
      - None if task_id does not exist
    """
    task = get_task(db, task_id)
    if not task:
        return None

    # Terminal states: do nothing (idempotent cancel endpoint behavior)
    if task.status in (TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled):
        return task

    # Mark as cancelled and close out if not already finished.
    task.status = TaskStatus.cancelled
    task.finished_at = task.finished_at or _utcnow()

    db.commit()
    db.refresh(task)
    return task
