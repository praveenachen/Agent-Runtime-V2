# Milestone 3 — Runs, Execution Graph, Metrics, and Core UI

## Goal
Turn normalized events into the product's first useful debugging experience.

## Deliverables
### Backend/data
- Construct run boundaries from normalized events.
- Build a general directed execution graph from OTel relationships + Agent Runtime semantics.
- Support branching, retries, repeated transitions, and concurrent spans.
- Compute v1 run/agent metrics:
  - wall-clock duration
  - agent/tool latency
  - tool calls
  - LLM calls
  - handoffs
  - retries
  - repeated transitions/loops
  - tokens
  - estimated cost where pricing metadata is available
  - errors
  - approval wait time when available
  - path length
- Materialize useful Gold tables/outputs.
- Provide stable APIs for run list, run detail, graph, metrics, and raw-event access.

### Frontend
Implement the UI direction in `docs/ui-guidelines.md` for:
- Overview
- Runs
- Run Detail

The Run Detail screen should make the execution graph the visual focal point and provide progressive disclosure into steps/raw events.

## Constraints
- No graph database.
- No anomaly diagnosis yet beyond basic status/error display.
- Avoid fake production complexity; use synthetic seed data only where needed for UI development/testing.

## Tests
Add unit/integration tests covering graph reconstruction for:
- linear execution
- branch/concurrency
- retry
- loop/repeated transition
