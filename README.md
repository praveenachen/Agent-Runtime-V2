# Agent Runtime V2

> **Debug the decisions, not just the code.**

Agent Runtime is a framework-agnostic debugging and control plane for production AI agents. It
turns OpenTelemetry spans into a semantic execution graph, evidence-first diagnosis, safe replay
metadata, runtime comparisons, and optional policy checks for consequential actions.

Traditional traces show services and latency. Agent workflows also need answers to different
questions: Which agent made a decision? Which tool was called? What changed between two workflow
versions? Did an approval authorize exactly the action that was retried? Agent Runtime adds that
agent-specific layer without becoming the workflow engine.

The primary demo uses real telemetry emitted by [Relay](https://github.com/praveenachen/Relay-2.0):
a COLLABORATE workflow that crosses several HTTP requests and therefore several OTel traces, while
remaining one logical Agent Runtime run.

## What it does

- Groups multiple OTel traces into one logical run using
  `(project_id, workflow_name, external_run_id)` while preserving every original trace and span.
- Builds semantic graphs for `RUN`, `AGENT_STEP`, `LLM_CALL`, `DECISION`, `APPROVAL`, `TOOL_CALL`,
  `HANDOFF`, `CHECKPOINT`, and `ERROR` events.
- Aggregates declared latency, token, cost, retry, tool, and error metrics. Missing metrics remain
  absent; Agent Runtime never turns “not emitted” into zero.
- Produces evidence-first diagnosis from observed facts, deterministic rules, and scoped historical
  baselines. Inferences are labeled as inferences.
- Compares configuration, execution structure, and outcomes between completed logical runs.
- Plans debugging replay with explicit tool safety modes and integration capability boundaries.
- Evaluates optional deterministic runtime policies and binds approvals to an immutable,
  sanitized action context so an approved retry does not create another approval.

Agent Runtime does **not** replace LangGraph, Temporal, or an application’s workflow engine. It is
framework-agnostic; OpenTelemetry is the instrumentation boundary. It captures observable events
and structured rationale supplied by the application, never hidden chain-of-thought. Replay is a
debugging tool, not a guarantee of deterministic historical reproduction.

## Architecture

```mermaid
flowchart LR
    A[Agent application<br/>Relay, LangGraph, Temporal, custom] -->|OTel traces| C[OTel Collector]
    C --> I[FastAPI ingestion]
    I --> B[Bronze<br/>redacted raw telemetry]
    B --> S[Silver<br/>normalized semantic events]
    S --> G[Gold<br/>logical runs, graph, metrics]
    G --> D[Diagnosis, Diff, Replay metadata]
    D --> U[API + Next.js UI]
    P[(PostgreSQL<br/>policies, approvals, replay requests)] <--> U
    A -. optional pre-action check .-> P
```

The local adapter stores Bronze, Silver, and Gold JSONL on a Docker volume. The production storage
boundary supports Databricks; PostgreSQL remains reserved for transactional control-plane state.
See the [architecture contract](docs/architecture.md),
[telemetry pipeline](docs/telemetry-pipeline.md), and [run/graph contract](docs/runs-graph.md).

## Relay integration

Relay owns workflow state, product approval, provider execution, idempotency, and artifacts. Agent
Runtime observes its OTel telemetry and can optionally make a deterministic policy decision just
before a selected provider write.

```mermaid
sequenceDiagram
    participant R as Relay COLLABORATE
    participant O as OTel Collector
    participant A as Agent Runtime
    participant H as Human reviewer
    participant P as Provider

    R->>O: spans from request/trace 1
    R->>O: spans from request/trace 2
    O->>A: OTLP export
    Note over A: group by project + workflow + external run ID
    A-->>A: preserve trace IDs and within-trace parents
    R->>A: optional policy check before queued action
    A-->>R: REQUIRE_APPROVAL
    H->>A: approve immutable action context
    R->>A: manual retry with same control reference
    A-->>R: ALLOW via existing approved approval
    R->>P: execute only the queued action
```

No cross-trace parent/child edges are invented. Events across traces are presented by execution
timestamp. See Relay’s
[Agent Runtime V2 demo guide](https://github.com/praveenachen/Relay-2.0/blob/main/docs/demos/agent-runtime-v2.md)
for the full two-repository setup and fixtures.

## OpenTelemetry integration

Send standard OTLP spans to the Collector and add the small semantic layer used by Agent Runtime.
Every trace that belongs to the same long-lived workflow should carry the same three grouping
attributes.

```python
from opentelemetry import trace

tracer = trace.get_tracer("relay.collaborate")

with tracer.start_as_current_span(
    "collaborate.plan_actions",
    attributes={
        "agent.runtime.event_type": "DECISION",
        "agent.runtime.project.id": "11111111-1111-4111-8111-111111111111",
        "agent.runtime.workflow.name": "project_meeting",
        "agent.runtime.workflow.version": "2",
        "agent.runtime.prompt.version": "review-request-v2",
        "agent.runtime.external_run_id": str(workflow_run_id),
        "agent.runtime.decision": "queue_provider_actions",
    },
):
    plan_actions()
```

Configure the SDK for the local Collector, for example
`OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` with OTLP/HTTP. Do not put secrets, full
prompts, transcripts, provider payloads, or hidden reasoning in span attributes.

## Run locally

Requirements: Docker with Compose. Copy `.env.example` to `.env` (`Copy-Item .env.example .env` on
PowerShell), then start PostgreSQL, the backend, frontend, and OTel Collector:

```bash
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose ps
```

| Service | Local address |
| --- | --- |
| Frontend | http://localhost:3000 |
| API / OpenAPI | http://localhost:8000 / http://localhost:8000/docs |
| Backend health | http://localhost:8000/api/v1/health |
| OTLP gRPC / HTTP | `localhost:4317` / `http://localhost:4318` |
| Collector health | http://localhost:13133 |
| PostgreSQL | `localhost:5432` |

To stop the stack without deleting its data, run `docker compose down`.

### Backend and frontend development

Start PostgreSQL with `docker compose up -d postgres`, then run the backend from `backend/`:

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
$env:AGENT_RUNTIME_DATABASE_URL="postgresql+psycopg://agent_runtime:agent_runtime@localhost:5432/agent_runtime"
$env:AGENT_RUNTIME_TELEMETRY_LOCAL_PATH=".data/telemetry"
.venv\Scripts\alembic upgrade head
.venv\Scripts\uvicorn agent_runtime.main:app --reload
```

Run the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

The Collector is already configured in `infra/otel-collector/config.yaml`; the all-Compose path is
the simplest way to run it against the containerized backend. Relay’s demo guide includes a
Compose override that avoids port conflicts when both repositories run together.

## Three-to-five-minute demo

1. **Healthy run:** complete Relay’s COLLABORATE fixture, find its WorkflowRun UUID in Runs, and
   open Run Detail. Show the multi-trace identity, semantic graph, timeline, and declared metrics.
2. **Controlled failure:** open the Relay fixture with the real mock-provider `ERROR` span. Show the
   failed node and diagnosis, separating observed evidence from inferred cause.
3. **Runtime Diff:** emit Relay’s V1/V2 comparison fixtures and compare them. Show workflow/prompt
   version changes and the added semantic execution step. Point out that missing token/cost values
   display as `—`, not zero.
4. **Runtime Control:** trigger `REQUIRE_APPROVAL`, approve the action, then manually retry it in
   Relay with the same control reference. The existing approval authorizes that immutable action;
   no duplicate approval is created and Agent Runtime does not resume the workflow itself.

The timed presenter script and exact verification checklist are in [docs/demo.md](docs/demo.md).

## Example policy

This rule requires review for any action Relay declares to have an external side effect:

```json
{
  "project_id": "11111111-1111-4111-8111-111111111111",
  "name": "Review provider writes",
  "enabled": true,
  "priority": 10,
  "action": "REQUIRE_APPROVAL",
  "conditions": { "side_effect": true },
  "fail_closed": true
}
```

Create it with `POST /api/v1/policies`. Policy evaluation is optional and inline; normal telemetry
export stays out of the application’s critical path. Approval continuation is server-side lookup,
not a bearer approval credential. The caller retains its checkpoint and retries manually.

## Design decisions

- **Standards-first:** OTel transports telemetry; no proprietary instrumentation SDK is required.
- **Logical run, physical traces:** stable application identity groups long-lived workflows without
  erasing trace identity or fabricating causal edges.
- **Evidence before explanation:** deterministic facts and baselines are assembled before an LLM
  explanation provider is asked to summarize them.
- **Honest absence:** unknown cost or token usage remains null throughout storage, APIs, Diff, and UI.
- **Narrow control plane:** optional policy checks protect selected actions; workflow orchestration
  remains with Relay, LangGraph, Temporal, or the application.
- **Safe replay boundary:** adapters declare capabilities and side-effect behavior explicitly.

## Tradeoffs and limitations

- Local JSONL telemetry storage is intended for development and demonstration, not multi-writer
  production durability or scale.
- The default diagnosis provider is deterministic. Richer LLM explanation requires an explicitly
  configured provider and is still constrained to the evidence package.
- Baseline quality grows with comparable run history; low coverage is reported rather than hidden.
- Replay support depends on the connected runtime adapter. Compare-only is always meaningful, but
  full rerun or checkpoint replay may be unavailable.
- Debugging replay cannot guarantee identical external data, model output, or provider behavior.
- The local project authorizer is permissive; production identity, RBAC, and tenancy enforcement are
  deployment integration work.
- Agent Runtime does not capture hidden chain-of-thought and should not receive secrets or raw
  sensitive payloads as telemetry or approval context.
- Approval does not automatically resume Relay. The caller must retry the same queued action with
  the same immutable control identity before the approval expires.

## Repository map and checks

```text
backend/                 FastAPI, domain modules, SQLAlchemy, Alembic, tests
frontend/                Next.js App Router control-plane UI
infra/otel-collector/    Local OTLP receiver/exporter configuration
docs/                    Architecture, contracts, and demo guide
compose.yaml             PostgreSQL/API/UI/Collector stack
```

```bash
cd backend && pytest && ruff check .
cd frontend && npm run lint && npm run typecheck && npm run build
```
