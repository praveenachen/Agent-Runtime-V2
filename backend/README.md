# Agent Runtime backend

One FastAPI modular monolith. Domain modules remain in-process; PostgreSQL owns
transactional state, while the telemetry analytics boundary is represented by a
port that Milestone 2 can implement for Databricks.

