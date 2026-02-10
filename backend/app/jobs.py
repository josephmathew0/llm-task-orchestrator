# backend/app/jobs.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Task, TaskStatus
from app.llm import get_llm_client
from app.worker import queue


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def execute_task(task_id: str) -> None:
    """
    Worker entrypoint: execute a task, persist output + metadata.
    Adds retry behavior using Task.attempts + Task.max_attempts.
    """
    # TODO: Check if you should use get_db
    db: Session = SessionLocal()
    try:
        task: Optional[Task] = db.get(Task, task_id)
        if not task:
            return

        # Idempotency safety: if task already finished/cancelled, do nothing.
        # TODO: Check if completed / failed/.. should be a all caps - naming convention for enums
        if task.status in (TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled):
            return

        # Mark running and increment attempts
        # TODO Lots of comments to describe this workflow
        # TODO: Stretch P3 - Potentially add console logging -> explore logging library python
        task.attempts = (task.attempts or 0) + 1
        task.status = TaskStatus.running
        if task.started_at is None:
            task.started_at = _utcnow()
        db.commit()
        db.refresh(task)

        start_ts = _utcnow()

        llm = get_llm_client()
        text = llm.generate(task.prompt)

        end_ts = _utcnow()
        latency_ms = int((end_ts - start_ts).total_seconds() * 1000)

        task.output = text
        task.error = None
        task.llm_provider = llm.__class__.__name__
        task.llm_model = getattr(llm, "model", None)
        task.latency_ms = latency_ms
        task.finished_at = end_ts
        task.status = TaskStatus.completed
        db.commit()

    except Exception as e:
        # Persist error + decide retry vs fail
        # TODO: Move "Persist error + decide retry vs fail" to a new handle function. Try inside except not a good approach
        try:
            task = db.get(Task, task_id)
            if not task:
                return

            # If someone cancelled it while it was running, don't retry.
            if task.status == TaskStatus.cancelled:
                task.finished_at = task.finished_at or _utcnow()
                db.commit()
                return

            task.error = str(e)
            task.finished_at = _utcnow()

            max_attempts = task.max_attempts if task.max_attempts is not None else 3
            attempts = task.attempts if task.attempts is not None else 0

            if attempts < max_attempts:
                task.status = TaskStatus.queued
                db.commit()
                db.refresh(task)

                # Re-enqueue immediately
                queue.enqueue(execute_task, str(task.id))
            else:
                task.status = TaskStatus.failed
                db.commit()

        finally:
            # swallow exception so RQ doesn't mark job failed;
            # we manage task status ourselves
            pass

    finally:
        db.close()
