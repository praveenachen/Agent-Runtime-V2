from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from agent_runtime.telemetry.records import BronzeSpanRecord, SilverEvent


@dataclass(frozen=True, slots=True)
class AppendResult:
    accepted_ids: tuple[str, ...] = ()
    duplicate_ids: tuple[str, ...] = ()


class TelemetryAnalyticsStore(Protocol):
    """Persistence boundary for Bronze and Silver telemetry.

    Production implementations target Databricks Delta. Local and in-memory
    adapters exist only for development and tests.
    """

    async def append_bronze(self, records: Sequence[BronzeSpanRecord]) -> AppendResult: ...

    async def append_silver(self, records: Sequence[SilverEvent]) -> AppendResult: ...

