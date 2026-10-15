# Milestone 6 — Runtime Policies + Approvals

## Goal
Add fast deterministic intervention for actions where waiting until post-run diagnosis is too late.

## Control model
- telemetry/observability stays out-of-band
- sensitive actions use an inline policy evaluation endpoint/hook

## Actions
- ALLOW
- BLOCK
- PAUSE
- REQUIRE_APPROVAL

## Deliverables
- deterministic policy model stored in Postgres
- rule evaluator supporting initial conditions such as:
  - agent/tool/operation
  - side_effect
  - confidence
  - current cost
  - tool-call count
  - retry count
  - repeated-transition count
- configurable fail-open/fail-closed behavior per policy
- approval lifecycle:
  - create request
  - pending
  - approve/reject
  - resume/stop integration boundary
- notification count/events for pending approvals
- Approvals + Policies UI matching `docs/ui-guidelines.md`
- audit history for policy decisions and approval outcomes

## Constraints
- no LLM in the critical policy decision path
- no autonomous prompt rewrite/model switch/reroute/self-healing
- policy checks must be fast and deterministic

## Tests
Cover:
- allow
- block
- pause
- require approval
- fail-open
- fail-closed
- approval resolution
