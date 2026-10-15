from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from agent_runtime.runs.models import (
    ExecutionGraph,
    GraphEdge,
    GraphNode,
    RunMetrics,
    RunRecord,
)
from agent_runtime.telemetry.ports import TelemetryAnalyticsStore
from agent_runtime.telemetry.records import SilverEvent


class BaselineProjector(Protocol):
    async def refresh_baselines(self) -> None: ...


class RunService:
    def __init__(
        self,
        store: TelemetryAnalyticsStore,
        *,
        baseline_projector: BaselineProjector | None = None,
    ) -> None:
        self._store = store
        self._baseline_projector = baseline_projector

    async def materialize(self, trace_ids: Sequence[str] | None = None) -> tuple[RunRecord, ...]:
        events = await self._store.query_silver(trace_ids=trace_ids)
        grouped: dict[str, list[SilverEvent]] = defaultdict(list)
        for event in events:
            grouped[event.trace_id].append(event)
        records = tuple(build_run(group) for group in grouped.values())
        if records:
            await self._store.upsert_gold_runs(records)
            if self._baseline_projector is not None:
                await self._baseline_projector.refresh_baselines()
        return records

    async def list_runs(
        self,
        *,
        status: str | None = None,
        workflow: str | None = None,
        environment: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RunRecord], int]:
        records = list(await self._store.list_gold_runs())
        if not records:
            await self.materialize()
            records = list(await self._store.list_gold_runs())
        if status:
            records = [record for record in records if record.status == status]
        if workflow:
            records = [record for record in records if record.workflow_name == workflow]
        if environment:
            records = [record for record in records if record.environment == environment]
        records.sort(key=lambda record: record.started_at, reverse=True)
        return records[offset : offset + limit], len(records)

    async def get_run(self, run_id: str) -> RunRecord | None:
        record = await self._store.get_gold_run(run_id)
        if record is not None:
            return record
        await self.materialize([run_id])
        return await self._store.get_gold_run(run_id)


def build_run(events: Sequence[SilverEvent]) -> RunRecord:
    if not events:
        raise ValueError("Cannot build a run without Silver events")
    ordered = sorted(events, key=lambda event: (_time(event.timestamp), event.span_id))
    starts = [_time(event.timestamp) for event in ordered]
    ends = [
        start + timedelta(milliseconds=event.duration_ms)
        for start, event in zip(starts, ordered, strict=True)
    ]
    nodes, edges, repeated_count = _build_graph(ordered)
    run_event = next((event for event in ordered if event.event_type == "RUN"), ordered[0])
    status = _run_status(ordered, run_event)
    graph = ExecutionGraph(nodes=tuple(nodes), edges=tuple(edges))
    metrics = _metrics(ordered, nodes, repeated_count, min(starts), max(ends))
    workflow = run_event.workflow_name or _first_value(ordered, "workflow_name")
    return RunRecord(
        run_id=run_event.trace_id,
        trace_id=run_event.trace_id,
        name=str(run_event.attributes.get("agent.runtime.run.name") or workflow or "Untitled run"),
        status=status,
        started_at=min(starts).isoformat(),
        ended_at=max(ends).isoformat(),
        materialized_at=datetime.now(UTC).isoformat(),
        organization_id=run_event.organization_id or _first_value(ordered, "organization_id"),
        project_id=run_event.project_id or _first_value(ordered, "project_id"),
        workflow_name=workflow,
        workflow_version=run_event.workflow_version or _first_value(ordered, "workflow_version"),
        environment=run_event.environment or _first_value(ordered, "environment"),
        graph=graph,
        metrics=metrics,
        events=tuple(event.to_dict() for event in ordered),
    )


def _build_graph(events: list[SilverEvent]) -> tuple[list[GraphNode], list[GraphEdge], int]:
    by_span = {event.span_id: event for event in events}
    depth_cache: dict[str, int] = {}

    def depth(event: SilverEvent, visiting: set[str] | None = None) -> int:
        if event.span_id in depth_cache:
            return depth_cache[event.span_id]
        active = set() if visiting is None else visiting
        if (
            event.span_id in active
            or not event.parent_span_id
            or event.parent_span_id not in by_span
        ):
            return 0
        active.add(event.span_id)
        result = 1 + depth(by_span[event.parent_span_id], active)
        active.remove(event.span_id)
        depth_cache[event.span_id] = result
        return result

    intervals = [
        (_time(event.timestamp), _time(event.timestamp) + timedelta(milliseconds=event.duration_ms))
        for event in events
    ]
    lanes: list[datetime] = []
    nodes: list[GraphNode] = []
    for index, event in enumerate(events):
        start, end = intervals[index]
        lane = next(
            (lane_index for lane_index, lane_end in enumerate(lanes) if lane_end <= start),
            len(lanes),
        )
        if lane == len(lanes):
            lanes.append(end)
        else:
            lanes[lane] = end
        concurrent = any(
            other_start < end and start < other_end
            for other_index, (other_start, other_end) in enumerate(intervals)
            if other_index != index
        )
        nodes.append(
            GraphNode(
                id=event.event_id,
                span_id=event.span_id,
                parent_span_id=event.parent_span_id,
                event_type=event.event_type,
                label=_label(event),
                started_at=start.isoformat(),
                ended_at=end.isoformat(),
                duration_ms=event.duration_ms,
                status=event.status,
                agent_name=event.agent_name,
                depth=depth(event),
                lane=lane,
                is_concurrent=concurrent,
                retry_index=_integer(event.semantic_attributes.get("retry_index")),
                semantic_attributes=event.semantic_attributes,
            )
        )

    edges: list[GraphEdge] = []
    for event in events:
        if event.parent_span_id in by_span:
            parent = by_span[event.parent_span_id]
            edges.append(_edge(parent.event_id, event.event_id, "parent_child"))

    for index, event in enumerate(events):
        if event.event_type == "HANDOFF":
            target_agent = event.semantic_attributes.get("to_agent")
            target = next(
                (
                    candidate
                    for candidate in events[index + 1 :]
                    if target_agent and candidate.agent_name == target_agent
                ),
                None,
            )
            if target:
                edges.append(
                    _edge(
                        event.event_id,
                        target.event_id,
                        "handoff",
                        {
                            "from_agent": event.semantic_attributes.get("from_agent"),
                            "to_agent": target_agent,
                        },
                    )
                )

        retry_index = _integer(event.semantic_attributes.get("retry_index"))
        if retry_index and retry_index > 0:
            key = _fingerprint(event)
            original = next(
                (
                    candidate
                    for candidate in reversed(events[:index])
                    if _fingerprint(candidate) == key
                ),
                None,
            )
            if original:
                edges.append(
                    _edge(original.event_id, event.event_id, "retry", {"retry_index": retry_index})
                )

    repeated_count = 0
    previous_by_fingerprint: dict[str, SilverEvent] = {}
    for event in (item for item in events if item.event_type != "RUN"):
        if (_integer(event.semantic_attributes.get("retry_index")) or 0) > 0:
            continue
        fingerprint = _fingerprint(event)
        previous = previous_by_fingerprint.get(fingerprint)
        if previous is not None:
            repeated_count += 1
            edges.append(_edge(previous.event_id, event.event_id, "repeated_transition"))
        previous_by_fingerprint[fingerprint] = event
    return nodes, _deduplicate_edges(edges), repeated_count


def _metrics(
    events: list[SilverEvent],
    nodes: list[GraphNode],
    repeated_count: int,
    started_at: datetime,
    ended_at: datetime,
) -> RunMetrics:
    input_tokens = sum(_number(event.attributes, _INPUT_TOKEN_KEYS, int) for event in events)
    output_tokens = sum(_number(event.attributes, _OUTPUT_TOKEN_KEYS, int) for event in events)
    declared_total = sum(_number(event.attributes, _TOTAL_TOKEN_KEYS, int) for event in events)
    costs = [_optional_number(event.attributes, _COST_KEYS) for event in events]
    declared_costs = [cost for cost in costs if cost is not None]
    approval_wait = sum(
        _optional_number(event.attributes, _APPROVAL_WAIT_KEYS) or event.duration_ms
        for event in events
        if event.event_type == "APPROVAL"
    )
    return RunMetrics(
        total_duration_ms=max(0.0, (ended_at - started_at).total_seconds() * 1000),
        agent_latency_ms=sum(
            event.duration_ms for event in events if event.event_type == "AGENT_STEP"
        ),
        tool_latency_ms=sum(
            event.duration_ms for event in events if event.event_type == "TOOL_CALL"
        ),
        tool_call_count=sum(event.event_type == "TOOL_CALL" for event in events),
        llm_call_count=sum(event.event_type == "LLM_CALL" for event in events),
        retry_count=sum(
            (_integer(event.semantic_attributes.get("retry_index")) or 0) > 0 for event in events
        ),
        handoff_count=sum(event.event_type == "HANDOFF" for event in events),
        repeated_transition_count=repeated_count,
        error_count=sum(
            event.event_type == "ERROR" or event.status.upper() == "ERROR" for event in events
        ),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=declared_total or input_tokens + output_tokens,
        estimated_cost=sum(declared_costs) if declared_costs else None,
        approval_wait_ms=approval_wait,
        path_length=max((node.depth for node in nodes), default=-1) + 1,
        step_count=sum(event.event_type != "RUN" for event in events),
    )


def _run_status(events: list[SilverEvent], run_event: SilverEvent) -> str:
    explicit = run_event.attributes.get("agent.runtime.run.status")
    if explicit:
        return str(explicit).lower()
    if any(event.event_type == "ERROR" or event.status.upper() == "ERROR" for event in events):
        return "failed"
    return "succeeded"


def _label(event: SilverEvent) -> str:
    semantic = event.semantic_attributes
    if event.event_type == "TOOL_CALL" and semantic.get("tool_name"):
        return str(semantic["tool_name"])
    if event.event_type == "HANDOFF":
        return f"{semantic.get('from_agent', '?')} → {semantic.get('to_agent', '?')}"
    if event.event_type == "DECISION" and semantic.get("decision"):
        return str(semantic["decision"])
    return event.agent_name or event.event_type.replace("_", " ").title()


def _fingerprint(event: SilverEvent) -> str:
    semantic = event.semantic_attributes
    subject = semantic.get("tool_name") or semantic.get("decision") or event.agent_name or ""
    if event.event_type == "HANDOFF":
        subject = f"{semantic.get('from_agent')}:{semantic.get('to_agent')}"
    return f"{event.event_type}:{subject}"


def _edge(
    source: str, target: str, edge_type: str, metadata: dict[str, Any] | None = None
) -> GraphEdge:
    return GraphEdge(
        id=f"{edge_type}:{source}:{target}",
        source=source,
        target=target,
        type=edge_type,
        metadata=metadata or {},
    )


def _deduplicate_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    unique: dict[str, GraphEdge] = {}
    for edge in edges:
        unique[edge.id] = edge
    return list(unique.values())


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _first_value(events: list[SilverEvent], field: str) -> Any:
    return next(
        (getattr(event, field) for event in events if getattr(event, field) is not None), None
    )


def _number(attributes: dict[str, Any], keys: tuple[str, ...], cast: type[int]) -> int:
    value = _optional_number(attributes, keys)
    return cast(value) if value is not None else 0


def _optional_number(attributes: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    value = next((attributes[key] for key in keys if attributes.get(key) is not None), None)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


_INPUT_TOKEN_KEYS = ("gen_ai.usage.input_tokens", "llm.usage.prompt_tokens", "input_tokens")
_OUTPUT_TOKEN_KEYS = ("gen_ai.usage.output_tokens", "llm.usage.completion_tokens", "output_tokens")
_TOTAL_TOKEN_KEYS = ("gen_ai.usage.total_tokens", "llm.usage.total_tokens", "total_tokens")
_COST_KEYS = ("agent.runtime.cost", "gen_ai.usage.cost", "llm.usage.cost", "cost")
_APPROVAL_WAIT_KEYS = ("agent.runtime.approval.wait_ms", "approval.wait_ms", "wait_ms")
