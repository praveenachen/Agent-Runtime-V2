from collections import defaultdict
from datetime import UTC, datetime
from statistics import median

from agent_runtime.analysis.models import BaselineKey, BaselineRecord, MetricBaseline
from agent_runtime.runs.models import RunRecord

BASELINE_METRICS = (
    "total_duration_ms",
    "estimated_cost",
    "total_tokens",
    "tool_call_count",
    "retry_count",
    "handoff_count",
    "step_count",
    "path_length",
)


def baseline_key(run: RunRecord) -> BaselineKey:
    return BaselineKey(
        workflow_name=run.workflow_name or "unknown-workflow",
        environment=run.environment or "unknown-environment",
        workflow_version=run.workflow_version,
        prompt_version=_event_field(run, "prompt_version"),
        model=_event_field(run, "model"),
    )


def project_baselines(runs: list[RunRecord]) -> tuple[BaselineRecord, ...]:
    grouped: dict[BaselineKey, list[RunRecord]] = defaultdict(list)
    for run in runs:
        grouped[baseline_key(run)].append(run)
    return tuple(_project_group(key, group) for key, group in grouped.items())


def project_reference_baseline(target: RunRecord, history: list[RunRecord]) -> BaselineRecord:
    key = baseline_key(target)
    compatible = [
        run for run in history if run.run_id != target.run_id and baseline_key(run) == key
    ]
    return _project_group(key, compatible)


def _project_group(key: BaselineKey, runs: list[RunRecord]) -> BaselineRecord:
    metrics: dict[str, MetricBaseline] = {}
    for metric_name in BASELINE_METRICS:
        values = [value for run in runs if (value := _metric_value(run, metric_name)) is not None]
        if values:
            metrics[metric_name] = _metric_baseline(metric_name, values)
    return BaselineRecord(
        baseline_id=key.id,
        key=key,
        updated_at=datetime.now(UTC).isoformat(),
        run_count=len(runs),
        metrics=metrics,
    )


def _metric_baseline(metric_name: str, values: list[float]) -> MetricBaseline:
    ordered = sorted(values)
    center = float(median(ordered))
    deviations = [abs(value - center) for value in ordered]
    sample_size = len(ordered)
    confidence = round(min(1.0, sample_size / 20), 3)
    return MetricBaseline(
        metric=metric_name,
        sample_size=sample_size,
        median=center,
        p90=_percentile(ordered, 0.9),
        median_absolute_deviation=float(median(deviations)),
        minimum=ordered[0],
        maximum=ordered[-1],
        confidence=confidence,
        confidence_label=_confidence_label(sample_size),
    )


def _percentile(values: list[float], fraction: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _confidence_label(sample_size: int) -> str:
    if sample_size < 2:
        return "insufficient"
    if sample_size < 5:
        return "low"
    if sample_size < 20:
        return "moderate"
    return "high"


def _metric_value(run: RunRecord, metric_name: str) -> float | None:
    value = getattr(run.metrics, metric_name)
    if value is None:
        return None
    return float(value)


def _event_field(run: RunRecord, field: str) -> str | None:
    return next((str(event[field]) for event in run.events if event.get(field) is not None), None)
