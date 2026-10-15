from typing import Any, Protocol

from agent_runtime.domain.models import ReplayCapability
from agent_runtime.replay.models import ReplayPlan, ReplayRequestRecord
from agent_runtime.runs.models import GraphNode, RunRecord


class ReplayRequestRepository(Protocol):
    async def create(self, record: ReplayRequestRecord) -> ReplayRequestRecord: ...

    async def get(self, request_id: str) -> ReplayRequestRecord | None: ...


class FrameworkReplayAdapter(Protocol):
    adapter_id: str

    def supports(self, capability: ReplayCapability, run: RunRecord) -> bool: ...

    def safe_to_reexecute(self, node: GraphNode) -> bool: ...

    async def submit(self, plan: ReplayPlan, changes: dict[str, Any]) -> str | None: ...


class GenericReplayAdapter:
    """Planning-only adapter used when no framework executor is configured."""

    adapter_id = "generic"

    def supports(self, capability: ReplayCapability, run: RunRecord) -> bool:
        return capability == ReplayCapability.COMPARE_ONLY

    def safe_to_reexecute(self, node: GraphNode) -> bool:
        return False

    async def submit(self, plan: ReplayPlan, changes: dict[str, Any]) -> str | None:
        return None
