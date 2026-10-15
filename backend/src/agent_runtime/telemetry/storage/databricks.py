import json
import re
from collections.abc import Sequence
from typing import Any, Protocol

from agent_runtime.analysis.models import BaselineRecord, DiagnosisRecord
from agent_runtime.runs.models import RunRecord
from agent_runtime.telemetry.ports import AppendResult
from agent_runtime.telemetry.records import BronzeSpanRecord, SilverEvent

BRONZE_TABLE_NAME = "bronze_agent_spans"
SILVER_TABLE_NAME = "silver_agent_events"
GOLD_RUNS_TABLE_NAME = "gold_runs"
GOLD_BASELINES_TABLE_NAME = "gold_workflow_baselines"
GOLD_DIAGNOSES_TABLE_NAME = "gold_run_diagnoses"

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

GOLD_RUNS_DELTA_COLUMNS = {
    "run_id": "STRING",
    "trace_id": "STRING",
    "started_at": "TIMESTAMP",
    "ended_at": "TIMESTAMP",
    "status": "STRING",
    "workflow_name": "STRING",
    "environment": "STRING",
    "run_json": "STRING",
}

GOLD_BASELINES_DELTA_COLUMNS = {
    "baseline_id": "STRING",
    "workflow_name": "STRING",
    "environment": "STRING",
    "updated_at": "TIMESTAMP",
    "run_count": "BIGINT",
    "baseline_json": "STRING",
}

GOLD_DIAGNOSES_DELTA_COLUMNS = {
    "diagnosis_id": "STRING",
    "run_id": "STRING",
    "generated_at": "TIMESTAMP",
    "status": "STRING",
    "diagnosis_json": "STRING",
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

    async def query_records(
        self,
        table: str,
        *,
        trace_ids: Sequence[str] | None = None,
    ) -> Sequence[dict[str, Any]]: ...


class DatabricksTelemetryStore:
    """Production Delta adapter independent of a specific Databricks client SDK."""

    def __init__(self, writer: DatabricksMergeWriter, *, catalog: str, schema: str) -> None:
        self._writer = writer
        self._bronze_table = _table_reference(catalog, schema, BRONZE_TABLE_NAME)
        self._silver_table = _table_reference(catalog, schema, SILVER_TABLE_NAME)
        self._gold_runs_table = _table_reference(catalog, schema, GOLD_RUNS_TABLE_NAME)
        self._gold_baselines_table = _table_reference(catalog, schema, GOLD_BASELINES_TABLE_NAME)
        self._gold_diagnoses_table = _table_reference(catalog, schema, GOLD_DIAGNOSES_TABLE_NAME)

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

    async def query_silver(self, trace_ids: Sequence[str] | None = None) -> list[SilverEvent]:
        rows = await self._writer.query_records(self._silver_table, trace_ids=trace_ids)
        return [SilverEvent(**json.loads(row["event_json"])) for row in rows]

    async def upsert_gold_runs(self, records: Sequence[RunRecord]) -> AppendResult:
        return await self._writer.merge_records(
            self._gold_runs_table,
            [_gold_run_row(record) for record in records],
            key_column="run_id",
        )

    async def list_gold_runs(self) -> list[RunRecord]:
        rows = await self._writer.query_records(self._gold_runs_table)
        return [RunRecord.from_dict(json.loads(row["run_json"])) for row in rows]

    async def get_gold_run(self, run_id: str) -> RunRecord | None:
        rows = await self._writer.query_records(self._gold_runs_table, trace_ids=[run_id])
        return RunRecord.from_dict(json.loads(rows[0]["run_json"])) if rows else None

    async def upsert_gold_baselines(self, records: Sequence[BaselineRecord]) -> AppendResult:
        return await self._writer.merge_records(
            self._gold_baselines_table,
            [_gold_baseline_row(record) for record in records],
            key_column="baseline_id",
        )

    async def list_gold_baselines(self) -> list[BaselineRecord]:
        rows = await self._writer.query_records(self._gold_baselines_table)
        return [BaselineRecord.from_dict(json.loads(row["baseline_json"])) for row in rows]

    async def upsert_gold_diagnoses(self, records: Sequence[DiagnosisRecord]) -> AppendResult:
        return await self._writer.merge_records(
            self._gold_diagnoses_table,
            [_gold_diagnosis_row(record) for record in records],
            key_column="diagnosis_id",
        )

    async def get_gold_diagnosis(self, run_id: str) -> DiagnosisRecord | None:
        rows = await self._writer.query_records(self._gold_diagnoses_table, trace_ids=[run_id])
        return DiagnosisRecord.from_dict(json.loads(rows[0]["diagnosis_json"])) if rows else None


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


def _gold_run_row(record: RunRecord) -> dict[str, Any]:
    return {
        "run_id": record.run_id,
        "trace_id": record.trace_id,
        "started_at": record.started_at,
        "ended_at": record.ended_at,
        "status": record.status,
        "workflow_name": record.workflow_name,
        "environment": record.environment,
        "run_json": json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True),
    }


def _gold_baseline_row(record: BaselineRecord) -> dict[str, Any]:
    return {
        "baseline_id": record.baseline_id,
        "workflow_name": record.key.workflow_name,
        "environment": record.key.environment,
        "updated_at": record.updated_at,
        "run_count": record.run_count,
        "baseline_json": json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True),
    }


def _gold_diagnosis_row(record: DiagnosisRecord) -> dict[str, Any]:
    return {
        "diagnosis_id": record.diagnosis_id,
        "run_id": record.run_id,
        "generated_at": record.generated_at,
        "status": record.status,
        "diagnosis_json": json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True),
    }
