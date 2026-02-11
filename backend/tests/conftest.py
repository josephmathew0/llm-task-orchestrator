from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure `backend/app` is importable as `app` when tests run in container.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db import get_db
from app.main import app
from app.models import Base


@pytest.fixture()
def db_session_factory(tmp_path) -> Generator[sessionmaker, None, None]:
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_file}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture()
def queue_spy(monkeypatch) -> list[tuple]:
    calls: list[tuple] = []

    def fake_enqueue(fn, *args, **kwargs):
        calls.append((fn, args, kwargs))
        return None

    monkeypatch.setattr("app.main.queue.enqueue", fake_enqueue)
    monkeypatch.setattr("app.jobs.queue.enqueue", fake_enqueue)
    return calls


@pytest.fixture()
def client(db_session_factory, monkeypatch, queue_spy) -> Generator[TestClient, None, None]:
    def override_get_db():
        db: Session = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.jobs.SessionLocal", db_session_factory)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
