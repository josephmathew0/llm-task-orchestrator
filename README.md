# Vinci4D Mini LLM Task Orchestrator

Minimal LLM task orchestration system with:

- Immediate and scheduled execution
- Background workers with retry logic
- Task chaining from parent output
- Best-effort cancellation
- Next.js UI with live polling

This repo is intentionally scoped for system design clarity over feature breadth.

## Architecture

```text
Frontend (Next.js)
        |
        v
   FastAPI API  -----> PostgreSQL (task state source of truth)
        |
        v
   Redis / RQ Queue <----- Scheduler (moves due scheduled tasks to queue)
        |
        v
      Worker (executes LLM calls, persists outputs/errors)
```

## Task Lifecycle

`scheduled -> queued -> running -> completed`

Failure/termination paths:

- `running -> queued` (retry path while attempts remain)
- `running -> failed` (retries exhausted)
- `scheduled|queued|running -> cancelled` (best effort for `running`)

Status meanings:

- `scheduled`: future `scheduled_for`
- `queued`: ready for worker pickup
- `running`: active worker attempt
- `completed`: terminal success
- `failed`: terminal failure
- `cancelled`: terminal user cancellation

## Repository Map

### Backend

- `backend/app/main.py`: FastAPI routes
- `backend/app/models.py`: SQLAlchemy models and `TaskStatus`
- `backend/app/crud.py`: DB operations and lifecycle helpers
- `backend/app/jobs.py`: worker execution and retry behavior
- `backend/app/scheduler.py`: scheduled task claiming loop
- `backend/app/llm.py`: mock/openai provider abstraction
- `backend/alembic/versions`: DB migrations

### Frontend

- `frontend/src/app/page.tsx`: task list + create form
- `frontend/src/app/tasks/[id]/page.tsx`: task detail route
- `frontend/src/app/tasks/[id]/TaskDetailClient.tsx`: detail UI + chain/cancel actions

## Prerequisites

- Docker + Docker Compose
- Node.js 20+ and npm (for local frontend dev)
- Python 3.11+ (optional, only for non-Docker backend runs)

## Documentation/Delivery

### 1. Set up the database

Start infrastructure and services:

```bash
docker compose up -d --build
```

Apply migrations:

```bash
docker compose exec backend alembic upgrade head
```

### 2. Generate or compile `.proto` files

This project does not use protobuf/gRPC, so no `.proto` generation step is required.

### 3. Run the Python server

With Docker:

```bash
docker compose up -d --build backend
```

Without Docker (from `backend/`):

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Required runtime environment variables:

- `DATABASE_URL`
- `REDIS_URL`
- `LLM_PROVIDER` (`mock` or `openai`)
- `OPENAI_API_KEY` (required only when `LLM_PROVIDER=openai`)
- `OPENAI_MODEL` (optional override)

## Run Modes

### Mode A: Docker backend stack + local frontend

Start DB, Redis, API, worker, scheduler:

```bash
docker compose up -d --build
```

Start frontend separately:

```bash
cd frontend
npm install
npm run dev
```

URLs:

- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Frontend: `http://localhost:3000`

### Mode B: Backend only with Docker

```bash
docker compose up -d --build postgres redis migrate backend worker scheduler
```

Use curl/Postman against `http://localhost:8000`.

## Environment Variables

Backend defaults live in `backend/app/settings.py`.

Key variables:

- `DATABASE_URL` (default: `postgresql+psycopg://app:app@localhost:5432/app`)
- `REDIS_URL` (default: `redis://localhost:6379/0`)
- `LLM_PROVIDER` (`mock` or `openai`, default `mock`)
- `OPENAI_API_KEY` (required when `LLM_PROVIDER=openai`)
- `OPENAI_MODEL` (default: `gpt-4o-mini`)

In Docker Compose, service-level environment already points backend/worker/scheduler to container hosts.

## API Endpoints

- `GET /health`: health check
- `POST /tasks`: create immediate or scheduled task
- `GET /tasks`: list tasks (`limit`, `offset`, optional `parent_task_id`)
- `GET /tasks/{task_id}`: get one task
- `POST /tasks/{task_id}/chain`: create child task from completed parent output
- `POST /tasks/{task_id}/retry`: retry failed task
- `POST /tasks/{task_id}/cancel`: cancel task

Swagger: `http://localhost:8000/docs`

## API Quick Examples

Create immediate task:

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Summarize notes",
    "prompt": "Summarize this text in 3 bullets",
    "scheduled_for": null
  }'
```

Create scheduled task (UTC):

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Run later",
    "prompt": "Write a short status update",
    "scheduled_for": "2026-02-11T18:30:00Z"
  }'
```

List tasks:

```bash
curl "http://localhost:8000/tasks?limit=50&offset=0"
```

Retry a failed task:

```bash
curl -X POST http://localhost:8000/tasks/<task_id>/retry \
  -H "Content-Type: application/json" \
  -d '{"max_attempts": 5}'
```

Cancel a task:

```bash
curl -X POST http://localhost:8000/tasks/<task_id>/cancel
```

## Database and Migrations

Run migrations in Docker:

```bash
docker compose exec backend alembic upgrade head
```

Open psql:

```bash
docker compose exec postgres psql -U app -d app
```

## Quality Checks

Backend compile check:

```bash
python -m compileall backend/app
```

Backend tests (first run after dependency changes):

```bash
docker compose up -d --build backend
```

```bash
docker compose exec backend pytest -q
```

Alternative via compose test profile:

```bash
docker compose --profile test run --rm backend-tests
```

Frontend lint:

```bash
npm -C frontend run lint
```

## CI

Backend tests run automatically in GitHub Actions on push (main/master) and pull requests.

- Workflow: `.github/workflows/backend-tests.yml`
- Command run in CI: `pytest backend/tests -q`

## Design Choices

- Polling instead of WebSockets for simpler state sync in take-home scope
- Retry orchestration in application logic instead of RQ-native retries
- Separate scheduler process to handle delayed execution cleanly
- Postgres-backed status transitions as system source of truth

## Thoughtfulness

### Approach

- Keep task status in PostgreSQL as the single source of truth.
- Separate responsibilities by process: API, scheduler, and worker.
- Keep delayed execution explicit in scheduler logic and immediate execution explicit in API.
- Keep retry/cancel behavior in application logic so lifecycle rules remain visible and testable.

### Why this approach

- Clear boundaries reduce accidental coupling and make failure modes easier to reason about.
- DB-backed lifecycle transitions simplify observability and state recovery.
- Explicit orchestration logic is easier to review than hidden framework defaults for this scope.

## What I’d Improve With Another Day

- Add more backend integration tests around scheduler claiming and migration edge cases.
- Introduce structured logging and request/task correlation IDs.
- Add production CORS/env hardening and container health/readiness checks.
- Add CI job for frontend lint/build in addition to backend tests.
- Add basic auth/ownership model for multi-user safety.

## Current Limitations

- No auth or multi-tenant boundaries
- No hard cancellation for in-flight provider calls
- No metrics/tracing stack
- Backend tests exist, but coverage can be expanded further

## Author

Joseph Mathew  
Built as part of a Vinci4D Software Engineer take-home assignment.
