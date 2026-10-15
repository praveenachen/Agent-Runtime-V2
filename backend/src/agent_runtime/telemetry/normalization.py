from datetime import UTC, datetime
from typing import Any

from agent_runtime.telemetry.records import BronzeSpanRecord, SilverEvent

SUPPORTED_EVENT_TYPES = {
    "RUN",
    "AGENT_STEP",
    "LLM_CALL",
    "TOOL_CALL",
    "DECISION",
    "HANDOFF",
    "APPROVAL",
    "CHECKPOINT",
    "ERROR",
}

_GEN_AI_OPERATION_TYPES = {
    "chat": "LLM_CALL",
    "text_completion": "LLM_CALL",
    "generate_content": "LLM_CALL",
    "execute_tool": "TOOL_CALL",
    "invoke_agent": "AGENT_STEP",
}

_COMMON_ALIASES = {
    "organization_id": ("agent.runtime.organization.id", "organization.id", "organization_id"),
    "project_id": ("agent.runtime.project.id", "project.id", "project_id"),
    "workflow_name": ("agent.runtime.workflow.name", "workflow.name", "workflow_name"),
    "workflow_version": (
        "agent.runtime.workflow.version",
        "workflow.version",
        "workflow_version",
    ),
    "environment": ("deployment.environment.name", "environment"),
    "agent_name": ("gen_ai.agent.name", "agent.name", "agent_name"),
    "prompt_version": ("agent.runtime.prompt.version", "prompt.version", "prompt_version"),
    "model": (
        "gen_ai.response.model",
        "gen_ai.request.model",
        "model",
    ),
    "git_commit": ("vcs.ref.head.revision", "git.commit", "git_commit"),
}

_SEMANTIC_ALIASES = {
    "TOOL_CALL": {
        "tool_name": ("gen_ai.tool.name", "tool.name", "tool_name"),
        "operation": ("agent.runtime.tool.operation", "tool.operation", "operation"),
        "success": ("agent.runtime.tool.success", "tool.success", "success"),
        "latency_ms": ("agent.runtime.tool.latency_ms", "tool.latency_ms", "latency_ms"),
        "side_effect": ("agent.runtime.tool.side_effect", "tool.side_effect", "side_effect"),
        "replayable": ("agent.runtime.tool.replayable", "tool.replayable", "replayable"),
        "input_ref": ("agent.runtime.tool.input_ref", "tool.input_ref", "input_ref"),
        "output_ref": ("agent.runtime.tool.output_ref", "tool.output_ref", "output_ref"),
        "retry_index": ("agent.runtime.retry_index", "retry_index"),
    },
    "DECISION": {
        "decision": ("agent.runtime.decision", "decision"),
        "confidence": ("agent.runtime.decision.confidence", "decision.confidence", "confidence"),
        "structured_reason": (
            "agent.runtime.decision.structured_reason",
            "decision.structured_reason",
            "structured_reason",
        ),
    },
    "HANDOFF": {
        "from_agent": ("agent.runtime.handoff.from_agent", "handoff.from_agent", "from_agent"),
        "to_agent": ("agent.runtime.handoff.to_agent", "handoff.to_agent", "to_agent"),
        "reason": ("agent.runtime.handoff.reason", "handoff.reason", "reason"),
    },
    "ERROR": {
        "error_type": ("error.type", "exception.type", "error_type"),
        "message_safe": ("agent.runtime.error.message_safe", "error.message_safe", "message_safe"),
        "retryable": ("agent.runtime.error.retryable", "error.retryable", "retryable"),
        "retry_index": ("agent.runtime.retry_index", "retry_index"),
    },
}


class SemanticNormalizer:
    def __init__(self, *, late_after_seconds: int = 300) -> None:
        self._late_after_seconds = late_after_seconds
        self._trace_watermarks: dict[str, int] = {}

    def normalize(self, record: BronzeSpanRecord) -> SilverEvent | None:
        resource_attributes = record.resource.get("attributes", {})
        span_attributes = record.span.get("attributes", {})
        attributes = {**resource_attributes, **span_attributes}
        event_type = _event_type(attributes)
        if event_type is None:
            return None

        start_nanos = int(record.span.get("start_time_unix_nano", 0))
        end_nanos = int(record.span.get("end_time_unix_nano", start_nanos))
        received_at = datetime.fromisoformat(record.received_at)
        timestamp = datetime.fromtimestamp(start_nanos / 1_000_000_000, tz=UTC)
        observed_lag_ms = max(0.0, (received_at - timestamp).total_seconds() * 1000)
        previous_watermark = self._trace_watermarks.get(record.trace_id)
        is_out_of_order = previous_watermark is not None and start_nanos < previous_watermark
        self._trace_watermarks[record.trace_id] = max(previous_watermark or 0, start_nanos)

        common = {
            field: _first(attributes, aliases) for field, aliases in _COMMON_ALIASES.items()
        }
        semantic = {
            field: value
            for field, aliases in _SEMANTIC_ALIASES.get(event_type, {}).items()
            if (value := _first(attributes, aliases)) is not None
        }
        return SilverEvent(
            event_id=record.record_id,
            trace_id=record.trace_id,
            span_id=record.span_id,
            parent_span_id=record.parent_span_id,
            timestamp=timestamp.isoformat(),
            duration_ms=max(0.0, (end_nanos - start_nanos) / 1_000_000),
            status=str(record.span.get("status", {}).get("code", "UNSET")),
            event_type=event_type,
            ingested_at=record.received_at,
            observed_lag_ms=observed_lag_ms,
            is_late=observed_lag_ms > self._late_after_seconds * 1000,
            is_out_of_order=is_out_of_order,
            semantic_attributes=semantic,
            attributes=attributes,
            **common,
        )


def _event_type(attributes: dict[str, Any]) -> str | None:
    explicit = _first(
        attributes,
        ("agent.runtime.event_type", "agent.event_type", "event_type"),
    )
    if explicit is not None:
        candidate = str(explicit).upper()
        return candidate if candidate in SUPPORTED_EVENT_TYPES else None
    operation = attributes.get("gen_ai.operation.name")
    if operation is not None:
        return _GEN_AI_OPERATION_TYPES.get(str(operation).lower())
    if "error.type" in attributes or "exception.type" in attributes:
        return "ERROR"
    return None


def _first(attributes: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        value = attributes.get(alias)
        if value is not None:
            return value
    return None

