import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agent_runtime.telemetry.ports import AppendResult
from agent_runtime.telemetry.records import BronzeSpanRecord, SilverEvent


class LocalJsonlTelemetryStore:
    """Durable local-development adapter; never selected in production."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._bronze_path = root / "bronze-spans.jsonl"
        self._silver_path = root / "silver-events.jsonl"
        self._bronze_ids = _load_ids(self._bronze_path, "record_id")
        self._silver_ids = _load_ids(self._silver_path, "event_id")
        self._lock = asyncio.Lock()

    async def append_bronze(self, records: Sequence[BronzeSpanRecord]) -> AppendResult:
        return await self._append(self._bronze_path, self._bronze_ids, records, "record_id")

    async def append_silver(self, records: Sequence[SilverEvent]) -> AppendResult:
        return await self._append(self._silver_path, self._silver_ids, records, "event_id")

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

