import asyncio
from datetime import UTC, datetime
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from agent_runtime.analysis.baselines import project_reference_baseline
from agent_runtime.analysis.detectors import BaselineDetector, RuleConfig, RuleDetector
from agent_runtime.analysis.models import DiagnosisNarrative, InferredCause
from agent_runtime.analysis.service import AnalysisService
from agent_runtime.config import Settings
from agent_runtime.main import create_app
from agent_runtime.runs.models import ExecutionGraph, GraphNode, RunMetrics, RunRecord
from agent_runtime.runs.service import RunService
from agent_runtime.telemetry.records import SilverEvent
from agent_runtime.telemetry.storage.local import LocalJsonlTelemetryStore
from agent_runtime.telemetry.storage.memory import InMemoryTelemetryStore


def test_cold_start_rules_detect_without_history() -> None:
    run = _run("target", retry_count=3, error_count=1, status="failed")
    baseline = project_reference_baseline(run, [run])

    findings = RuleDetector().detect(run, baseline)

    assert {finding.anomaly_type for finding in findings} == {
        "excessive_retries",
        "run_failure",
    }
    assert all(finding.detector_type == "rule" for finding in findings)
    assert all(finding.baseline_comparison is None for finding in findings)


def test_rule_thresholds_and_configured_validation_are_explicit() -> None:
    run = _run(
        "target",
        tool_call_count=5,
        repeated_transition_count=1,
        approval_wait_ms=1_000,
        expected_validations="schema_check, safety_check",
        observed_validations=("schema_check",),
    )
    detector = RuleDetector(
        RuleConfig(
            excessive_retries=10,
            repeated_transitions=1,
            excessive_tool_calls=5,
            approval_wait_ms=1_000,
        )
    )

    findings = detector.detect(run, project_reference_baseline(run, []))

    assert {finding.anomaly_type for finding in findings} == {
        "repeated_transition",
        "excessive_tool_calls",
        "approval_wait",
        "missing_validation_step",
    }
    missing = next(item for item in findings if item.anomaly_type == "missing_validation_step")
    assert "safety_check" in missing.observed_fact
    assert missing.inferred_cause is None


def test_statistical_detector_uses_robust_history_and_surfaces_sample_size() -> None:
    history = [_run(f"history-{index}", total_duration_ms=100 + index) for index in range(10)]
    target = _run("target", total_duration_ms=1_000)
    baseline = project_reference_baseline(target, [*history, target])

    findings = BaselineDetector().detect(target, baseline)

    latency = next(item for item in findings if item.anomaly_type == "latency_spike")
    assert latency.baseline_comparison is not None
    assert latency.baseline_comparison.sample_size == 10
    assert latency.baseline_comparison.median == 104.5
    assert latency.baseline_comparison.current_value == 1_000
    assert latency.baseline_comparison.confidence_label == "moderate"


def test_insufficient_history_never_claims_baseline_anomaly() -> None:
    history = [_run("history", total_duration_ms=100)]
    target = _run("target", total_duration_ms=10_000)
    baseline = project_reference_baseline(target, [*history, target])

    findings = BaselineDetector().detect(target, baseline)

    assert findings == ()
    assert baseline.metrics["total_duration_ms"].sample_size == 1
    assert baseline.metrics["total_duration_ms"].confidence_label == "insufficient"


def test_evidence_grounding_discards_unreferenced_inferred_cause() -> None:
    store = InMemoryTelemetryStore()
    run = _run("target", error_count=1, status="failed")
    asyncio.run(store.upsert_gold_runs([run]))
    service = AnalysisService(store, explainer=UngroundedExplainer())

    diagnosis = asyncio.run(service.diagnose(run.run_id))

    assert diagnosis is not None
    assert diagnosis.observed_facts == tuple(
        item.observed_fact for item in diagnosis.evidence.items
    )
    assert diagnosis.inferred_causes == ()
    assert diagnosis.evidence.items[0].inferred_cause is None


def test_observed_facts_and_inferences_remain_separate() -> None:
    store = InMemoryTelemetryStore()
    run = _run("target", retry_count=4)
    asyncio.run(store.upsert_gold_runs([run]))

    diagnosis = asyncio.run(AnalysisService(store).diagnose(run.run_id))

    assert diagnosis is not None
    assert diagnosis.provider == "deterministic-fallback"
    assert diagnosis.observed_facts
    assert diagnosis.inferred_causes
    assert all(cause.is_inference for cause in diagnosis.inferred_causes)
    valid_ids = {item.evidence_id for item in diagnosis.evidence.items}
    assert all(
        set(cause.supporting_evidence_ids).issubset(valid_ids)
        for cause in diagnosis.inferred_causes
    )


def test_diagnosis_apis_return_anomalies_evidence_and_coverage() -> None:
    store = InMemoryTelemetryStore()
    run = _run("target", error_count=1, status="failed")
    asyncio.run(store.upsert_gold_runs([run]))
    app = create_app(Settings(app_env="test", _env_file=None), telemetry_store=store)

    async def request_views():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return (
                await client.get("/api/v1/runs/target/diagnosis"),
                await client.get("/api/v1/runs/target/anomalies"),
                await client.get("/api/v1/runs/target/evidence"),
            )

    diagnosis, anomalies, evidence = asyncio.run(request_views())

    assert diagnosis.status_code == anomalies.status_code == evidence.status_code == 200
    assert diagnosis.json()["status"] == "anomalies_detected"
    assert anomalies.json()["total"] == 1
    assert evidence.json()["items"][0]["anomaly_type"] == "run_failure"
    assert evidence.json()["baseline_coverage"][0]["sample_size"] == 0
    assert store.gold_diagnoses["target"].provider == "deterministic-fallback"
    assert store.gold_baselines


def test_local_gold_analysis_survives_store_restart(tmp_path: Path) -> None:
    store = LocalJsonlTelemetryStore(tmp_path)
    run = _run("target", error_count=1, status="failed")
    asyncio.run(store.upsert_gold_runs([run]))
    asyncio.run(AnalysisService(store).diagnose(run.run_id))

    restarted = LocalJsonlTelemetryStore(tmp_path)
    diagnosis = asyncio.run(restarted.get_gold_diagnosis(run.run_id))

    assert diagnosis is not None
    assert diagnosis.evidence.items[0].anomaly_type == "run_failure"
    assert asyncio.run(restarted.list_gold_baselines())[0].key.workflow_name == "checkout"


def test_run_materialization_refreshes_baseline_projection() -> None:
    store = InMemoryTelemetryStore()
    projector = RecordingProjector()
    now = datetime.now(UTC).isoformat()
    event = SilverEvent(
        event_id="trace:run",
        trace_id="trace",
        span_id="run",
        parent_span_id=None,
        timestamp=now,
        duration_ms=10,
        status="OK",
        event_type="RUN",
        ingested_at=now,
        observed_lag_ms=0,
        is_late=False,
        is_out_of_order=False,
        workflow_name="checkout",
        environment="test",
    )
    asyncio.run(store.append_silver([event]))

    asyncio.run(RunService(store, baseline_projector=projector).materialize())

    assert projector.refresh_count == 1


class UngroundedExplainer:
    provider_name = "test-llm"

    async def explain(self, evidence):
        return DiagnosisNarrative(
            impact="A provider supplied impact statement.",
            inferred_causes=(
                InferredCause(
                    statement="Unsupported cause.",
                    confidence="high",
                    supporting_evidence_ids=("invented:evidence",),
                ),
            ),
            suggested_investigations=("Inspect the evidence.",),
            evidence_sufficient=True,
        )


class RecordingProjector:
    def __init__(self) -> None:
        self.refresh_count = 0

    async def refresh_baselines(self) -> None:
        self.refresh_count += 1


def _run(
    run_id: str,
    *,
    status: str = "succeeded",
    total_duration_ms: float = 100,
    tool_call_count: int = 0,
    retry_count: int = 0,
    repeated_transition_count: int = 0,
    error_count: int = 0,
    approval_wait_ms: float = 0,
    expected_validations: str | None = None,
    observed_validations: tuple[str, ...] = (),
) -> RunRecord:
    metrics = RunMetrics(
        total_duration_ms=total_duration_ms,
        agent_latency_ms=0,
        tool_latency_ms=0,
        tool_call_count=tool_call_count,
        llm_call_count=0,
        retry_count=retry_count,
        handoff_count=0,
        repeated_transition_count=repeated_transition_count,
        error_count=error_count,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        estimated_cost=None,
        approval_wait_ms=approval_wait_ms,
        path_length=1,
        step_count=tool_call_count,
    )
    run_attributes = {}
    if expected_validations:
        run_attributes["agent.runtime.expected_validation_steps"] = expected_validations
    events = [
        {
            "event_id": f"{run_id}:run",
            "event_type": "RUN",
            "attributes": run_attributes,
            "semantic_attributes": {},
            "prompt_version": "prompt-v1",
            "model": "model-v1",
        }
    ]
    events.extend(
        {
            "event_id": f"{run_id}:checkpoint:{name}",
            "event_type": "CHECKPOINT",
            "attributes": {"agent.runtime.checkpoint.name": name},
            "semantic_attributes": {},
        }
        for name in observed_validations
    )
    nodes = tuple(
        GraphNode(
            id=f"{run_id}:node:{index}",
            span_id=f"node:{index}",
            parent_span_id=None,
            event_type="ERROR" if error_count and index == 0 else "TOOL_CALL",
            label="step",
            started_at=datetime.now(UTC).isoformat(),
            ended_at=datetime.now(UTC).isoformat(),
            duration_ms=1,
            status="ERROR" if error_count and index == 0 else "OK",
            agent_name="agent",
            depth=0,
            lane=0,
            is_concurrent=False,
            retry_index=index if index and index <= retry_count else None,
        )
        for index in range(max(tool_call_count, retry_count, error_count, 1))
    )
    return RunRecord(
        run_id=run_id,
        trace_id=run_id,
        name="test run",
        status=status,
        started_at=datetime.now(UTC).isoformat(),
        ended_at=datetime.now(UTC).isoformat(),
        materialized_at=datetime.now(UTC).isoformat(),
        organization_id=None,
        project_id=None,
        workflow_name="checkout",
        workflow_version="v1",
        environment="test",
        graph=ExecutionGraph(nodes=nodes, edges=()),
        metrics=metrics,
        events=tuple(events),
    )
