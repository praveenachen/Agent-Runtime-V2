import asyncio
from collections.abc import Sequence

from agent_runtime.analysis.models import BaselineRecord, DiagnosisRecord
from agent_runtime.runs.models import RunRecord
from agent_runtime.telemetry.ports import AppendResult
from agent_runtime.telemetry.records import BronzeSpanRecord, SilverEvent


class InMemoryTelemetryStore:
    def __init__(self) -> None:
        self.bronze: dict[str, BronzeSpanRecord] = {}
        self.silver: dict[str, SilverEvent] = {}
        self.gold_runs: dict[str, RunRecord] = {}
        self.gold_baselines: dict[str, BaselineRecord] = {}
        self.gold_diagnoses: dict[str, DiagnosisRecord] = {}
        self._lock = asyncio.Lock()

    async def append_bronze(self, records: Sequence[BronzeSpanRecord]) -> AppendResult:
        async with self._lock:
            return _append_unique(self.bronze, records)

    async def append_silver(self, records: Sequence[SilverEvent]) -> AppendResult:
        async with self._lock:
            return _append_unique(self.silver, records)

    async def query_silver(self, trace_ids: Sequence[str] | None = None) -> list[SilverEvent]:
        selected = set(trace_ids) if trace_ids is not None else None
        return [
            event
            for event in self.silver.values()
            if selected is None or event.trace_id in selected
        ]

    async def upsert_gold_runs(self, records: Sequence[RunRecord]) -> AppendResult:
        async with self._lock:
            accepted = []
            duplicates = []
            for record in records:
                (duplicates if record.run_id in self.gold_runs else accepted).append(record.run_id)
                self.gold_runs[record.run_id] = record
            return AppendResult(tuple(accepted), tuple(duplicates))

    async def list_gold_runs(self) -> list[RunRecord]:
        return list(self.gold_runs.values())

    async def get_gold_run(self, run_id: str) -> RunRecord | None:
        return self.gold_runs.get(run_id)

    async def upsert_gold_baselines(self, records: Sequence[BaselineRecord]) -> AppendResult:
        async with self._lock:
            return _upsert(self.gold_baselines, records, "baseline_id")

    async def list_gold_baselines(self) -> list[BaselineRecord]:
        return list(self.gold_baselines.values())

    async def upsert_gold_diagnoses(self, records: Sequence[DiagnosisRecord]) -> AppendResult:
        async with self._lock:
            return _upsert(self.gold_diagnoses, records, "diagnosis_id")

    async def get_gold_diagnosis(self, run_id: str) -> DiagnosisRecord | None:
        return self.gold_diagnoses.get(run_id)


def _append_unique(target: dict, records: Sequence) -> AppendResult:
    accepted: list[str] = []
    duplicates: list[str] = []
    for record in records:
        record_id = record.record_id if hasattr(record, "record_id") else record.event_id
        if record_id in target:
            duplicates.append(record_id)
        else:
            target[record_id] = record
            accepted.append(record_id)
    return AppendResult(tuple(accepted), tuple(duplicates))


def _upsert(target: dict, records: Sequence, id_field: str) -> AppendResult:
    accepted: list[str] = []
    duplicates: list[str] = []
    for record in records:
        record_id = str(getattr(record, id_field))
        (duplicates if record_id in target else accepted).append(record_id)
        target[record_id] = record
    return AppendResult(tuple(accepted), tuple(duplicates))
