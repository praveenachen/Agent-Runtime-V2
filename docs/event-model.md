# Agent Runtime — Event Model

This document defines the initial canonical semantic model layered on top of OpenTelemetry.

## Principle
Do not replace OpenTelemetry. Extend OTel spans with a minimal set of agent-specific semantic attributes.

## Event types
- RUN
- AGENT_STEP
- LLM_CALL
- TOOL_CALL
- DECISION
- HANDOFF
- APPROVAL
- CHECKPOINT
- ERROR

## Common fields
Where available:
- trace_id
- span_id
- parent_span_id
- timestamp
- duration_ms
- status
- event_type
- organization_id / project_id
- workflow_name
- workflow_version
- environment
- agent_name
- prompt_version
- model
- git_commit

## TOOL_CALL attributes
- tool_name
- operation
- success
- latency_ms
- side_effect: boolean
- replayable: boolean
- input_ref / output_ref where large payloads are externalized
- retry_index where relevant

## DECISION attributes
- decision
- confidence (optional; only if supplied by the workflow/model layer)
- structured_reason (optional)

Do not synthesize hidden chain-of-thought.

## HANDOFF attributes
- from_agent
- to_agent
- reason (optional)

## APPROVAL attributes
- approval_type
- required
- state: pending|approved|rejected|expired
- requested_at
- resolved_at
- reviewer_id/reference when appropriate

## CHECKPOINT attributes
- checkpoint_name
- checkpoint_ref
- replay_capability

## ERROR attributes
- error_type
- message_safe
- retryable (optional)
- retry_index

## Side effects
`side_effect=true` means the operation changes external state.
Examples: send email, create calendar event, update CRM, write/delete production data.

## Replayability
`replayable=true` means the step may safely execute again under the selected replay mode.

These are separate concepts. A read can be non-reproducible even if it has no side effect; v1 should not over-model this unless a concrete need appears.

## Large payloads
Avoid embedding huge prompts/documents/tool outputs into hot OLTP rows.
Preserve metadata and references; store large payloads in governed object storage/Volumes when needed.

## Evolution
Schema changes should be backward-compatible where practical. Bronze raw OTel data is the source for reprocessing when normalization semantics change.
