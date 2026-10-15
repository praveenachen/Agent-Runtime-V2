from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BronzeSpanRecord:
    record_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    received_at: str
    source_format: str
    resource: dict[str, Any]
    instrumentation_scope: dict[str, Any]
    span: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SilverEvent:
    event_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    timestamp: str
    duration_ms: float
    status: str
    event_type: str
    ingested_at: str
    observed_lag_ms: float
    is_late: bool
    is_out_of_order: bool
    organization_id: str | None = None
    project_id: str | None = None
    workflow_name: str | None = None
    workflow_version: str | None = None
    environment: str | None = None
    agent_name: str | None = None
    prompt_version: str | None = None
    model: str | None = None
    git_commit: str | None = None
    semantic_attributes: dict[str, Any] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

