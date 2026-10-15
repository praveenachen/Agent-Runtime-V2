from dataclasses import dataclass
from typing import Protocol

from agent_runtime.analysis.baselines import BASELINE_METRICS
from agent_runtime.analysis.models import BaselineComparison, BaselineRecord, EvidenceItem
from agent_runtime.runs.models import RunRecord


class Detector(Protocol):
    name: str

    def detect(self, run: RunRecord, baseline: BaselineRecord) -> tuple[EvidenceItem, ...]: ...


@dataclass(frozen=True, slots=True)
class RuleConfig:
    excessive_retries: int = 3
    repeated_transitions: int = 2
    excessive_tool_calls: int = 20
    approval_wait_ms: float = 300_000


class RuleDetector:
    name = "rule"

    def __init__(self, config: RuleConfig | None = None) -> None:
        self._config = config or RuleConfig()

    def detect(self, run: RunRecord, baseline: BaselineRecord) -> tuple[EvidenceItem, ...]:
        del baseline
        findings: list[EvidenceItem] = []
        metrics = run.metrics
        if metrics.retry_count >= self._config.excessive_retries:
            findings.append(
                _rule_finding(
                    run,
                    "excessive_retries",
                    "warning",
                    f"The run recorded {metrics.retry_count} retries; the configured limit is "
                    f"{self._config.excessive_retries}.",
                    {
                        "retry_count": metrics.retry_count,
                        "threshold": self._config.excessive_retries,
                    },
                    _nodes(run, retry=True),
                    "Inspect the retried operations and their error or timeout evidence.",
                )
            )
        if metrics.repeated_transition_count >= self._config.repeated_transitions:
            findings.append(
                _rule_finding(
                    run,
                    "repeated_transition",
                    "warning",
                    f"The execution graph contains {metrics.repeated_transition_count} repeated "
                    "semantic transitions.",
                    {
                        "repeated_transition_count": metrics.repeated_transition_count,
                        "threshold": self._config.repeated_transitions,
                    },
                    tuple(
                        edge.target
                        for edge in run.graph.edges
                        if edge.type == "repeated_transition"
                    ),
                    "Inspect the repeated steps for an unmet exit condition.",
                )
            )
        if metrics.tool_call_count >= self._config.excessive_tool_calls:
            findings.append(
                _rule_finding(
                    run,
                    "excessive_tool_calls",
                    "warning",
                    f"The run made {metrics.tool_call_count} tool calls; the configured limit is "
                    f"{self._config.excessive_tool_calls}.",
                    {
                        "tool_call_count": metrics.tool_call_count,
                        "threshold": self._config.excessive_tool_calls,
                    },
                    _nodes(run, event_type="TOOL_CALL"),
                    "Review repeated or unnecessary tool invocations.",
                )
            )
        if metrics.error_count > 0 or run.status == "failed":
            findings.append(
                _rule_finding(
                    run,
                    "run_failure",
                    "critical" if run.status == "failed" else "warning",
                    f"The run status is {run.status} and contains {metrics.error_count} error "
                    "event(s).",
                    {"run_status": run.status, "error_count": metrics.error_count},
                    _nodes(run, event_type="ERROR"),
                    "Inspect the recorded error spans before changing runtime behavior.",
                )
            )
        if metrics.approval_wait_ms >= self._config.approval_wait_ms:
            findings.append(
                _rule_finding(
                    run,
                    "approval_wait",
                    "warning",
                    f"Approval waiting time was {metrics.approval_wait_ms:.0f} ms; the configured "
                    f"limit is {self._config.approval_wait_ms:.0f} ms.",
                    {
                        "approval_wait_ms": metrics.approval_wait_ms,
                        "threshold": self._config.approval_wait_ms,
                    },
                    _nodes(run, event_type="APPROVAL"),
                    "Check reviewer availability and the approval routing path.",
                )
            )
        findings.extend(_missing_validation_findings(run))
        return tuple(findings)


class BaselineDetector:
    name = "statistical"

    def detect(self, run: RunRecord, baseline: BaselineRecord) -> tuple[EvidenceItem, ...]:
        findings: list[EvidenceItem] = []
        for metric_name in BASELINE_METRICS:
            metric_baseline = baseline.metrics.get(metric_name)
            if metric_baseline is None or metric_baseline.sample_size < 2:
                continue
            current = getattr(run.metrics, metric_name)
            if current is None:
                continue
            robust_limit = metric_baseline.median + 3 * metric_baseline.median_absolute_deviation
            threshold = max(metric_baseline.p90, robust_limit)
            if float(current) <= threshold or float(current) <= metric_baseline.median:
                continue
            comparison = BaselineComparison(
                metric=metric_name,
                current_value=float(current),
                median=metric_baseline.median,
                p90=metric_baseline.p90,
                deviation_from_median=float(current) - metric_baseline.median,
                threshold=threshold,
                sample_size=metric_baseline.sample_size,
                confidence=metric_baseline.confidence,
                confidence_label=metric_baseline.confidence_label,
                baseline_scope=baseline.key,
            )
            findings.append(
                EvidenceItem(
                    evidence_id=f"baseline:{metric_name}",
                    anomaly_type=_baseline_category(metric_name),
                    detector_type=self.name,
                    severity="warning" if metric_baseline.confidence < 0.5 else "high",
                    observed_fact=(
                        f"{_display_name(metric_name)} is {float(current):.2f}, above the "
                        f"historical threshold of {threshold:.2f}."
                    ),
                    metric_evidence={metric_name: float(current)},
                    baseline_comparison=comparison,
                    recommendation=(
                        f"Compare the run with typical {_display_name(metric_name)} behavior."
                    ),
                )
            )
        return tuple(findings)


def _rule_finding(
    run: RunRecord,
    anomaly_type: str,
    severity: str,
    observed_fact: str,
    metric_evidence: dict[str, float | int | str | None],
    node_ids: tuple[str, ...],
    recommendation: str,
) -> EvidenceItem:
    graph_ids = tuple(
        edge.id for edge in run.graph.edges if edge.source in node_ids or edge.target in node_ids
    )
    return EvidenceItem(
        evidence_id=f"rule:{anomaly_type}",
        anomaly_type=anomaly_type,
        detector_type="rule",
        severity=severity,
        observed_fact=observed_fact,
        metric_evidence=metric_evidence,
        graph_evidence=graph_ids,
        affected_node_ids=node_ids,
        recommendation=recommendation,
    )


def _missing_validation_findings(run: RunRecord) -> list[EvidenceItem]:
    expected = _expected_validations(run)
    if not expected:
        return []
    observed = {
        str(
            event.get("semantic_attributes", {}).get("checkpoint_name")
            or event.get("attributes", {}).get("agent.runtime.checkpoint.name")
            or event.get("attributes", {}).get("checkpoint_name")
        )
        for event in run.events
        if event.get("event_type") == "CHECKPOINT"
    }
    missing = sorted(expected - observed)
    if not missing:
        return []
    return [
        _rule_finding(
            run,
            "missing_validation_step",
            "high",
            "The run omitted configured validation step(s): " + ", ".join(missing) + ".",
            {"expected_count": len(expected), "missing_count": len(missing)},
            (),
            "Verify the workflow path and restore the declared validation checkpoint(s).",
        )
    ]


def _expected_validations(run: RunRecord) -> set[str]:
    value = next(
        (
            event.get("attributes", {}).get("agent.runtime.expected_validation_steps")
            for event in run.events
            if event.get("event_type") == "RUN"
            and event.get("attributes", {}).get("agent.runtime.expected_validation_steps")
        ),
        None,
    )
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    return set()


def _nodes(
    run: RunRecord,
    *,
    event_type: str | None = None,
    retry: bool = False,
) -> tuple[str, ...]:
    return tuple(
        node.id
        for node in run.graph.nodes
        if (event_type is None or node.event_type == event_type)
        and (not retry or (node.retry_index or 0) > 0)
    )


def _baseline_category(metric_name: str) -> str:
    return {
        "total_duration_ms": "latency_spike",
        "estimated_cost": "cost_spike",
        "total_tokens": "token_spike",
        "tool_call_count": "unusual_tool_call_count",
        "retry_count": "unusual_retry_count",
        "handoff_count": "unusual_handoff_count",
        "step_count": "unusual_step_count",
        "path_length": "unusual_path_depth",
    }[metric_name]


def _display_name(metric_name: str) -> str:
    return metric_name.replace("_ms", "").replace("_", " ")
