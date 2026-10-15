# Milestone 5 — Debugging Replay + Runtime Diff

## Goal
Let developers test changes safely and compare runtime behavior.

## Replay model
Debugging replay, not exact historical reproduction.

Support capability progression:
- compare existing completed runs
- full rerun
- checkpoint replay when the underlying framework/integration supports it

## Tool replay modes
- Re-execute safe tools
- Reuse prior outputs
- Dry-run/mock side effects

## Deliverables
- Replay request/state model in Postgres.
- Semantic checkpoint abstraction.
- Adapter boundary for framework-native checkpoint/replay when available.
- Safe fallback to full rerun when checkpoint replay is unsupported.
- Side-effect-aware replay behavior using event semantics.
- Runtime Diff engine comparing:
  - configuration
  - execution sequence/structure
  - outcomes/metrics
- Simple sequence/structural diff first; no complex graph-edit algorithms.
- Compare / Runtime Diff UI matching `docs/ui-guidelines.md`.

## Safety
Never blindly repeat external side effects during debugging replay.

## Tests
Cover all three replay modes and at least one side-effecting synthetic tool.
