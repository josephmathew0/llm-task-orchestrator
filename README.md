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

```bash
docker compose up -d --build
Services Started
backend

scheduler

worker

postgres

redis

Testing
API (curl)
curl http://localhost:8000/tasks
UI
Visit:

http://localhost:3000
You can:

Create tasks

Schedule tasks

Cancel tasks

Chain tasks

Database Access
docker compose exec postgres psql -U app -d app
Migrations
Alembic handles schema changes.

Example:

docker compose exec backend alembic upgrade head
Enum changes (such as adding cancelled) are handled explicitly using:

ALTER TYPE ... ADD VALUE
Design Decisions & Tradeoffs
Why polling instead of WebSockets?
Simpler

Deterministic

Adequate for task-oriented workloads

Easy to reason about during interviews

Why RQ instead of Celery?
Lightweight

Explicit control over retries

Easier mental model for take-home scope

Why a separate scheduler?
Clean responsibility boundaries

Enables delayed execution

Mirrors real production job systems

Known Limitations (Intentional)
No authentication / multi-tenant support

No hard LLM cancellation (provider-dependent)

No metrics stack (Prometheus / OpenTelemetry)

No distributed tracing

These are explicitly excluded to keep the scope focused.

What This Demonstrates
Clean architecture

Correct concurrency handling

Explicit lifecycle modeling

Production-safe background job patterns

Strong separation of concerns

Thoughtful tradeoffs

Author
Joseph Mathew
Built as part of a Vinci4D Software Engineer take-home assignment.