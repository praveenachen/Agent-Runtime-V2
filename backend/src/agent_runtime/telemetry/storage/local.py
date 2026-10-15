import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agent_runtime.analysis.models import BaselineRecord, DiagnosisRecord
from agent_runtime.runs.models import RunRecord
from agent_runtime.telemetry.ports import AppendResult
from agent_runtime.telemetry.records import BronzeSpanRecord, SilverEvent


class LocalJsonlTelemetryStore:
    """Durable local-development adapter; never selected in production."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._bronze_path = root / "bronze-spans.jsonl"
        self._silver_path = root / "silver-events.jsonl"
        self._gold_path = root / "gold-runs.jsonl"
        self._baseline_path = root / "gold-baselines.jsonl"
        self._diagnosis_path = root / "gold-diagnoses.jsonl"
        self._bronze_ids = _load_ids(self._bronze_path, "record_id")
        self._silver_ids = _load_ids(self._silver_path, "event_id")
        self._gold_runs = _load_gold_runs(self._gold_path)
        self._gold_baselines = _load_baselines(self._baseline_path)
        self._gold_diagnoses = _load_diagnoses(self._diagnosis_path)
        self._lock = asyncio.Lock()

    async def append_bronze(self, records: Sequence[BronzeSpanRecord]) -> AppendResult:
        return await self._append(self._bronze_path, self._bronze_ids, records, "record_id")

    async def append_silver(self, records: Sequence[SilverEvent]) -> AppendResult:
        return await self._append(self._silver_path, self._silver_ids, records, "event_id")

    async def query_silver(self, trace_ids: Sequence[str] | None = None) -> list[SilverEvent]:
        selected = set(trace_ids) if trace_ids is not None else None
        return await asyncio.to_thread(_load_silver, self._silver_path, selected)

    async def upsert_gold_runs(self, records: Sequence[RunRecord]) -> AppendResult:
        async with self._lock:
            accepted: list[str] = []
            duplicates: list[str] = []
            for record in records:
                (duplicates if record.run_id in self._gold_runs else accepted).append(record.run_id)
                self._gold_runs[record.run_id] = record
            await asyncio.to_thread(_write_gold_snapshot, self._gold_path, self._gold_runs)
            return AppendResult(tuple(accepted), tuple(duplicates))

    async def list_gold_runs(self) -> list[RunRecord]:
        return list(self._gold_runs.values())

    async def get_gold_run(self, run_id: str) -> RunRecord | None:
        return self._gold_runs.get(run_id)

    async def upsert_gold_baselines(self, records: Sequence[BaselineRecord]) -> AppendResult:
        return await self._upsert_snapshot(
            self._baseline_path,
            self._gold_baselines,
            records,
            "baseline_id",
        )

    async def list_gold_baselines(self) -> list[BaselineRecord]:
        return list(self._gold_baselines.values())

    async def upsert_gold_diagnoses(self, records: Sequence[DiagnosisRecord]) -> AppendResult:
        return await self._upsert_snapshot(
            self._diagnosis_path,
            self._gold_diagnoses,
            records,
            "diagnosis_id",
        )

    async def get_gold_diagnosis(self, run_id: str) -> DiagnosisRecord | None:
        return self._gold_diagnoses.get(run_id)

    async def _upsert_snapshot(
        self,
        path: Path,
        target: dict,
        records: Sequence,
        id_field: str,
    ) -> AppendResult:
        async with self._lock:
            accepted: list[str] = []
            duplicates: list[str] = []
            for record in records:
                record_id = str(getattr(record, id_field))
                (duplicates if record_id in target else accepted).append(record_id)
                target[record_id] = record
            await asyncio.to_thread(_write_snapshot, path, target, id_field)
            return AppendResult(tuple(accepted), tuple(duplicates))

    async def _append(
        self,
        path: Path,
        known_ids: set[str],
        records: Sequence[BronzeSpanRecord] | Sequence[SilverEvent],
        id_field: str,
    ) -> AppendResult:
        async with self._lock:
            accepted_records = []
            duplicate_ids = []
            pending_ids: set[str] = set()
            for record in records:
                record_id = str(getattr(record, id_field))
                if record_id in known_ids or record_id in pending_ids:
                    duplicate_ids.append(record_id)
                else:
                    accepted_records.append(record)
                    pending_ids.add(record_id)
            if accepted_records:
                await asyncio.to_thread(_append_lines, path, accepted_records)
                known_ids.update(pending_ids)
            return AppendResult(
                tuple(str(getattr(record, id_field)) for record in accepted_records),
                tuple(duplicate_ids),
            )


def _append_lines(path: Path, records: Sequence[BronzeSpanRecord] | Sequence[SilverEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True))
            output.write("\n")


def _load_ids(path: Path, id_field: str) -> set[str]:
    if not path.exists():
        return set()
    identifiers: set[str] = set()
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                payload: dict[str, Any] = json.loads(line)
                identifiers.add(str(payload[id_field]))
    return identifiers


def _load_silver(path: Path, trace_ids: set[str] | None) -> list[SilverEvent]:
    if not path.exists():
        return []
    events: list[SilverEvent] = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            payload = json.loads(line)
            if trace_ids is None or payload["trace_id"] in trace_ids:
                events.append(SilverEvent(**payload))
    return events


def _load_gold_runs(path: Path) -> dict[str, RunRecord]:
    if not path.exists():
        return {}
    records: dict[str, RunRecord] = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                record = RunRecord.from_dict(json.loads(line))
                records[record.run_id] = record
    return records


def _write_gold_snapshot(path: Path, records: dict[str, RunRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        for record in sorted(records.values(), key=lambda item: item.run_id):
            output.write(json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True))
            output.write("\n")
    temporary.replace(path)


def _load_baselines(path: Path) -> dict[str, BaselineRecord]:
    return _load_projection(path, BaselineRecord.from_dict, "baseline_id")


def _load_diagnoses(path: Path) -> dict[str, DiagnosisRecord]:
    return _load_projection(path, DiagnosisRecord.from_dict, "diagnosis_id")


def _load_projection(path: Path, factory, id_field: str) -> dict:
    if not path.exists():
        return {}
    records = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                record = factory(json.loads(line))
                records[str(getattr(record, id_field))] = record
    return records


def _write_snapshot(path: Path, records: dict, id_field: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        for record in sorted(records.values(), key=lambda item: str(getattr(item, id_field))):
            output.write(json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True))
            output.write("\n")
    temporary.replace(path)
