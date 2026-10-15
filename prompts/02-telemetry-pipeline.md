# Milestone 2 — Telemetry Pipeline

## Goal
Receive standard OpenTelemetry traces, preserve raw telemetry, and normalize supported agent semantics into the Agent Runtime event model.

## Deliverables
- OTLP-compatible ingestion path from OTel Collector to Agent Runtime.
- Asynchronous/non-blocking ingestion handling on the application side of the pipeline.
- Bronze persistence contract for raw OTel records in Databricks.
- Silver transformation/normalization for the semantic event types in `docs/event-model.md`.
- Deduplication strategy using stable event/span identity.
- Handling/recording of late or out-of-order events without pretending ordering is always perfect.
- Preservation of original attributes sufficient for future reprocessing.
- Redaction/safety hook for secrets before durable storage; keep implementation minimal but real.
- Integration tests using synthetic OTel traces.

## Important
Do not introduce Kafka/SQS. If you believe buffering is necessary, explain why the Collector's existing capabilities are insufficient before changing architecture.

## Acceptance examples
Synthetic runs should successfully produce Bronze raw records and Silver normalized events for at least:
- RUN/AGENT_STEP
- LLM_CALL
- TOOL_CALL
- HANDOFF
- DECISION
- ERROR

Do not build graph reconstruction yet beyond what is required to validate parent/span relationships.
