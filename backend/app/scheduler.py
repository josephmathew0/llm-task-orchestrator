# backend/app/scheduler.py
"""
Task scheduler process.

Responsibility:
- Periodically scan the DB for tasks in status=scheduled that are now "due"
  (scheduled_for <= now).
- Atomically "claim" those tasks by flipping scheduled -> queued.
- Enqueue claimed task IDs onto the Redis queue so workers can execute them.

Key design goals:
- Exactly-once enqueue per task (in practice: *at-most-once enqueue* with DB as source of truth).
- Safe with multiple scheduler instances (FOR UPDATE SKIP LOCKED).
- Respect cancellation: cancelled tasks must never be enqueued.
- Production-friendly loop: backoff on transient DB errors; avoid spammy logs.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Iterable, List

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.db import SessionLocal
from app.jobs import execute_task
from app.models import Task, TaskStatus
from app.worker import queue

# How often the scheduler wakes up to look for due tasks.
POLL_SECONDS = 2

# Max tasks to claim in a single DB transaction. Keeps the scheduler lightweight.
BATCH_SIZE = 10

# Backoff configuration if the DB is temporarily unavailable.
DB_ERROR_BACKOFF_MIN_SECONDS = 1
DB_ERROR_BACKOFF_MAX_SECONDS = 15


def _utcnow() -> datetime:
    """Return timezone-aware UTC 'now'."""
    return datetime.now(timezone.utc)


def _sleep_with_jitter(seconds: float) -> None:
    """
    Sleep for `seconds` plus a small jitter to avoid thundering herd behavior
    if multiple schedulers restart at the same time.
    """
    jitter = random.uniform(0, 0.25)  # 0-250ms
    time.sleep(max(0.0, seconds + jitter))


def claim_and_enqueue_due_tasks() -> int:
    """
    One scheduler "tick".

    Steps:
      1) Select up to BATCH_SIZE tasks:
           - status = scheduled
           - scheduled_for IS NOT NULL
           - scheduled_for <= now
         using FOR UPDATE SKIP LOCKED so multiple schedulers won't double-claim.
      2) Flip each row to status=queued (claim).
      3) Commit transaction (DB is the source of truth).
      4) Enqueue jobs outside the transaction.

    Important notes:
    - We never enqueue before commit. If we crash between claim and enqueue,
      the task will be queued in DB but not in Redis. That's acceptable here and
      can be handled later by a "reconciler" (optional) that re-enqueues queued tasks
      that have no worker activity.
    - Cancelled tasks are excluded by the WHERE clause; additionally, we do a
      belt-and-suspenders check before updating.
    """
    db = SessionLocal()
    claimed_ids: List[str] = []

    try:
        now = _utcnow()

        # Select a small batch of scheduled tasks that are due.
        # FOR UPDATE SKIP LOCKED:
        # - prevents two scheduler instances from claiming the same task
        # - avoids deadlocks and allows horizontal scaling
        stmt = (
            select(Task)
            .where(Task.status == TaskStatus.scheduled)
            .where(Task.scheduled_for.is_not(None))
            .where(Task.scheduled_for <= now)
            .order_by(Task.scheduled_for.asc())
            .with_for_update(skip_locked=True)
            .limit(BATCH_SIZE)
        )

        tasks = list(db.execute(stmt).scalars().all())

        for task in tasks:
            # Defensive checks:
            # - If someone cancelled it between select and update, don't claim.
            # - If status changed for any reason, don't claim.
            if task.status != TaskStatus.scheduled:
                continue

            # Claim: scheduled -> queued
            task.status = TaskStatus.queued
            claimed_ids.append(str(task.id))

        # Commit the claim BEFORE enqueueing so we don't enqueue the same task twice.
        db.commit()

    finally:
        db.close()

    # Enqueue outside the DB transaction.
    # This avoids holding DB locks while talking to Redis.
    for task_id in claimed_ids:
        queue.enqueue(execute_task, task_id)

    return len(claimed_ids)


def main() -> None:
    """
    Main scheduler loop.

    Production readiness improvements:
    - Adds simple backoff for transient DB errors (OperationalError).
    - Avoids spamming errors for expected startup race conditions.
    """
    backoff_seconds = DB_ERROR_BACKOFF_MIN_SECONDS

    while True:
        try:
            n = claim_and_enqueue_due_tasks()
            if n:
                # Keep logging lightweight; in real systems use structured logging.
                print(f"[scheduler] claimed+enqueued={n} at {_utcnow().isoformat()}")

            # Reset backoff after a successful tick.
            backoff_seconds = DB_ERROR_BACKOFF_MIN_SECONDS
            _sleep_with_jitter(POLL_SECONDS)

        except (OperationalError,) as e:
            # DB temporarily unavailable (startup, network hiccup, etc.).
            # Backoff to reduce log noise and avoid hammering the DB.
            print(f"[scheduler] DB OperationalError: {e!r} (backing off {backoff_seconds}s)")
            _sleep_with_jitter(backoff_seconds)
            backoff_seconds = min(DB_ERROR_BACKOFF_MAX_SECONDS, backoff_seconds * 2)

        except (ProgrammingError,) as e:
            # Typically indicates schema mismatch / migrations not applied yet.
            # Keep process alive and retry; this often resolves after `alembic upgrade head`.
            print(f"[scheduler] DB ProgrammingError: {e!r} (did you run migrations?)")
            _sleep_with_jitter(max(POLL_SECONDS, 3))

        except Exception as e:
            # Unknown error: keep scheduler alive.
            print(f"[scheduler] ERROR: {e!r}")
            _sleep_with_jitter(POLL_SECONDS)


if __name__ == "__main__":
    main()
