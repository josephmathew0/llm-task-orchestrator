# backend/app/schemas.py
"""
Pydantic schemas (request/response models) for the API.

Why this file exists:
- FastAPI uses Pydantic models to validate incoming request bodies.
- Pydantic models also define the shape of responses (what the API returns).
- This gives you strong validation, clear docs (OpenAPI), and stable contracts for the frontend.

Note:
- We use `from_attributes = True` so response models can be created directly from
  SQLAlchemy ORM objects.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models import TaskStatus


class TaskCreate(BaseModel):
    """
    Request body for creating a new task.

    `scheduled_for`:
      - If None, task is due immediately (backend will mark it queued and enqueue).
      - If provided and in the future, task is scheduled and the scheduler will enqueue it later.
    """
    name: str = Field(..., max_length=200, description="Human-friendly task name")
    prompt: str = Field(..., min_length=1, description="Prompt sent to the LLM")
    scheduled_for: Optional[datetime] = Field(
        default=None,
        description="UTC datetime when the task should run (optional)",
    )


class TaskChainCreate(BaseModel):
    """
    Request body for creating a child task from a parent task's output.
    """
    name: str = Field(..., max_length=200, description="Child task name")
    instruction: str = Field(..., min_length=1, description="Instruction applied to the parent output")
    scheduled_for: Optional[datetime] = Field(
        default=None,
        description="UTC datetime when the chained task should run (optional)",
    )


class TaskOut(BaseModel):
    """
    API response model representing a Task.

    This mirrors the DB entity closely so the frontend can render:
    - status, timestamps, outputs, errors, provider/model metadata, retry info, and parent linkage.
    """
    id: uuid.UUID
    name: str
    prompt: str
    status: TaskStatus

    scheduled_for: Optional[datetime]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    output: Optional[str]
    error: Optional[str]

    parent_task_id: Optional[uuid.UUID]

    llm_provider: Optional[str]
    llm_model: Optional[str]
    latency_ms: Optional[int]

    # retry visibility in API
    attempts: int
    max_attempts: int

    class Config:
        # Allow `TaskOut.model_validate(sqlalchemy_task)` style conversion from ORM objects.
        from_attributes = True


class TaskRetryRequest(BaseModel):
    """
    Optional request body for retrying a task.

    Allows the client to override `max_attempts` when retrying.
    """
    max_attempts: Optional[int] = Field(
        default=None,
        ge=1,
        le=20,
        description="Override the task's max retry attempts for this retry cycle",
    )


class TaskCancelRequest(BaseModel):
    """
    Optional request body for cancelling a task.

    We keep this lightweight and forward-compatible:
    - `reason` is optional, stored/used only if you later choose to persist it.
    - Cancellation semantics (what can be cancelled and when) are enforced in the API + worker.
    """
    reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional reason for cancellation (for audit/logging/UI)",
    )
