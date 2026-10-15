# Agent Runtime backend

One FastAPI modular monolith. PostgreSQL owns transactional application state.
OTLP traces enter through `/api/v1/telemetry/otlp/v1/traces`; redacted Bronze and
normalized Silver records are written through the telemetry analytics port. Local
development uses JSONL and production composition supplies the Databricks Delta
merge writer.

