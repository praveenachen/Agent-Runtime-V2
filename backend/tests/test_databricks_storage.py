import asyncio
import json
from datetime import UTC, datetime

import pytest

from agent_runtime.telemetry.ports import AppendResult
from agent_runtime.telemetry.records import BronzeSpanRecord
from agent_runtime.telemetry.storage.databricks import DatabricksTelemetryStore


class RecordingMergeWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict], str]] = []

    async def merge_records(self, table, records, *, key_column):
        materialized = list(records)
        self.calls.append((table, materialized, key_column))
        return AppendResult(tuple(str(record[key_column]) for record in materialized), ())


def test_databricks_adapter_emits_idempotent_bronze_merge_contract() -> None:
    writer = RecordingMergeWriter()
    store = DatabricksTelemetryStore(writer, catalog="agent_runtime", schema="telemetry")
    record = BronzeSpanRecord(
        record_id="trace:span",
        trace_id="trace",
        span_id="span",
        parent_span_id=None,
        received_at=datetime.now(UTC).isoformat(),
        source_format="otlp_http_protobuf",
        resource={"attributes": {"service.name": "demo"}},
        instrumentation_scope={"name": "test"},
        span={"name": "run"},
    )

    result = asyncio.run(store.append_bronze([record]))

    table, rows, key_column = writer.calls[0]
    assert table == "agent_runtime.telemetry.bronze_agent_spans"
    assert key_column == "record_id"
    assert result.accepted_ids == ("trace:span",)
    assert json.loads(rows[0]["span_json"]) == {"name": "run"}


def test_databricks_adapter_rejects_unsafe_table_identifiers() -> None:
    with pytest.raises(ValueError, match="Unsafe Databricks identifier"):
        DatabricksTelemetryStore(
            RecordingMergeWriter(),
            catalog="agent-runtime;drop",
            schema="telemetry",
        )
