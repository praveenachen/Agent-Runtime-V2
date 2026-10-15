# Agent Runtime

Framework-agnostic debugging and control plane for production AI agents.

> Debug the decisions, not just the code.

This repository contains the Milestone 1 production-shaped foundation: a FastAPI
modular monolith, PostgreSQL application-state schema, OpenTelemetry Collector
configuration, a Databricks analytics port, and a Next.js dashboard shell. The
architecture contract remains authoritative in [`docs/architecture.md`](docs/architecture.md).

## Repository layout

```text
backend/                 FastAPI API, domain modules, SQLAlchemy, Alembic, tests
frontend/                Next.js App Router shell and reusable UI primitives
infra/otel-collector/    Local OTLP receiver/exporter configuration
docs/                    Architecture, event model, scope, and UI contracts
prompts/                 Sequential milestone briefs
compose.yaml             Local Postgres/API/UI/Collector stack
```

## Local development

### Docker Compose

Copy `.env.example` to `.env`, then run:

```bash
docker compose up --build
docker compose exec backend alembic upgrade head
```

- UI: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- OTLP: `localhost:4317` (gRPC) or `localhost:4318` (HTTP)

The Collector is intentionally pointed at the Milestone 2 ingestion path. Until
that endpoint exists, it can receive and retry telemetry but cannot persist it.

### Run services directly

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn agent_runtime.main:app --reload
```

Frontend (Node 20.9+):

```bash
cd frontend
npm install
npm run dev
```

## Checks

```bash
cd backend && pytest && ruff check .
cd frontend && npm run lint && npm run typecheck && npm run build
```

## Milestone boundaries

Milestone 1 defines application-state placeholders and integration boundaries.
It intentionally does not implement OTLP ingestion, Bronze/Silver/Gold jobs,
execution graphs, diagnosis, replay execution, runtime diff, policy evaluation,
or approval orchestration. Those remain ordered in `prompts/02` through `06`.
