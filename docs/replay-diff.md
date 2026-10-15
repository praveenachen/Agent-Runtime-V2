# Replay and Runtime Diff Contract

Milestone 5 implements debugging replay planning and deterministic comparison. It does not
promise byte-for-byte historical reproduction and does not introduce a workflow engine.

## Capability model

- `compare_only` is always available for two completed Gold run records.
- `full_rerun` is available only when a configured integration adapter can submit it.
- `checkpoint_replay` additionally requires a semantic checkpoint in the source run.
- An unsupported checkpoint request falls back to full rerun only when that capability is
  supported. Otherwise the request is persisted as blocked and no execution is claimed.

Framework adapters implement a small protocol and remain optional. LangGraph, Temporal, or
another runtime can supply an adapter without becoming a core dependency. The built-in generic
adapter is planning-only.

## Semantic checkpoints

A checkpoint is a governed pointer, not an arbitrary memory snapshot. It contains run/trace/span
identity, execution timestamp, workflow/environment/version context, integration identity, and
state/input/output references. Large state remains in the integration's persistence layer or a
governed Volume/object store.

## Tool safety matrix

- Re-execute only when `replayable=true` and `side_effect=false`, or when the selected adapter
  explicitly attests that re-execution is safe.
- Reuse requires a concrete `output_ref`; missing output is blocked rather than invented.
- In dry-run mode, `side_effect=true` produces a `mock` decision with `simulated=true`.
- Missing or ambiguous safety metadata chooses reuse when a reference exists, otherwise block.

Every per-step decision and reason is stored with the replay request in PostgreSQL. An adapter
submission reference means the adapter accepted the plan; it is not proof of completion.

## Runtime Diff

Configuration compares workflow name/version, environment, prompt version, model, Git commit,
explicit config version, and per-tool versions when those attributes are present.
Execution nodes are sorted by execution timestamp and span identity, then represented by stable
`event_type:semantic_subject` signatures. A simple sequence matcher and multiset counts report
added/removed steps, tools, and handoffs. Retry and repeated-transition counts are explicit deltas,
so loops are visible without graph-edit-distance algorithms.

Outcomes compare duration, estimated cost, tokens, tool calls, retries, handoffs, and run status.
Numeric output includes absolute and percentage deltas when defined, plus a transparent
improved/regressed/unchanged assessment.
