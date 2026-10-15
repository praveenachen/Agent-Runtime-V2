# Agent Runtime

Framework-agnostic debugging and control plane for production AI agents.

> Debug the decisions, not just the code.

This repository contains the Milestone 6 core architecture: a FastAPI modular monolith,
PostgreSQL application-state schema, OpenTelemetry Collector, OTLP trace ingestion,
Bronze/Silver telemetry contracts, Gold run projections, directed execution graphs,
derived metrics, evidence-first diagnosis, safe replay planning, Runtime Diff, deterministic
runtime policies, human approvals, and a Next.js control-plane UI. The architecture
contract remains authoritative in [`docs/architecture.md`](docs/architecture.md).

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
- Agent Runtime OTLP/HTTP endpoint: `POST /api/v1/telemetry/otlp/v1/traces`

Local telemetry is written to the `telemetry-data` volume as redacted Bronze and
normalized Silver JSONL plus derived Gold run JSONL. Production uses the Databricks
adapter boundary described in [`docs/telemetry-pipeline.md`](docs/telemetry-pipeline.md)
and [`docs/runs-graph.md`](docs/runs-graph.md).
The analysis contract is documented in
[`docs/analysis-diagnosis.md`](docs/analysis-diagnosis.md).
Replay safety and deterministic comparison are documented in
[`docs/replay-diff.md`](docs/replay-diff.md).
Runtime control and approval semantics are documented in
[`docs/runtime-control.md`](docs/runtime-control.md).

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

Milestone 6 adds project-scoped deterministic policy evaluation, persisted decisions, approval
state and audit history, and optional resume/stop adapter boundaries. The default adapter does not
orchestrate workflows. ML decisions, inline diagnosis, autonomous remediation, model switching,
prompt rewriting, and full RBAC remain outside the core architecture.
