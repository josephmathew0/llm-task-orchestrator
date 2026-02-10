import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from app.models import TaskStatus

# TODO: Add good comments above each function - generate with AI
class TaskCreate(BaseModel):
    name: str = Field(..., max_length=200)
    prompt: str
    scheduled_for: datetime | None = None


class TaskChainCreate(BaseModel):
    name: str = Field(..., max_length=200)
    instruction: str = Field(..., min_length=1)
    scheduled_for: datetime | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    name: str
    prompt: str
    status: TaskStatus
    scheduled_for: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    output: str | None
    error: str | None
    parent_task_id: uuid.UUID | None
    llm_provider: str | None
    llm_model: str | None
    latency_ms: int | None

    # retry visibility in API
    attempts: int
    max_attempts: int

    class Config:
        from_attributes = True


class TaskRetryRequest(BaseModel):
    # optional; lets you override max_attempts at retry time
    max_attempts: int | None = Field(default=None, ge=1, le=20)

