# Milestone 1 — Foundation

Read `docs/architecture.md`, `docs/event-model.md`, `docs/product-scope.md`, and `docs/ui-guidelines.md` before modifying code.

## Goal
Create the minimal production-shaped foundation for Agent Runtime without implementing later product features prematurely.

## Deliverables
- FastAPI backend skeleton with modular internal boundaries.
- PostgreSQL connection/configuration and migrations.
- Core OLTP models needed now: project, workflow configuration/reference, policy placeholder, replay request placeholder, approval placeholder.
- Environment/config handling suitable for local dev.
- OTel Collector local configuration stub wired toward Agent Runtime ingestion.
- Databricks configuration abstraction/interfaces only where needed to support the next milestone; do not build the full pipeline yet.
- Next.js/React/TypeScript frontend shell matching the documented navigation and dark infrastructure design system.
- Shared UI primitives sufficient for later screens (do not build every screen yet).
- Local developer setup, preferably Docker Compose only where it meaningfully simplifies Postgres/backend/frontend/collector startup.
- Tests for config and basic API health.

## Constraints
- Modular monolith.
- No Kafka/SQS.
- No graph DB.
- No custom agent SDK.
- No anomaly engine yet.
- No replay engine yet.
- No policy evaluation yet.

## Before implementation
Explain:
1. proposed repo structure,
2. dependency choices,
3. what is intentionally deferred.

Then implement and validate the milestone.
