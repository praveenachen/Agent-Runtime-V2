# Runs, Execution Graph, and Gold Contract

This contract implements Milestone 3 on top of the Silver telemetry contract. PostgreSQL is not
used for telemetry, graph, or metric records.

## Run boundary and status

A v1 run is the set of supported Silver events with one OpenTelemetry `trace_id`. The trace ID is
also the stable `run_id`. A `RUN` event supplies preferred run metadata; when it is absent, the
earliest event supplies metadata and the full event interval supplies the boundary.

Execution time is authoritative. Events are sorted by timestamp and span ID as a stable tie-breaker.
Arrival timestamps and out-of-order flags never determine graph order. A run fails when it contains
an `ERROR` event or error-status span. Otherwise it succeeds unless telemetry declares an explicit
`agent.runtime.run.status`.

## Directed graph

Each Silver event remains a distinct node. Nodes carry span identity, semantic type, execution
interval, agent, status, depth, concurrency lane, and retry metadata. Edges are typed:

- `parent_child`: direct OTel parent-span relationship;
- `handoff`: a handoff event to the first following event owned by its destination agent;
- `retry`: a prior matching semantic operation to an explicitly indexed retry;
- `repeated_transition`: a prior occurrence of the same semantic operation to its recurrence.

Branches are preserved as sibling nodes. Overlapping intervals are marked concurrent and assigned
separate presentation lanes; the system does not invent an ordering edge between them. Semantic
edges may make the representation cyclic, so v1 `path_length` is the maximum OTel parent depth,
including the root, rather than a longest path through every semantic edge.

## Gold run record

The Gold record contains run metadata, the graph, execution-ordered Silver event snapshots, and:

- wall-clock duration from earliest start to latest end;
- summed `AGENT_STEP` and `TOOL_CALL` latency;
- tool, LLM, retry, handoff, repeated-transition, and error counts;
- input, output, and total tokens when declared;
- cost only when telemetry declares a cost attribute;
- approval event wait time, preferring a declared wait value and otherwise using span duration;
- parent-depth path length and non-`RUN` step count.

Local development persists an atomic `gold-runs.jsonl` snapshot beside Bronze and Silver JSONL.
Tests use the in-memory adapter. Production delegates Silver queries and Gold Delta merges to the
credential-aware Databricks writer supplied by deployment composition.

## API

- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/graph`
- `GET /api/v1/runs/{run_id}/metrics`
- `GET /api/v1/runs/{run_id}/events`

The list accepts `status`, `workflow`, `environment`, `limit`, and `offset`. The detail response is
the convenient aggregate used by the UI; the focused graph, metric, and event routes remain stable
boundaries for other clients.
