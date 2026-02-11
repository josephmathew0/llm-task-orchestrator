from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Task, TaskStatus


def test_create_immediate_task_enqueues_job(client, queue_spy):
    response = client.post(
        "/tasks",
        json={"name": "immediate task", "prompt": "hello", "scheduled_for": None},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == TaskStatus.queued.value
    assert len(queue_spy) == 1
    _, args, _ = queue_spy[0]
    assert args[0] == payload["id"]


def test_create_scheduled_task_does_not_enqueue(client, queue_spy):
    scheduled_for = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    response = client.post(
        "/tasks",
        json={"name": "scheduled task", "prompt": "hello later", "scheduled_for": scheduled_for},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == TaskStatus.scheduled.value
    assert len(queue_spy) == 0


def test_retry_resets_failed_task_and_enqueues(client, db_session_factory, queue_spy):
    with db_session_factory() as db:
        task = Task(
            name="failed task",
            prompt="retry me",
            status=TaskStatus.failed,
            attempts=3,
            max_attempts=3,
            error="boom",
            output="stale output",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            llm_provider="OldProvider",
            llm_model="old-model",
            latency_ms=123,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = str(task.id)

    response = client.post(f"/tasks/{task_id}/retry", json={"max_attempts": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == TaskStatus.queued.value
    assert payload["attempts"] == 0
    assert payload["max_attempts"] == 5
    assert payload["error"] is None
    assert payload["output"] is None
    assert payload["started_at"] is None
    assert payload["finished_at"] is None
    assert payload["llm_provider"] is None
    assert payload["llm_model"] is None
    assert payload["latency_ms"] is None
    assert len(queue_spy) == 1
    _, args, _ = queue_spy[0]
    assert args[0] == task_id


def test_cancel_endpoint_is_idempotent(client, db_session_factory):
    with db_session_factory() as db:
        task = Task(name="cancel me", prompt="cancel", status=TaskStatus.queued)
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = str(task.id)

    first = client.post(f"/tasks/{task_id}/cancel")
    assert first.status_code == 200
    assert first.json()["status"] == TaskStatus.cancelled.value

    second = client.post(f"/tasks/{task_id}/cancel")
    assert second.status_code == 200
    assert second.json()["status"] == TaskStatus.cancelled.value


def test_get_task_invalid_uuid_returns_422(client):
    response = client.get("/tasks/not-a-uuid")
    assert response.status_code == 422
