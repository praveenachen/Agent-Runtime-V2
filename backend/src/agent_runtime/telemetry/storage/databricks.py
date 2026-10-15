import json
import re
from collections.abc import Sequence
from typing import Any, Protocol

from agent_runtime.telemetry.ports import AppendResult
from agent_runtime.telemetry.records import BronzeSpanRecord, SilverEvent

BRONZE_TABLE_NAME = "bronze_agent_spans"
SILVER_TABLE_NAME = "silver_agent_events"

BRONZE_DELTA_COLUMNS = {
    "record_id": "STRING",
    "trace_id": "STRING",
    "span_id": "STRING",
    "parent_span_id": "STRING",
    "received_at": "TIMESTAMP",
    "source_format": "STRING",
    "resource_json": "STRING",
    "instrumentation_scope_json": "STRING",
    "span_json": "STRING",
}

SILVER_DELTA_COLUMNS = {
    "event_id": "STRING",
    "trace_id": "STRING",
    "span_id": "STRING",
    "parent_span_id": "STRING",
    "timestamp": "TIMESTAMP",
    "duration_ms": "DOUBLE",
    "status": "STRING",
    "event_type": "STRING",
    "ingested_at": "TIMESTAMP",
    "observed_lag_ms": "DOUBLE",
    "is_late": "BOOLEAN",
    "is_out_of_order": "BOOLEAN",
    "event_json": "STRING",
}


class DatabricksMergeWriter(Protocol):
    """Connector seam for Delta MERGE operations using the stable record ID."""

    async def merge_records(
        self,
        table: str,
        records: Sequence[dict[str, Any]],
        *,
        key_column: str,
    ) -> AppendResult: ...


class DatabricksTelemetryStore:
    """Production Delta adapter independent of a specific Databricks client SDK."""

    def __init__(self, writer: DatabricksMergeWriter, *, catalog: str, schema: str) -> None:
        self._writer = writer
        self._bronze_table = _table_reference(catalog, schema, BRONZE_TABLE_NAME)
        self._silver_table = _table_reference(catalog, schema, SILVER_TABLE_NAME)

    async def append_bronze(self, records: Sequence[BronzeSpanRecord]) -> AppendResult:
        return await self._writer.merge_records(
            self._bronze_table,
            [_bronze_row(record) for record in records],
            key_column="record_id",
        )

    async def append_silver(self, records: Sequence[SilverEvent]) -> AppendResult:
        return await self._writer.merge_records(
            self._silver_table,
            [_silver_row(record) for record in records],
            key_column="event_id",
        )


def _table_reference(catalog: str, schema: str, table: str) -> str:
    for identifier in (catalog, schema, table):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
            raise ValueError(f"Unsafe Databricks identifier: {identifier!r}")
    return f"{catalog}.{schema}.{table}"


def _bronze_row(record: BronzeSpanRecord) -> dict[str, Any]:
    return {
        "record_id": record.record_id,
        "trace_id": record.trace_id,
        "span_id": record.span_id,
        "parent_span_id": record.parent_span_id,
        "received_at": record.received_at,
        "source_format": record.source_format,
        "resource_json": json.dumps(record.resource, separators=(",", ":"), sort_keys=True),
        "instrumentation_scope_json": json.dumps(
            record.instrumentation_scope, separators=(",", ":"), sort_keys=True
        ),
        "span_json": json.dumps(record.span, separators=(",", ":"), sort_keys=True),
    }


def _silver_row(record: SilverEvent) -> dict[str, Any]:
    return {
        "event_id": record.event_id,
        "trace_id": record.trace_id,
        "span_id": record.span_id,
        "parent_span_id": record.parent_span_id,
        "timestamp": record.timestamp,
        "duration_ms": record.duration_ms,
        "status": record.status,
        "event_type": record.event_type,
        "ingested_at": record.ingested_at,
        "observed_lag_ms": record.observed_lag_ms,
        "is_late": record.is_late,
        "is_out_of_order": record.is_out_of_order,
        "event_json": json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True),
    }

