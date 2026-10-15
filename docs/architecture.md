# Agent Runtime — Architecture Contract

## Product thesis
Agent Runtime is a framework-agnostic debugging and control plane for production AI agents.

It helps developers understand what agents did, why behavior changed, how a run differs from another run, how to safely replay/debug a run, and when the system should intervene before a risky action executes.

Tagline: **Debug the decisions, not just the code.**

## Design principles
1. Use existing infrastructure where the problem is already solved well.
2. Build only the agent-specific layer that creates product value.
3. Prefer open standards over proprietary instrumentation.
4. Keep v1 understandable and explainable; avoid unnecessary ML and distributed-system complexity.
5. Preserve raw telemetry so normalization/analysis can improve later.
6. Keep observability out of the critical path where possible.
7. Use real-time control only where immediate intervention is valuable.
8. Keep framework integrations optional; Agent Runtime must not depend on LangGraph, LangSmith, Temporal, OpenAI Agents SDK, Claude Agent SDK, or any one vendor.

---

# System architecture

```text
Agent application(s)
  ├─ LangGraph / OpenAI / Claude / Temporal / custom Python / Databricks agents
  │
  └─ OpenTelemetry instrumentation (async, non-blocking)
           ↓
     OTel Collector
           ↓
   Agent Runtime ingestion
           ↓
   Databricks Bronze
    raw OTel records
           ↓
   Databricks Silver
 normalized agent events
           ↓
  Execution Graph Builder
           ↓
   Databricks Gold
 metrics / baselines / derived analytics
           ↓
     Analysis engine
  rules + statistics + evidence
           ↓
      LLM diagnosis
           ↓
 API / replay / policies / UI
           ↓
 PostgreSQL application state
```

PostgreSQL and Databricks have distinct responsibilities:
- **PostgreSQL**: transactional application state.
- **Databricks**: telemetry history, normalization, derived metrics, behavioral analytics.

---

# Layer 1 — Instrumentation

## Decision
Use **OpenTelemetry** rather than a proprietary Agent Runtime SDK.

### Primary signal
- OTel traces/spans.
- OTel logs/events may supplement traces where useful.

### Emission
- Asynchronous/non-blocking.
- Telemetry failure should not fail the agent application.

### Why
- Open standard.
- Framework-independent.
- Compatible with existing observability systems.
- Lower long-term maintenance burden than custom adapters as the primary instrumentation mechanism.

### Constraint
Do not require users to adopt a proprietary Agent Runtime SDK just to instrument workflows.

---

# Layer 2 — Event ingestion

## Decision
Use:

```text
Application → OTel Collector → Agent Runtime ingestion
```

Do **not** add Kafka/SQS/message queue in v1.

### Rationale
The Collector already provides batching, retries, filtering, and a standard ingestion boundary. A queue adds operational complexity that is not justified by initial scale.

### Future-proofing
Keep ingestion modular so a queue can be inserted later:

```text
Collector → Queue → Processing Workers
```

if throughput, backpressure, or durability requirements justify it.

---

# Layer 3 — Event model + normalization

## Decision
Use a **hybrid model**:
- Keep OTel spans as the transport/trace primitive.
- Normalize agent behavior using a small set of standardized semantic attributes.
- Preserve framework-specific metadata as flexible attributes.

## Core semantic event types
- RUN
- AGENT_STEP
- LLM_CALL
- TOOL_CALL
- DECISION
- HANDOFF
- APPROVAL
- CHECKPOINT
- ERROR

## Core identity/trace fields
- trace_id
- span_id
- parent_span_id
- timestamp
- duration
- status
- workflow_name
- workflow_version
- environment
- agent_name
- event_type

## Tool-call semantics
Useful properties include:
- tool_name
- operation
- success
- latency
- side_effect
- replayable

### `side_effect`
Whether the action changes something outside the agent.
Examples:
- DB read: false
- send email: true
- update CRM: true
- book calendar event: true

### `replayable`
Whether Agent Runtime may safely execute the step again during debugging.

## Decision semantics
Where explicitly available from the application/framework:
- decision
- confidence
- reason / structured rationale

Do not depend on hidden chain-of-thought. Record observable decisions/metadata only.

## Principle
Use emerging OTel GenAI conventions where they fit; add Agent Runtime-specific attributes only where necessary.

---

# Layer 4 — Storage + run model

## Decision
Use a **hybrid PostgreSQL + Databricks architecture**.

## PostgreSQL — OLTP / product state
Store:
- organizations/projects
- workflows/configuration
- policies
- approvals
- replay requests
- user-facing run indexes / references
- settings
- transactional application state

## Databricks — telemetry + analytics

### Bronze
Preserve raw OTel telemetry with minimal transformation.

Goals:
- auditability
- reprocessing
- future normalization improvements
- lossless historical record

### Silver
Normalized Agent Runtime semantic events.

Responsibilities:
- schema normalization
- type casting
- deduplication
- handling late/out-of-order telemetry
- core Agent Runtime semantic fields

### Gold
Derived data for product analytics and diagnosis:
- run metrics
- agent metrics
- workflow baselines
- latency/cost/token aggregates
- retries / loops / handoffs
- execution-path summaries
- anomaly evidence

## Large payloads
Do not bloat transactional tables with very large prompts/tool outputs/documents.
Use Unity Catalog-governed object storage/Volumes for large payloads when needed, with references from structured records.

## Version metadata
Capture early:
- environment
- workflow_version
- prompt_version
- model
- git_commit (when available)
- tool/config versions where useful

---

# Layer 5 — Execution graph + metrics

## Decision
Represent each run internally as a **general directed execution graph**.

Do not use a graph database in v1.

## Sources
Build the graph from:
- normalized Silver events
- OTel span/parent relationships
- normalized handoff/tool/decision semantics

## Nodes
Possible nodes:
- agents
- LLM calls
- tool calls
- decisions
- approvals
- checkpoints

## Edges
Possible relationships:
- parent/child
- handoff
- called
- triggered
- returned_to

The graph must support:
- branching
- concurrency
- repeated transitions
- retries
- loops

## Metrics
Derive at minimum:
- run latency
- agent latency
- tool latency
- wall-clock vs summed span time
- tool-call count
- LLM-call count
- handoff count
- retry count
- loop/repeated-transition count
- token usage
- estimated cost
- errors
- approval wait time
- path length

Write useful aggregates to Gold tables.

Layer 5 reports what happened; it does not decide whether the behavior is bad.

---

# Layer 6 — Analysis + diagnosis

## Decision
Use:
- deterministic rules
- statistical baselines
- evidence-first LLM explanation

Do **not** add ML anomaly detection to v1 architecture.

### Why no ML detector
Most important anomalies are straightforward and explainable:
- excessive retries
- loops
- unusual tool count
- missing expected validation
- cost spikes
- latency spikes
- stuck approvals
- unexpected handoffs

Rules + statistics are easier to validate and explain. Add ML only if real product usage later reveals meaningful patterns rules/statistics cannot capture.

## Cold start / warm-up behavior
### Immediate value
From the first runs, Agent Runtime can provide rule-based insights:
- errors
- retries
- known loops
- skipped expected steps
- policy violations

### Warm-up
As more runs accumulate, Agent Runtime continuously updates workflow baselines and can provide richer comparisons:
- above-normal latency
- above-normal cost
- rare paths
- abnormal transition/tool usage

Do not hard-code an artificial fixed warm-up count. Expose confidence/coverage as data accumulates.

## Baseline scope
Start with:
- workflow
- environment

Add finer dimensions such as workflow/model/prompt versions only when needed to prevent baseline mixing.

## Diagnosis architecture

```text
Execution graph
+ metrics
+ historical baseline
+ triggered rules
        ↓
Evidence package
        ↓
LLM explanation
```

The LLM must explain evidence, not independently guess root cause.

Clearly distinguish:
- observed facts
- likely cause / inference
- impact
- suggested investigation / next steps

## Timing
Deep diagnosis is primarily **post-run** in v1.

Real-time intervention belongs to Layer 8 and should use fast deterministic rules rather than full diagnosis.

---

# Layer 7 — Replay + Runtime Diff

## Decision
Agent Runtime implements **debugging replay**, not perfect deterministic historical reproduction.

Goal:
> Given saved state, what happens if we rerun from here with a changed prompt/model/tool/configuration?

## Replay capability model
Different integrations may support different capabilities:
1. Compare completed runs only.
2. Full rerun from the beginning.
3. Semantic checkpoint replay from the middle of the workflow.

Do not expose these as "levels" in the user-facing product unless useful; this is an architecture capability model.

## Checkpoints
Use semantic checkpoints around meaningful workflow boundaries.
Prefer framework-native checkpoint/persistence support when available (e.g. LangGraph/Temporal). Fall back to full rerun where checkpoint replay is not supported.

## Tool replay modes
Support three modes:
1. **Re-execute safe tools**
2. **Reuse prior outputs**
3. **Dry-run/mock side effects**

Side-effecting operations must not be blindly re-executed during debugging.

## Runtime Diff
Compare three categories:

### Configuration
- prompt version
- model
- workflow version
- tool/config version
- git commit where available

### Execution behavior
- nodes/steps added or removed
- tool calls
- handoffs
- decisions
- retries
- loops
- path length
- sequence/transition differences

### Outcomes
- latency
- cost
- tokens
- success/failure
- evaluation/result quality when available

Use simple structural/sequence comparison first. Do not introduce complex graph-edit algorithms unless product needs justify them.

---

# Layer 8 — Runtime control + developer experience

## Runtime control
Use a **hybrid control model**.

### Out-of-band
Normal observability/telemetry stays out of the critical path.

### Inline
Sensitive or consequential actions can call a fast Agent Runtime policy check before execution.

## Policy engine
Deterministic rule-based v1 engine.

Supported actions:
- ALLOW
- BLOCK
- PAUSE
- REQUIRE_APPROVAL

Useful policy conditions:
- agent/tool/operation
- permission scope
- side_effect
- confidence
- current run cost
- tool-call count
- retry count
- repeated transition/loop count

## Fail behavior
Fail-open vs fail-closed must be configurable by policy/action sensitivity.

Examples:
- low-risk read-only search → may fail open
- destructive production write → fail closed

## Human approval
Flow:

```text
Agent proposes action
→ policy match
→ pause
→ human reviews action/context/confidence
→ approve or reject
→ resume or stop
```

## Do not implement in v1
- autonomous prompt rewriting
- automatic model switching
- self-healing workflows
- automatic agent rerouting

---

# Developer UI / UX contract

## Product feel
The UI should feel like modern infrastructure software without becoming intimidating.

Keywords:
- polished
- dark-mode-first
- professional
- calm
- high information density, but progressive disclosure
- intuitive
- minimal learning curve
- enterprise-ready

Avoid:
- dense notebook-like experiences
- hidden essential actions
- dashboards full of low-value charts
- configuration-heavy workflows for common tasks

## Core navigation
- Overview
- Runs
- Policies
- Approvals
- Compare
- Settings

## Main product workflow

```text
Find suspicious run
→ inspect execution graph
→ read diagnosis
→ compare / replay
→ evaluate improvement
```

## Overview
Show only high-signal information:
- active/total runs
- success rate
- avg latency
- cost
- run activity trend
- recent runs
- pending approvals
- recent alerts
- system health

## Runs
Filterable run table with:
- status
- run ID
- workflow
- environment
- start time
- duration
- tool calls
- cost
- anomalies
- actions

Statuses include:
- Succeeded
- Running
- Failed
- Paused
- Awaiting approval

## Run details
Primary screen for debugging.
Include:
- execution graph
- run metadata
- metrics
- diagnosis
- step/timeline view
- raw events/traces access
- Compare
- Replay

## Compare / Runtime Diff
Show:
- original vs replay
- config differences
- metric deltas
- execution-path changes
- trace/step differences
- behavioral summary
- replay mode

## Approvals
Must feel actionable, not like a generic notification center.
Show:
- action proposed
- workflow/agent/run
- risk category
- confidence
- side-effect class
- time waiting
- Approve / Reject / View details

Global notification bell should surface pending approvals and important alerts.

## Policies
Simple, readable rule builder.
Prefer human-readable expressions such as:

```text
WHEN side_effect = true
AND confidence < 0.70
THEN REQUIRE_APPROVAL
```

Include:
- scope
- active/inactive state
- fail-open/fail-closed
- recent matches/activity
- affected agents/tools

## UI implementation principles
- consistent spacing and card system
- restrained accent colors
- status color semantics consistent everywhere
- use progressive disclosure for raw telemetry
- keyboard-friendly search/navigation
- API-first backend; UI is a client of stable APIs
- desktop-first v1, responsive enough not to break at smaller widths

---

# Technology direction

These are defaults, not excuses to over-engineer.

- Backend: Python + FastAPI
- App architecture: modular monolith
- OLTP: PostgreSQL
- Telemetry analytics: Databricks Delta / Bronze-Silver-Gold
- Large telemetry payloads: Unity Catalog Volumes/object storage when justified
- Instrumentation: OpenTelemetry
- Ingestion: OTel Collector → Agent Runtime
- Frontend: Next.js / React / TypeScript
- Agent framework support: framework-agnostic
- LangGraph: optional integration
- LangSmith: optional benchmark/integration, not a dependency
- Temporal: selective use for durable workflows/checkpoint semantics where it adds value

---

# Explicit non-goals for v1

Do not build:
- proprietary instrumentation SDK as a requirement
- custom distributed queue
- Kafka/SQS unless scale requires it later
- custom workflow engine
- a Temporal replacement
- a LangGraph replacement
- a LangSmith clone
- graph database
- microservice fleet
- ML anomaly detector
- autonomous self-healing/remediation
- generic log-management/APM platform

---

# Architecture review rule

Before adding any new component, answer:
1. What concrete problem does it solve?
2. Is this already solved well by an existing tool?
3. Does the current scale require it?
4. Does it preserve the architecture contract above?
5. Can it be added behind an existing interface later instead?

If the answer is weak, do not add it.
