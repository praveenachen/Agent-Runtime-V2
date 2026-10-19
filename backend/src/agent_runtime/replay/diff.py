from collections import Counter
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from agent_runtime.replay.models import (
    ExecutionDifference,
    FieldDifference,
    MetricDifference,
    RuntimeDiff,
    SequenceDifference,
)
from agent_runtime.runs.models import GraphNode, RunRecord


def compare_runs(original: RunRecord, comparison: RunRecord) -> RuntimeDiff:
    original_sequence = tuple(_signature(node) for node in _ordered_steps(original))
    comparison_sequence = tuple(_signature(node) for node in _ordered_steps(comparison))
    matcher = SequenceMatcher(a=original_sequence, b=comparison_sequence, autojunk=False)
    sequence_changes = tuple(
        SequenceDifference(
            operation=tag,
            original_start=i1,
            original_end=i2,
            comparison_start=j1,
            comparison_end=j2,
            original=original_sequence[i1:i2],
            comparison=comparison_sequence[j1:j2],
        )
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    )
    original_counts = Counter(original_sequence)
    comparison_counts = Counter(comparison_sequence)
    execution = ExecutionDifference(
        original_sequence=original_sequence,
        comparison_sequence=comparison_sequence,
        sequence_changes=sequence_changes,
        added_steps=dict(comparison_counts - original_counts),
        removed_steps=dict(original_counts - comparison_counts),
        added_tools=_category_delta(original, comparison, "TOOL_CALL"),
        removed_tools=_category_delta(comparison, original, "TOOL_CALL"),
        added_handoffs=_category_delta(original, comparison, "HANDOFF"),
        removed_handoffs=_category_delta(comparison, original, "HANDOFF"),
        retry_delta=comparison.metrics.retry_count - original.metrics.retry_count,
        repeated_transition_delta=(
            comparison.metrics.repeated_transition_count
            - original.metrics.repeated_transition_count
        ),
    )
    configuration = tuple(
        FieldDifference(field, before, after, before != after)
        for field, before, after in _configuration_values(original, comparison)
    )
    outcomes = tuple(
        _metric(name, before, after, lower_is_better)
        for name, before, after, lower_is_better in (
            (
                "duration_ms",
                original.metrics.total_duration_ms,
                comparison.metrics.total_duration_ms,
                True,
            ),
            (
                "estimated_cost",
                original.metrics.estimated_cost,
                comparison.metrics.estimated_cost,
                True,
            ),
            ("total_tokens", original.metrics.total_tokens, comparison.metrics.total_tokens, True),
            (
                "tool_calls",
                original.metrics.tool_call_count,
                comparison.metrics.tool_call_count,
                True,
            ),
            ("retries", original.metrics.retry_count, comparison.metrics.retry_count, True),
            ("handoffs", original.metrics.handoff_count, comparison.metrics.handoff_count, True),
            ("status", original.status, comparison.status, False),
        )
    )
    return RuntimeDiff(
        original_run_id=original.run_id,
        comparison_run_id=comparison.run_id,
        configuration=configuration,
        execution=execution,
        outcomes=outcomes,
        generated_at=datetime.now(UTC).isoformat(),
    )


def _ordered_steps(run: RunRecord) -> list[GraphNode]:
    return sorted(
        (node for node in run.graph.nodes if node.event_type != "RUN"),
        key=lambda node: (node.started_at, node.span_id),
    )


def _signature(node: GraphNode) -> str:
    semantic = node.semantic_attributes
    subject: Any = node.agent_name or node.label
    if node.event_type == "TOOL_CALL":
        subject = semantic.get("tool_name") or node.label
    elif node.event_type == "HANDOFF":
        subject = f"{semantic.get('from_agent', '?')}->{semantic.get('to_agent', '?')}"
    elif node.event_type == "DECISION":
        subject = semantic.get("decision") or node.label
    return f"{node.event_type}:{subject}"


def _category_delta(before: RunRecord, after: RunRecord, event_type: str) -> dict[str, int]:
    left = Counter(
        _signature(node) for node in _ordered_steps(before) if node.event_type == event_type
    )
    right = Counter(
        _signature(node) for node in _ordered_steps(after) if node.event_type == event_type
    )
    return dict(right - left)


def _configuration_values(
    original: RunRecord, comparison: RunRecord
) -> tuple[tuple[str, Any, Any], ...]:
    fields = (
        ("workflow_name", original.workflow_name, comparison.workflow_name),
        (
            "workflow_version",
            _version_value(original.workflow_version),
            _version_value(comparison.workflow_version),
        ),
        ("environment", original.environment, comparison.environment),
        (
            "prompt_version",
            _version_value(_event_field(original, "prompt_version")),
            _version_value(_event_field(comparison, "prompt_version")),
        ),
        (
            "model",
            _version_value(_event_field(original, "model")),
            _version_value(_event_field(comparison, "model")),
        ),
        (
            "git_commit",
            _event_field(original, "git_commit"),
            _event_field(comparison, "git_commit"),
        ),
        (
            "config_version",
            _version_value(_attribute_value(original, "agent.runtime.config.version")),
            _version_value(_attribute_value(comparison, "agent.runtime.config.version")),
        ),
        ("tool_versions", _tool_versions(original), _tool_versions(comparison)),
    )
    return fields


def _event_field(run: RunRecord, field: str) -> Any:
    return next((event.get(field) for event in run.events if event.get(field) is not None), None)


def _attribute_value(run: RunRecord, field: str) -> Any:
    return next(
        (
            event.get("attributes", {}).get(field)
            for event in run.events
            if event.get("attributes", {}).get(field) is not None
        ),
        None,
    )


def _tool_versions(run: RunRecord) -> dict[str, str]:
    versions: dict[str, str] = {}
    for event in run.events:
        if event.get("event_type") != "TOOL_CALL":
            continue
        semantic = event.get("semantic_attributes", {})
        attributes = event.get("attributes", {})
        name = semantic.get("tool_name")
        version = attributes.get("agent.runtime.tool.version")
        if name is not None and version is not None:
            versions[str(name)] = str(version)
    return versions


def _version_value(value: Any) -> str | None:
    return str(value) if value is not None else None


def _metric(
    name: str,
    original: float | int | str | None,
    comparison: float | int | str | None,
    lower_is_better: bool,
) -> MetricDifference:
    if isinstance(original, (int, float)) and isinstance(comparison, (int, float)):
        delta = float(comparison - original)
        percent = (delta / float(original) * 100) if original else None
        assessment = (
            "unchanged"
            if delta == 0
            else ("improved" if (delta < 0) == lower_is_better else "regressed")
        )
    else:
        delta = percent = None
        if original == comparison:
            assessment = "unchanged"
        elif name == "status" and comparison == "succeeded":
            assessment = "improved"
        elif name == "status" and original == "succeeded":
            assessment = "regressed"
        else:
            assessment = "changed"
    return MetricDifference(name, original, comparison, delta, percent, assessment)
