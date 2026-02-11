# Vinci4D Mini LLM Task Orchestrator

A minimal, production-oriented **LLM task orchestration system** supporting:

- Immediate and scheduled execution
- Background processing with retries
- Task chaining
- Task cancellation
- Real-time UI updates via polling
- Clean separation of concerns (API / scheduler / worker)

This project is intentionally scoped to demonstrate **system design, correctness, and maintainability** rather than raw feature breadth.

---

## High-Level Architecture

┌────────────┐ HTTP ┌──────────────┐
│ Frontend │ ──────────────▶ │ FastAPI │
│ (Next.js) │ │ Backend │
└────────────┘ └──────┬───────┘

                                   DB writes / reads
                                         
                                  ┌──────────────┐
                                  │  PostgreSQL  │
                                  │   (Tasks)   │
                                  └──────────────┘
                                         
                           enqueue jobs / scheduling
                                         
    ┌──────────────┐      Redis      ┌──────────────┐
    │  Scheduler   │ ──────────────▶ │   RQ Queue   │
    └──────────────┘                 └──────┬───────┘
                                              
                                     executes tasks
                                              
                                     ┌──────────────┐
                                     │    Worker    │
                                     │  (RQ worker)│
                                     └──────────────┘

---

## Core Concepts

### Task Lifecycle

Each task progresses through a well-defined state machine:

scheduled → queued → running → completed  
└──→ failed  
└──→ cancelled


**State meanings:**

- **scheduled** – Has a future `scheduled_for`
- **queued** – Ready for execution
- **running** – Actively executed by a worker
- **completed** – Successfully finished
- **failed** – Retries exhausted
- **cancelled** – User-initiated terminal state

All state transitions are **persisted in PostgreSQL** and treated as the **single source of truth**.

---

## Features

### 1. Immediate & Scheduled Tasks

- Tasks without `scheduled_for` are queued immediately
- Future tasks are picked up by a **dedicated scheduler process**
- Scheduler uses `FOR UPDATE SKIP LOCKED` to prevent double execution

---

### 2. Background Execution

- Implemented using **Redis + RQ**
- Workers are **stateless and idempotent**
- Safe to scale horizontally

---

### 3. Retries

- Configurable `max_attempts`
- `attempts` increment only when execution starts
- Retry logic lives **inside the worker**, not RQ

---

### 4. Task Chaining

- Child tasks inherit the parent task’s output
- Enforced constraint: **parent must be completed with output**
- Scheduling rules apply to chained tasks as well

---

### 5. Task Cancellation

- Supported for **scheduled, queued, and running** tasks
- **scheduled / queued** → never executed
- **running** → best-effort cancellation
- Cancellation is **idempotent and terminal**

---

### 6. Frontend (Next.js)

- Live polling **only while tasks are active**
- Immediate optimistic UI updates
- Clear task status visualization
- Chain + cancel controls in task detail view

---

## Technology Stack

### Backend

- **FastAPI** – REST API
- **SQLAlchemy 2.0** – ORM
- **PostgreSQL 16** – Persistence
- **Alembic** – Schema migrations
- **Redis + RQ** – Background jobs
- **Docker Compose** – Local orchestration

### Frontend

- **Next.js (App Router)**
- Client-side polling
- No external UI libraries (intentional simplicity)

---

## Codebase Walkthrough (Backend + Frontend)

This section explains the **flow of the system** and what each major file is responsible for, so reviewers can quickly map the architecture to the implementation.

---

### Backend (`backend/app`)

**Request → Database → Queue → Worker → Database → UI polling**

#### API Layer

- **`backend/app/main.py`**
  - FastAPI application entrypoint.
  - Defines all HTTP endpoints:
    - create task
    - list tasks
    - get task
    - chain task
    - retry task
    - cancel task
  - Enqueues tasks that should run immediately.
  - Leaves scheduled tasks for the scheduler to enqueue later.

- **`backend/app/schemas.py`**
  - Pydantic request/response models.
  - Defines the API contract used by the frontend.
  - Provides validation and OpenAPI documentation.

#### Persistence Layer

- **`backend/app/models.py`**
  - SQLAlchemy ORM models.
  - Defines the `Task` table and `TaskStatus` enum.
  - `status` is the single source of truth for task lifecycle.

- **`backend/app/crud.py`**
  - Encapsulates all database operations.
  - Normalizes timestamps to UTC.
  - Determines initial task status (`scheduled` vs `queued`).
  - Implements safe, idempotent task cancellation.

- **`backend/app/db.py`**
  - Database engine and session management.
  - Provides `SessionLocal` and `get_db` dependency.

#### Background Processing

- **`backend/app/scheduler.py`**
  - Dedicated scheduler loop.
  - Periodically scans for due tasks (`scheduled_for <= now`).
  - Uses `FOR UPDATE SKIP LOCKED` to safely claim tasks.
  - Transitions tasks from `scheduled → queued` before enqueueing.

- **`backend/app/jobs.py`**
  - RQ worker entrypoint (`execute_task`).
  - Executes the LLM call.
  - Handles retries, failures, and best-effort cancellation.
  - Ensures idempotency by checking terminal states.

- **`backend/app/worker.py`**
  - Defines the Redis/RQ queue used by the API and scheduler.

- **`backend/app/llm.py`**
  - LLM client abstraction.
  - Uses a mock provider for this assignment.
  - Single integration point for swapping real providers later.

#### Migrations

- **`backend/alembic/versions/*`**
  - Alembic migration scripts.
  - Includes explicit enum migration for adding `cancelled` to `TaskStatus`.

---

### Frontend (`frontend/src/app`)

**UI → API fetch → render → poll while active**

- **`frontend/src/app/page.tsx`**
  - Home page.
  - Create tasks (immediate or scheduled).
  - Displays task list and status.
  - Polls only while tasks are active.

- **`frontend/src/app/tasks/[id]/pageToRoute.tsx`**
  - Next.js route wrapper.
  - Extracts task ID from URL and renders the client component.

- **`frontend/src/app/tasks/[id]/TaskDetailClient.tsx`**
  - Task detail view.
  - Shows metadata, prompt, output, and errors.
  - Allows chaining tasks with optional scheduling.
  - Polls task state while active.
  - Supports retry and cancellation actions.

---

## Database Design

### Tasks Table

Key fields:

- `status` → PostgreSQL ENUM  
  (`scheduled | queued | running | completed | failed | cancelled`)
- `scheduled_for` → timezone-aware UTC timestamp
- `attempts / max_attempts` → retry control
- `parent_task_id` → self-referential FK for chaining

### Why PostgreSQL ENUM?

- Strong data integrity
- Explicit lifecycle constraints
- Migration-backed evolution (e.g. adding `cancelled`)

---

## Scheduler Design

- Runs as a **separate container**
- Polls every `POLL_SECONDS`
- Claims tasks atomically using row-level locking
- Enqueues jobs **only after DB commit**
- Safe to run multiple schedulers concurrently

---

## Worker Design

- Stateless, idempotent execution
- Checks for cancellation:
  - before execution
  - after LLM generation
- Does **not** rely on RQ retry semantics
- Database status is authoritative

---

## API Endpoints

### Health
GET /health


### Create Task
POST /tasks


### List Tasks
GET /tasks


### Get Task
GET /tasks/{id}


### Chain Task
POST /tasks/{id}/chain


### Retry Failed Task
POST /tasks/{id}/retry


### Cancel Task
POST /tasks/{id}/cancel


All endpoints are automatically documented via **Swagger UI**.

---

## Running Locally

Build and start all services using Docker Compose:

```bash
docker compose up -d --build
```

## Services Started
The following containers will be launched:

backend – FastAPI API server

scheduler – Delayed task scheduler

worker – RQ background worker

postgres – PostgreSQL database

redis – Redis queue backend

## Testing
#### API (curl)
List all tasks:

curl http://localhost:8000/tasks
#### UI
Visit the frontend in your browser:

http://localhost:3000

### From the UI you can:

Create tasks

Schedule tasks

Cancel tasks

Chain tasks

### Database Access
Connect directly to PostgreSQL:

docker compose exec postgres psql -U app -d app
Migrations
Alembic handles all schema changes.

Run all migrations:

docker compose exec backend alembic upgrade head
Enum changes (such as adding cancelled) are handled explicitly using:

ALTER TYPE ... ADD VALUE  

### Design Decisions & Tradeoffs
Why polling instead of WebSockets?  

- Simpler implementation

- Deterministic behavior

- Adequate for task-oriented workloads

- Easy to reason about during interviews

### Why RQ instead of Celery?
Lightweight

Explicit control over retries

Easier mental model for take-home scope

Why a separate scheduler?
Clean responsibility boundaries

Enables delayed execution

Mirrors real production job systems

### Known Limitations (Intentional)
No authentication / multi-tenant support

No hard LLM cancellation (provider-dependent)

No metrics stack (Prometheus / OpenTelemetry)

No distributed tracing

These are intentionally excluded to keep the scope focused.

### What This Demonstrates
Clean architecture

Correct concurrency handling

Explicit lifecycle modeling

Production-safe background job patterns

Strong separation of concerns

Thoughtful tradeoffs

## What I’d Improve With Another Day

With additional time, I would focus on production-hardening and developer experience improvements.

### Persistence & Safety
- Add Docker volumes for PostgreSQL to persist tasks across restarts.
- Add explicit database reset / migrate scripts for local development.

### Cancellation Improvements
- Persist optional cancellation reasons.
- Integrate cooperative cancellation with LLM providers that support it.
- Surface clearer cancellation state in the UI.

### Observability
- Replace `print()` with structured logging.
- Add request IDs to correlate API and worker logs.
- Introduce metrics for task throughput, retries, and latency.

### Reliability
- Add a watchdog for stuck `running` tasks.
- Enforce maximum execution time per task.
- Improve scheduler resilience with backoff and jitter.

### UX Enhancements
- Cancel and retry buttons directly in the task list.
- Advanced filtering (status, scheduled time, chains).
- Better empty and error states.

### Authentication & Multi-Tenancy
- API keys or JWT-based authentication.
- Per-user task ownership and isolation.

### Testing
- Unit tests for lifecycle transitions.
- Integration tests for scheduler + worker flows.
- Failure and cancellation edge-case coverage.

## Author
# Joseph Mathew
Built as part of a Vinci4D Software Engineer take-home assignment.