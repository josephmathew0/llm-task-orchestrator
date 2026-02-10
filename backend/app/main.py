import uuid
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.crud import create_chained_task, create_task, get_task, is_due, list_tasks
from app.db import get_db
from app.jobs import execute_task
from app.models import TaskStatus
from app.schemas import TaskChainCreate, TaskCreate, TaskOut, TaskRetryRequest
from app.worker import queue

app = FastAPI(title="Vinci4D Mini LLM Task Orchestrator")

# TODO: Explain this
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/tasks", response_model=TaskOut)
def api_create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = create_task(db, payload.name, payload.prompt, payload.scheduled_for)

    if is_due(task):
        task.status = TaskStatus.queued
        db.commit()
        queue.enqueue(execute_task, str(task.id))
        db.refresh(task)

    return task


@app.get("/tasks", response_model=list[TaskOut])
def api_list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    parent_task_id: UUID | None = None,
    db: Session = Depends(get_db),
):
    return list_tasks(db, limit=limit, offset=offset, parent_task_id=parent_task_id)


@app.get("/tasks/{task_id}", response_model=TaskOut)
def api_get_task(task_id: str, db: Session = Depends(get_db)):
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@app.post("/tasks/{task_id}/chain", response_model=TaskOut)
def api_chain_task(task_id: uuid.UUID, payload: TaskChainCreate, db: Session = Depends(get_db)):
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

    if is_due(child):
        child.status = TaskStatus.queued
        db.commit()
        queue.enqueue(execute_task, str(child.id))
        db.refresh(child)

    return child


@app.post("/tasks/{task_id}/retry", response_model=TaskOut)
def api_retry_task(task_id: uuid.UUID, payload: TaskRetryRequest | None = None, db: Session = Depends(get_db)):
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status != TaskStatus.failed:
        raise HTTPException(409, "Only failed tasks can be retried")

    # reset fields for a clean retry
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
