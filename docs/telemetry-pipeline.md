# Telemetry Pipeline Contract

This contract implements Milestone 2 without changing the binding architecture in
`architecture.md` and `event-model.md`.

## Data flow and acknowledgement

```text
Agent application
  -> OpenTelemetry Collector (batching, retry, bounded sending queue)
  -> POST /api/v1/telemetry/otlp/v1/traces (binary OTLP protobuf, optional gzip)
  -> decode and redact
  -> durable Bronze append
  -> OTLP success response
  -> after-response Silver normalization and append
```

The API acknowledges only after Bronze accepts the batch. Silver is outside the
response path because Bronze is the reprocessing source. No external message queue
is present. A future queue can be inserted behind the ingestion/store interfaces if
scale or durability requirements justify it.

## Bronze

Bronze stores one redacted record per span with stable ID `<trace_id>:<span_id>`:

- receipt timestamp and source encoding;
- trace, span, and parent span identity;
- resource attributes and schema URL;
- instrumentation scope metadata;
- the OTel span envelope: name, kind, trace state, timestamps, status, attributes,
  events, links, flags, and dropped-item counts.

Repeated delivery is first-write-wins on the stable record ID. Bronze intentionally
keeps unsupported semantic spans so future normalizers can reprocess them.

## Silver

Silver stores supported Agent Runtime semantic events with:

- stable event/trace/span/parent identity;
- canonical event type, UTC timestamp, duration, and status;
- organization, project, workflow, environment, agent, prompt, model, and commit
  metadata where supplied;
- normalized type-specific semantic fields;
- the complete redacted resource-plus-span attribute map;
- ingestion lag, late-arrival flag, and observed out-of-order flag.

Silver deduplicates on the same stable ID. Arrival order is metadata and is never
treated as execution order.

## Semantic attributes

`agent.runtime.event_type` is the preferred extension attribute. The aliases
`agent.event_type` and `event_type` are accepted. The normalizer also maps these
standard GenAI operations when present:

- `chat`, `text_completion`, `generate_content` -> `LLM_CALL`
- `execute_tool` -> `TOOL_CALL`
- `invoke_agent` -> `AGENT_STEP`

Unknown types remain only in Bronze.

## Redaction

Redaction runs after protobuf decoding and before any storage adapter receives a
record. Sensitive keys include authorization/cookie/password/secret/API-key and
access/refresh-token forms. Nested values are traversed. Recognizable bearer tokens,
OpenAI-style secret keys, and AWS access-key IDs are also replaced in string values.

The replacement marker is `[REDACTED]`. Raw unredacted protobuf bytes are not stored.

## Storage adapters

- Local development: append-only JSONL files under `AGENT_RUNTIME_TELEMETRY_LOCAL_PATH`.
- Tests: in-memory adapter.
- Production: `DatabricksTelemetryStore`, which delegates idempotent Delta `MERGE`
  operations to a credential-aware `DatabricksMergeWriter` supplied by deployment
  composition. Local startup does not require Databricks credentials or its SDK.

PostgreSQL is not used for telemetry records.

