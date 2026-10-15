from datetime import UTC, datetime

from agent_runtime.analysis.baselines import (
    BASELINE_METRICS,
    project_baselines,
    project_reference_baseline,
)
from agent_runtime.analysis.detectors import BaselineDetector, Detector, RuleDetector
from agent_runtime.analysis.explainers import (
    DeterministicDiagnosisExplainer,
    DiagnosisExplainer,
)
from agent_runtime.analysis.models import (
    BaselineCoverage,
    DiagnosisNarrative,
    DiagnosisRecord,
    EvidencePackage,
)
from agent_runtime.telemetry.ports import TelemetryAnalyticsStore


class AnalysisService:
    def __init__(
        self,
        store: TelemetryAnalyticsStore,
        *,
        detectors: tuple[Detector, ...] | None = None,
        explainer: DiagnosisExplainer | None = None,
    ) -> None:
        self._store = store
        self._detectors = detectors or (RuleDetector(), BaselineDetector())
        self._explainer = explainer or DeterministicDiagnosisExplainer()

    async def refresh_baselines(self) -> None:
        history = await self._store.list_gold_runs()
        projected = project_baselines(history)
        if projected:
            await self._store.upsert_gold_baselines(projected)

    async def diagnose(self, run_id: str) -> DiagnosisRecord | None:
        target = await self._store.get_gold_run(run_id)
        if target is None:
            return None
        history = await self._store.list_gold_runs()
        await self.refresh_baselines()
        reference = project_reference_baseline(target, history)
        items = tuple(
            finding
            for detector in self._detectors
            for finding in detector.detect(target, reference)
        )
        generated_at = datetime.now(UTC).isoformat()
        evidence = EvidencePackage(
            run_id=run_id,
            generated_at=generated_at,
            items=tuple(sorted(items, key=_evidence_sort_key)),
            baseline_coverage=_coverage(reference),
        )
        narrative = _ground_narrative(await self._explainer.explain(evidence), evidence)
        diagnosis = DiagnosisRecord(
            diagnosis_id=run_id,
            run_id=run_id,
            generated_at=generated_at,
            status="anomalies_detected" if evidence.items else "no_anomalies",
            provider=self._explainer.provider_name,
            observed_facts=tuple(item.observed_fact for item in evidence.items),
            impact=narrative.impact,
            inferred_causes=narrative.inferred_causes,
            suggested_investigations=narrative.suggested_investigations,
            evidence_sufficient=narrative.evidence_sufficient,
            evidence=evidence,
        )
        await self._store.upsert_gold_diagnoses([diagnosis])
        return diagnosis


def _coverage(baseline) -> tuple[BaselineCoverage, ...]:
    coverage = []
    for metric_name in BASELINE_METRICS:
        metric = baseline.metrics.get(metric_name)
        coverage.append(
            BaselineCoverage(
                metric=metric_name,
                sample_size=metric.sample_size if metric else 0,
                confidence=metric.confidence if metric else 0.0,
                confidence_label=metric.confidence_label if metric else "insufficient",
                baseline_scope=baseline.key,
            )
        )
    return tuple(coverage)


def _ground_narrative(
    narrative: DiagnosisNarrative,
    evidence: EvidencePackage,
) -> DiagnosisNarrative:
    valid_ids = {item.evidence_id for item in evidence.items}
    grounded_causes = tuple(
        cause
        for cause in narrative.inferred_causes
        if cause.supporting_evidence_ids
        and set(cause.supporting_evidence_ids).issubset(valid_ids)
        and cause.is_inference
    )
    return DiagnosisNarrative(
        impact=narrative.impact,
        inferred_causes=grounded_causes,
        suggested_investigations=narrative.suggested_investigations,
        evidence_sufficient=bool(evidence.items) and narrative.evidence_sufficient,
    )


def _evidence_sort_key(item) -> tuple[int, str]:
    severity = {"critical": 0, "high": 1, "warning": 2, "info": 3}
    return severity.get(item.severity, 4), item.anomaly_type
