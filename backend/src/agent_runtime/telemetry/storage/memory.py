import asyncio
from collections.abc import Sequence

from agent_runtime.telemetry.ports import AppendResult
from agent_runtime.telemetry.records import BronzeSpanRecord, SilverEvent


class InMemoryTelemetryStore:
    def __init__(self) -> None:
        self.bronze: dict[str, BronzeSpanRecord] = {}
        self.silver: dict[str, SilverEvent] = {}
        self._lock = asyncio.Lock()

    async def append_bronze(self, records: Sequence[BronzeSpanRecord]) -> AppendResult:
        async with self._lock:
            return _append_unique(self.bronze, records)

    async def append_silver(self, records: Sequence[SilverEvent]) -> AppendResult:
        async with self._lock:
            return _append_unique(self.silver, records)


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

