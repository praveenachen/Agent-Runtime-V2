from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from agent_runtime.telemetry.records import BronzeSpanRecord, SilverEvent

if TYPE_CHECKING:
    from agent_runtime.runs.models import RunRecord


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

    async def query_silver(self, trace_ids: Sequence[str] | None = None) -> list[SilverEvent]: ...

    async def upsert_gold_runs(self, records: Sequence["RunRecord"]) -> AppendResult: ...

    async def list_gold_runs(self) -> list["RunRecord"]: ...

    async def get_gold_run(self, run_id: str) -> "RunRecord | None": ...
