from collections.abc import Sequence
from typing import Any, Protocol


class TelemetryAnalyticsStore(Protocol):
    """Databricks boundary for raw and normalized telemetry.

    Milestone 1 intentionally provides only the port. Bronze/Silver/Gold writes
    and any Databricks client dependency belong to later milestones.
    """

    async def append_bronze(self, records: Sequence[dict[str, Any]]) -> None: ...

