from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from agent_runtime.domain.models import ReplayCapability, ReplayMode, ReplayStatus


class ReplayAction(StrEnum):
    REEXECUTE = "reexecute"
    REUSE = "reuse"
    MOCK = "mock"
    BLOCK_UNSAFE = "block_unsafe"


@dataclass(frozen=True, slots=True)
class SemanticCheckpoint:
    checkpoint_id: str
    run_id: str
    trace_id: str
    span_id: str
    timestamp: str
    integration: str | None
    workflow_name: str | None
    environment: str | None
    workflow_version: str | None
    prompt_version: str | None
    model: str | None
    state_reference: str | None
    input_reference: str | None
    output_reference: str | None


@dataclass(frozen=True, slots=True)
class CapabilityAvailability:
    capability: ReplayCapability
    available: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ReplayCapabilities:
    run_id: str
    adapter_id: str
    capabilities: tuple[CapabilityAvailability, ...]
    checkpoints: tuple[SemanticCheckpoint, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StepReplayDecision:
    node_id: str
    span_id: str
    label: str
    event_type: str
    action: ReplayAction
    reason: str
    simulated: bool = False


@dataclass(frozen=True, slots=True)
class ReplayPlan:
    source_run_id: str
    requested_capability: ReplayCapability
    resolved_capability: ReplayCapability
    checkpoint_id: str | None
    adapter_id: str
    mode: ReplayMode
    fallback_used: bool
    decisions: tuple[StepReplayDecision, ...]
    executable: bool
    blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReplayRequestRecord:
    id: str
    project_id: str | None
    source_run_id: str
    mode: ReplayMode
    status: ReplayStatus
    requested_changes: dict[str, Any]
    requested_capability: ReplayCapability
    resolved_capability: ReplayCapability
    checkpoint_id: str | None
    adapter_id: str
    plan: dict[str, Any]
    output_run_id: str | None
    external_reference: str | None
    status_reason: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FieldDifference:
    field: str
    original: Any
    comparison: Any
    changed: bool


@dataclass(frozen=True, slots=True)
class SequenceDifference:
    operation: str
    original_start: int
    original_end: int
    comparison_start: int
    comparison_end: int
    original: tuple[str, ...] = ()
    comparison: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MetricDifference:
    metric: str
    original: float | int | str | None
    comparison: float | int | str | None
    delta: float | None
    percent_change: float | None
    assessment: str


@dataclass(frozen=True, slots=True)
class ExecutionDifference:
    original_sequence: tuple[str, ...]
    comparison_sequence: tuple[str, ...]
    sequence_changes: tuple[SequenceDifference, ...]
    added_steps: dict[str, int]
    removed_steps: dict[str, int]
    added_tools: dict[str, int]
    removed_tools: dict[str, int]
    added_handoffs: dict[str, int]
    removed_handoffs: dict[str, int]
    retry_delta: int
    repeated_transition_delta: int


@dataclass(frozen=True, slots=True)
class RuntimeDiff:
    original_run_id: str
    comparison_run_id: str
    configuration: tuple[FieldDifference, ...]
    execution: ExecutionDifference
    outcomes: tuple[MetricDifference, ...]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
