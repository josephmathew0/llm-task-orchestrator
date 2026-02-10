# backend/app/jobs.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.llm import get_llm_client
from app.models import Task, TaskStatus
from app.worker import queue


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def execute_task(task_id: str) -> None:
    """
    RQ worker entrypoint: execute a task and persist output + metadata.

    Key properties:
    - Idempotent: safe to run multiple times (will no-op for terminal states).
    - Best-effort cancellation:
        * If a task is cancelled before execution begins, we do nothing.
        * If cancelled while running, we cannot forcibly stop the LLM call
          (unless the LLM client supports cancellation). We therefore:
            - check for cancellation right before starting
            - check again right after generation
            - if cancelled, we record finished_at and do NOT overwrite status
              to completed, and we do NOT retry.
    - Retry behavior:
        * Uses Task.attempts and Task.max_attempts
        * Re-enqueues only if task is not cancelled and attempts < max_attempts
    """
    db: Session = SessionLocal()
    try:
        task: Optional[Task] = db.get(Task, task_id)
        if not task:
            return

        # Terminal states are idempotent: do nothing.
        if task.status in (TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled):
            return

        # If a task is still scheduled (future), the scheduler should enqueue it later.
        # If it ended up here anyway, treat it as a no-op to avoid early execution.
        if task.status == TaskStatus.scheduled:
            return

        # Cancellation check BEFORE marking running:
        # This covers the common case: cancelled while queued.
        if task.status == TaskStatus.cancelled:
            task.finished_at = task.finished_at or _utcnow()
            db.commit()
            return

        # ----------------------------------------------------------------------
        # Transition to running (single source of truth stored in DB)
        # ----------------------------------------------------------------------
        # We increment attempts when we begin an execution attempt.
        task.attempts = (task.attempts or 0) + 1
        task.status = TaskStatus.running
        task.error = None
        if task.started_at is None:
            task.started_at = _utcnow()
        db.commit()
        db.refresh(task)

        # If the task was cancelled immediately after we set running,
        # bail out without doing work.
        if task.status == TaskStatus.cancelled:
            task.finished_at = task.finished_at or _utcnow()
            db.commit()
            return

        # ----------------------------------------------------------------------
        # Execute the model call
        # ----------------------------------------------------------------------
        start_ts = _utcnow()
        llm = get_llm_client()
        text = llm.generate(task.prompt)
        end_ts = _utcnow()
        latency_ms = int((end_ts - start_ts).total_seconds() * 1000)

        # Re-load to ensure we respect cancellations that occurred mid-run.
        # (Separate transactions/processes could have updated status.)
        db.refresh(task)

        # If cancelled while the model was running, don't mark completed.
        if task.status == TaskStatus.cancelled:
            task.finished_at = task.finished_at or end_ts
            db.commit()
            return

        # ----------------------------------------------------------------------
        # Persist success
        # ----------------------------------------------------------------------
        task.output = text
        task.error = None
        task.llm_provider = llm.__class__.__name__
        task.llm_model = getattr(llm, "model", None)
        task.latency_ms = latency_ms
        task.finished_at = end_ts
        task.status = TaskStatus.completed
        db.commit()

    except Exception as e:
        # Persist error + decide retry vs fail.
        # We intentionally swallow exceptions so RQ doesn't mark the job as failed;
        # task status is the source of truth for orchestration.
        try:
            task = db.get(Task, task_id)
            if not task:
                return

            # If cancelled at any point, do not retry and do not overwrite status.
            if task.status == TaskStatus.cancelled:
                task.finished_at = task.finished_at or _utcnow()
                db.commit()
                return

            task.error = str(e)
            task.finished_at = _utcnow()

            max_attempts = task.max_attempts if task.max_attempts is not None else 3
            attempts = task.attempts if task.attempts is not None else 0

            if attempts < max_attempts:
                # Put back to queued and re-enqueue immediately.
                # Note: if cancellation happens after this point, the next run will no-op.
                task.status = TaskStatus.queued
                db.commit()
                db.refresh(task)
                queue.enqueue(execute_task, str(task.id))
            else:
                task.status = TaskStatus.failed
                db.commit()

        finally:
            # Swallow exception so RQ doesn't manage retries/status.
            pass

    finally:
        db.close()
