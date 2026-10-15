from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str
    span_id: str
    parent_span_id: str | None
    event_type: str
    label: str
    started_at: str
    ended_at: str
    duration_ms: float
    status: str
    agent_name: str | None
    depth: int
    lane: int
    is_concurrent: bool
    retry_index: int | None = None
    semantic_attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GraphEdge:
    id: str
    source: str
    target: str
    type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionGraph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


@dataclass(frozen=True, slots=True)
class RunMetrics:
    total_duration_ms: float
    agent_latency_ms: float
    tool_latency_ms: float
    tool_call_count: int
    llm_call_count: int
    retry_count: int
    handoff_count: int
    repeated_transition_count: int
    error_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float | None
    approval_wait_ms: float
    path_length: int
    step_count: int


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    trace_id: str
    name: str
    status: str
    started_at: str
    ended_at: str
    materialized_at: str
    organization_id: str | None
    project_id: str | None
    workflow_name: str | None
    workflow_version: str | None
    environment: str | None
    graph: ExecutionGraph
    metrics: RunMetrics
    events: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary_dict(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("graph")
        payload.pop("events")
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunRecord":
        graph = payload["graph"]
        return cls(
            **{
                key: value
                for key, value in payload.items()
                if key not in {"graph", "metrics", "events"}
            },
            graph=ExecutionGraph(
                nodes=tuple(GraphNode(**node) for node in graph["nodes"]),
                edges=tuple(GraphEdge(**edge) for edge in graph["edges"]),
            ),
            metrics=RunMetrics(**payload["metrics"]),
            events=tuple(payload["events"]),
        )
