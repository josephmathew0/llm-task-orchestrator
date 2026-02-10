import time
from datetime import datetime, timezone
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Task, TaskStatus
from app.worker import queue
from app.jobs import execute_task

POLL_SECONDS = 2


def claim_and_enqueue_due_tasks():
    # TODO: Check if you should be using get_db? 
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # TODO: Create a new file called query_builder and add this functionality - ScheduledTaskRetrievalQuery
        stmt = (
            select(Task)
            .where(Task.status == TaskStatus.scheduled)
            .where((Task.scheduled_for.is_(None)) | (Task.scheduled_for <= now))
            .with_for_update(skip_locked=True)
            .limit(10)
        )

        tasks = list(db.execute(stmt).scalars().all())
        for task in tasks:
            task.status = TaskStatus.queued
            # TODO: Add comments to relevant functionality/flows. Eg why are we doing db.flush()
            db.flush()
            queue.enqueue(execute_task, str(task.id))

        db.commit()
    finally:
        db.close()


def main():
    while True:
        claim_and_enqueue_due_tasks()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
