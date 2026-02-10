import time
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import TaskStatus
from app.crud import get_task
from app.llm import get_llm_client


def run_task(db: Session, task_id):
    task = get_task(db, task_id)
    if not task:
        return
    # TODO: Check on the differnce between this and job.py -> execute task
    # TODO: If both are needed move common functionality to a separate file
    # TODO: clear comments on the purpose
    # idempotency: don't rerun finished tasks
    if task.status in (TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled):
        return

    task.status = TaskStatus.running
    task.started_at = datetime.now(timezone.utc)
    task.error = None
    db.commit()

    client = get_llm_client()
    start = time.time()

    try:
        output = client.generate(task.prompt)
        latency_ms = int((time.time() - start) * 1000)

        task.output = output
        task.status = TaskStatus.completed
        task.finished_at = datetime.now(timezone.utc)
        task.llm_provider = client.__class__.__name__
        task.llm_model = getattr(client, "model", None)
        task.latency_ms = latency_ms
        db.commit()
    except Exception as e:
        task.status = TaskStatus.failed
        task.error = str(e)
        task.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise
