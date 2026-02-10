from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task, TaskStatus


def create_task(db: Session, name: str, prompt: str, scheduled_for: datetime | None) -> Task:
    task = Task(
        name=name,
        prompt=prompt,
        scheduled_for=scheduled_for,
        status=TaskStatus.scheduled,
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
    stmt = select(Task)

    if parent_task_id is not None:
        stmt = stmt.where(Task.parent_task_id == parent_task_id)

    stmt = stmt.order_by(Task.created_at.desc()).limit(limit).offset(offset)

    return list(db.execute(stmt).scalars().all())


def get_task(db: Session, task_id) -> Task | None:
    return db.get(Task, task_id)


def is_due(task: Task) -> bool:
    if task.status != TaskStatus.scheduled:
        return False
    if task.scheduled_for is None:
        return True
    return task.scheduled_for <= datetime.now(timezone.utc)


def create_chained_task(
    db: Session,
    parent: Task,
    name: str,
    instruction: str,
    scheduled_for: datetime | None,
) -> Task:
    prompt = (
        "Parent output:\n"
        "<<<\n"
        f"{parent.output}\n"
        ">>>\n\n"
        f"Instruction:\n{instruction}\n"
    )

    task = Task(
        name=name,
        prompt=prompt,
        scheduled_for=scheduled_for,
        status=TaskStatus.scheduled,
        parent_task_id=parent.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
