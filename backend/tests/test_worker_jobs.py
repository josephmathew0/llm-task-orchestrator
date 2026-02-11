from __future__ import annotations

import threading
import time

from app.jobs import execute_task
from app.models import Task, TaskStatus


class SuccessLLM:
    model = "test-model"

    def generate(self, prompt: str) -> str:
        return f"ok: {prompt}"


def test_execute_task_completes_and_persists_metadata(db_session_factory, monkeypatch, queue_spy):
    with db_session_factory() as db:
        task = Task(name="worker success", prompt="hello", status=TaskStatus.queued)
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
        task_id_str = str(task.id)

    monkeypatch.setattr("app.jobs.SessionLocal", db_session_factory)
    monkeypatch.setattr("app.jobs.get_llm_client", lambda: SuccessLLM())

    execute_task(task_id_str)

    with db_session_factory() as db:
        saved = db.get(Task, task_id)
        assert saved is not None
        assert saved.status == TaskStatus.completed
        assert saved.attempts == 1
        assert saved.output == "ok: hello"
        assert saved.error is None
        assert saved.started_at is not None
        assert saved.finished_at is not None
        assert saved.llm_provider == "SuccessLLM"
        assert saved.llm_model == "test-model"
        assert saved.latency_ms is not None
        assert saved.latency_ms >= 0

    assert queue_spy == []


def test_execute_task_requeues_when_attempts_remain(db_session_factory, monkeypatch, queue_spy):
    class FailingLLM:
        def generate(self, prompt: str) -> str:
            raise RuntimeError("transient failure")

    with db_session_factory() as db:
        task = Task(
            name="retry me",
            prompt="fail once",
            status=TaskStatus.queued,
            attempts=0,
            max_attempts=2,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
        task_id_str = str(task.id)

    monkeypatch.setattr("app.jobs.SessionLocal", db_session_factory)
    monkeypatch.setattr("app.jobs.get_llm_client", lambda: FailingLLM())

    execute_task(task_id_str)

    with db_session_factory() as db:
        saved = db.get(Task, task_id)
        assert saved is not None
        assert saved.status == TaskStatus.queued
        assert saved.attempts == 1
        assert saved.error == "transient failure"
        assert saved.finished_at is not None

    assert len(queue_spy) == 1
    _, args, _ = queue_spy[0]
    assert args[0] == task_id_str


def test_execute_task_marks_failed_when_attempts_exhausted(db_session_factory, monkeypatch, queue_spy):
    class AlwaysFailLLM:
        def generate(self, prompt: str) -> str:
            raise RuntimeError("permanent failure")

    with db_session_factory() as db:
        task = Task(
            name="fail hard",
            prompt="no retry",
            status=TaskStatus.queued,
            attempts=0,
            max_attempts=1,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
        task_id_str = str(task.id)

    monkeypatch.setattr("app.jobs.SessionLocal", db_session_factory)
    monkeypatch.setattr("app.jobs.get_llm_client", lambda: AlwaysFailLLM())

    execute_task(task_id_str)

    with db_session_factory() as db:
        saved = db.get(Task, task_id)
        assert saved is not None
        assert saved.status == TaskStatus.failed
        assert saved.attempts == 1
        assert saved.error == "permanent failure"

    assert queue_spy == []


def test_execute_task_respects_mid_run_cancellation(db_session_factory, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    class BlockingLLM:
        def generate(self, prompt: str) -> str:
            started.set()
            release.wait(timeout=5)
            return "should not be persisted"

    with db_session_factory() as db:
        task = Task(name="cancel in flight", prompt="work", status=TaskStatus.queued)
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
        task_id_str = str(task.id)

    monkeypatch.setattr("app.jobs.SessionLocal", db_session_factory)
    monkeypatch.setattr("app.jobs.get_llm_client", lambda: BlockingLLM())

    worker_thread = threading.Thread(target=execute_task, args=(task_id_str,))
    worker_thread.start()

    assert started.wait(timeout=5)
    with db_session_factory() as db:
        task = db.get(Task, task_id)
        assert task is not None
        task.status = TaskStatus.cancelled
        db.commit()

    release.set()
    worker_thread.join(timeout=5)
    assert not worker_thread.is_alive()

    with db_session_factory() as db:
        saved = db.get(Task, task_id)
        assert saved is not None
        assert saved.status == TaskStatus.cancelled
        assert saved.output is None
        assert saved.finished_at is not None


def test_execute_task_atomic_claim_prevents_double_run(db_session_factory, monkeypatch):
    lock = threading.Lock()
    calls = {"count": 0}

    class SlowLLM:
        model = "slow-model"

        def generate(self, prompt: str) -> str:
            with lock:
                calls["count"] += 1
            time.sleep(0.15)
            return "single run"

    with db_session_factory() as db:
        task = Task(name="race", prompt="once", status=TaskStatus.queued)
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
        task_id_str = str(task.id)

    monkeypatch.setattr("app.jobs.SessionLocal", db_session_factory)
    monkeypatch.setattr("app.jobs.get_llm_client", lambda: SlowLLM())

    t1 = threading.Thread(target=execute_task, args=(task_id_str,))
    t2 = threading.Thread(target=execute_task, args=(task_id_str,))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    with db_session_factory() as db:
        saved = db.get(Task, task_id)
        assert saved is not None
        assert saved.status == TaskStatus.completed
        assert saved.attempts == 1
        assert saved.output == "single run"

    assert calls["count"] == 1
