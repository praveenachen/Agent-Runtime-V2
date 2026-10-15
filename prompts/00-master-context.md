# Prompt 0 — Repository + Architecture Bootstrap

You are implementing **Agent Runtime**, a framework-agnostic debugging and control plane for production AI agents.

Before changing code:
1. Read all files under `docs/`, especially `docs/architecture.md`.
2. Inspect the existing repository completely enough to understand its current structure, dependencies, and any existing implementation.
3. Summarize what already exists and identify conflicts with the architecture contract.
4. Propose the smallest repository structure and implementation sequence consistent with the documented decisions.
5. Do not add infrastructure or dependencies that are not justified by the architecture contract.

## Fixed architecture decisions
Treat these as constraints unless you explicitly stop and explain why a change is necessary:
- OpenTelemetry traces/spans are the primary instrumentation standard.
- Telemetry emission is async/non-blocking.
- OTel Collector feeds Agent Runtime directly in v1; no Kafka/SQS/message queue.
- Agent semantics extend OTel rather than replacing it with a proprietary SDK.
- PostgreSQL is OLTP/application state.
- Databricks is telemetry/history analytics using Bronze/Silver/Gold.
- Large payloads may use Unity Catalog Volumes/object storage when justified.
- Runs are represented as directed execution graphs.
- No graph DB in v1.
- Diagnosis uses deterministic rules + statistical baselines + evidence-backed LLM explanation.
- No ML anomaly detector in v1.
- Deep diagnosis is post-run.
- Real-time checks are deterministic guardrails only.
- Replay is debugging replay, not exact historical reproduction.
- Replay supports: re-execute safe tools, reuse prior outputs, dry-run/mock side effects.
- Runtime Diff compares config, execution behavior, and outcomes.
- Runtime control actions are ALLOW/BLOCK/PAUSE/REQUIRE_APPROVAL.
- Modular monolith, not microservices.
- API-first backend.

## Technology defaults
Unless the repository already has a compelling equivalent:
- Python + FastAPI backend
- PostgreSQL
- Databricks / Delta for telemetry pipeline
- OTel Collector
- Next.js + React + TypeScript frontend

## Non-goals
Do not build or introduce:
- proprietary instrumentation SDK as a requirement
- custom workflow engine
- Kafka/SQS in v1
- graph database
- microservices
- ML anomaly detection
- self-healing/autonomous remediation
- LangSmith/LangGraph/Temporal replacements

## Working style
For every milestone:
1. Understand current code.
2. Propose the smallest design.
3. Identify tradeoffs/assumptions.
4. Implement.
5. Add tests.
6. Run tests/lint/type checks where available.
7. Summarize files changed and technical debt/known limitations.

Do not implement the entire product in this prompt. Establish the repository structure, shared conventions, local development setup, and architecture scaffolding needed for Milestone 1 only.
