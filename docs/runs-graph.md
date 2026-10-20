# Runs, Execution Graph, and Gold Contract

PostgreSQL is not used for telemetry, graph, or metric records.

## Logical run identity and status

When telemetry supplies all three values, a logical run is grouped by the stable tuple:

```text
(project_id, workflow_name, external_run_id)
```

The public `run_id` is a deterministic SHA-256-derived identifier for that tuple. Including project
and workflow prevents identical external IDs from merging unrelated workflows or tenants. A logical
run may contain any number of OTel traces. Every event and graph node retains its original
`trace_id`, `span_id`, and `parent_span_id`.

If any grouping field is absent or inconsistent inside a trace, that trace keeps the backward-
compatible behavior: its `trace_id` is the `run_id` and it is not merged with another trace. This is
an additive projection; Bronze and Silver records are not destructively migrated.

Execution time is authoritative. Events are sorted by timestamp and span ID as a stable tie-breaker.
Arrival timestamps and out-of-order flags never determine graph order. A run fails when any member
trace contains an `ERROR` event or error-status span. Otherwise it succeeds unless telemetry
declares an explicit `agent.runtime.run.status`.

## Directed graph

Each Silver event remains a distinct node. Nodes carry trace/span identity, semantic type,
execution interval, agent, status, depth, concurrency lane, and retry metadata. Edges are typed:

- `parent_child`: a real OTel parent relationship, resolved only within the same trace;
- `handoff`: a declared handoff to the first following event owned by its destination agent;
- `retry`: a prior matching semantic operation to an explicitly indexed retry;
- `repeated_transition`: a prior occurrence of the same semantic operation to its recurrence.

Agent Runtime never fabricates a parent/child edge across traces. Timestamp order provides a
coherent presentation across member traces without claiming causality. Branches remain sibling
nodes. Overlapping intervals are marked concurrent and assigned presentation lanes. Semantic edges
may make the representation cyclic, so `path_length` is the maximum real OTel parent depth,
including the root, rather than a longest path through every semantic edge.

## Gold run record

The Gold projection contains logical identity, all member `trace_ids`, the graph,
execution-ordered Silver event snapshots, and:

- wall-clock duration from earliest start to latest end across all member traces;
- summed `AGENT_STEP` and `TOOL_CALL` latency;
- tool, LLM, retry, handoff, repeated-transition, and error counts;
- input, output, and total tokens only when declared;
- cost only when telemetry declares a cost attribute;
- approval event wait time, preferring a declared wait value and otherwise using span duration;
- parent-depth path length and non-`RUN` step count.

Numeric absence remains null. In particular, an unreported token count or cost is not projected as
zero. Version-like semantic attributes are normalized to strings before baseline scopes and Diff
configuration keys are constructed.

Local development persists an atomic `gold-runs.jsonl` snapshot beside Bronze and Silver JSONL.
Tests use the in-memory adapter. Production delegates Silver queries and Gold Delta merges to the
credential-aware Databricks writer supplied by deployment composition.

## API

- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/graph`
- `GET /api/v1/runs/{run_id}/metrics`
- `GET /api/v1/runs/{run_id}/events`

The list accepts `status`, `workflow`, `environment`, `limit`, and `offset`. Existing single-trace
clients keep the same endpoints and trace-based IDs. Grouped-run responses add `trace_ids` and
`external_run_id`; `trace_id` remains as the representative trace for compatibility.
