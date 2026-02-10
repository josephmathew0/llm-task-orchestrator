# backend/app/main.py

import uuid
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.crud import (
    cancel_task,
    create_chained_task,
    create_task,
    get_task,
    list_tasks,
)
from app.db import get_db
from app.jobs import execute_task
from app.models import TaskStatus
from app.schemas import TaskChainCreate, TaskCreate, TaskOut, TaskRetryRequest
from app.worker import queue

app = FastAPI(title="Vinci4D Mini LLM Task Orchestrator")

# ------------------------------------------------------------------------------
# CORS middleware
# ------------------------------------------------------------------------------
# This allows the frontend (Next.js, Swagger UI, etc.) to call the API.
# In production, you would typically restrict allow_origins to known domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------------------
@app.get("/health")
def health():
    """
    Lightweight health endpoint for Docker, load balancers, or uptime checks.
    """
    return {"ok": True}


# ------------------------------------------------------------------------------
# Create task
# ------------------------------------------------------------------------------
@app.post("/tasks", response_model=TaskOut)
def api_create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    """
    Create a new task.

    The CRUD layer decides the initial status:
      - queued    → run immediately
      - scheduled → picked up later by the scheduler

    Important design choice:
    - The API is responsible for enqueueing *immediate* tasks.
    - The scheduler is responsible for enqueueing *future* tasks.
    """
    task = create_task(db, payload.name, payload.prompt, payload.scheduled_for)

    # If the task should run immediately, enqueue it now.
    # Scheduled tasks are handled by the scheduler process.
    if task.status == TaskStatus.queued:
        queue.enqueue(execute_task, str(task.id))

    return task


# ------------------------------------------------------------------------------
# List tasks
# ------------------------------------------------------------------------------
@app.get("/tasks", response_model=list[TaskOut])
def api_list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    parent_task_id: UUID | None = None,
    db: Session = Depends(get_db),
):
    """
    List tasks with optional pagination and chaining filter.
    """
    return list_tasks(db, limit=limit, offset=offset, parent_task_id=parent_task_id)


# ------------------------------------------------------------------------------
# Get task by id
# ------------------------------------------------------------------------------
@app.get("/tasks/{task_id}", response_model=TaskOut)
def api_get_task(task_id: str, db: Session = Depends(get_db)):
    """
    Fetch a single task by UUID.
    """
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


# ------------------------------------------------------------------------------
# Chain task
# ------------------------------------------------------------------------------
@app.post("/tasks/{task_id}/chain", response_model=TaskOut)
def api_chain_task(task_id: uuid.UUID, payload: TaskChainCreate, db: Session = Depends(get_db)):
    """
    Create a new task whose prompt is derived from a completed parent task.

    Constraints:
    - Parent task must be completed
    - Parent task must have output
    """
    parent = get_task(db, task_id)
    if not parent:
        raise HTTPException(404, "Parent task not found")

    if parent.status != TaskStatus.completed or not parent.output:
        raise HTTPException(409, "Parent task must be completed with output to chain")

    child = create_chained_task(
        db=db,
        parent=parent,
        name=payload.name,
        instruction=payload.instruction,
        scheduled_for=payload.scheduled_for,
    )

    # Same enqueue rule as create_task
    if child.status == TaskStatus.queued:
        queue.enqueue(execute_task, str(child.id))

    return child


# ------------------------------------------------------------------------------
# Retry failed task
# ------------------------------------------------------------------------------
@app.post("/tasks/{task_id}/retry", response_model=TaskOut)
def api_retry_task(
    task_id: uuid.UUID,
    payload: TaskRetryRequest | None = None,
    db: Session = Depends(get_db),
):
    """
    Retry a failed task.

    Behavior:
    - Only failed tasks can be retried
    - Resets execution-related fields
    - Re-enqueues the task immediately
    """
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status != TaskStatus.failed:
        raise HTTPException(409, "Only failed tasks can be retried")

    # Reset fields for a clean retry
    task.status = TaskStatus.queued
    task.attempts = 0

    if payload and payload.max_attempts is not None:
        task.max_attempts = payload.max_attempts

    task.error = None
    task.output = None
    task.started_at = None
    task.finished_at = None
    task.llm_provider = None
    task.llm_model = None
    task.latency_ms = None

    db.commit()
    db.refresh(task)

    queue.enqueue(execute_task, str(task.id))
    return task


# ------------------------------------------------------------------------------
# Cancel task
# ------------------------------------------------------------------------------
@app.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def api_cancel_task(task_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Cancel a task.

    Allowed states:
    - scheduled → safe cancel (will never run)
    - queued    → safe cancel (will never run)
    - running   → best-effort cancel (worker must cooperate)

    Terminal states (completed / failed / cancelled) are idempotent.
    """
    task = cancel_task(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    return task
