from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BaselineKey:
    workflow_name: str
    environment: str
    workflow_version: str | None = None
    prompt_version: str | None = None
    model: str | None = None

    @property
    def id(self) -> str:
        values = (
            self.workflow_name,
            self.environment,
            self.workflow_version or "*",
            self.prompt_version or "*",
            self.model or "*",
        )
        return "|".join(str(value) for value in values)


@dataclass(frozen=True, slots=True)
class MetricBaseline:
    metric: str
    sample_size: int
    median: float
    p90: float
    median_absolute_deviation: float
    minimum: float
    maximum: float
    confidence: float
    confidence_label: str


@dataclass(frozen=True, slots=True)
class BaselineRecord:
    baseline_id: str
    key: BaselineKey
    updated_at: str
    run_count: int
    metrics: dict[str, MetricBaseline]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BaselineRecord":
        return cls(
            baseline_id=payload["baseline_id"],
            key=BaselineKey(**payload["key"]),
            updated_at=payload["updated_at"],
            run_count=payload["run_count"],
            metrics={name: MetricBaseline(**metric) for name, metric in payload["metrics"].items()},
        )


@dataclass(frozen=True, slots=True)
class BaselineComparison:
    metric: str
    current_value: float
    median: float
    p90: float
    deviation_from_median: float
    threshold: float
    sample_size: int
    confidence: float
    confidence_label: str
    baseline_scope: BaselineKey


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    anomaly_type: str
    detector_type: str
    severity: str
    observed_fact: str
    metric_evidence: dict[str, float | int | str | None] = field(default_factory=dict)
    graph_evidence: tuple[str, ...] = ()
    baseline_comparison: BaselineComparison | None = None
    affected_node_ids: tuple[str, ...] = ()
    inferred_cause: str | None = None
    recommendation: str | None = None


@dataclass(frozen=True, slots=True)
class BaselineCoverage:
    metric: str
    sample_size: int
    confidence: float
    confidence_label: str
    baseline_scope: BaselineKey


@dataclass(frozen=True, slots=True)
class EvidencePackage:
    run_id: str
    generated_at: str
    items: tuple[EvidenceItem, ...]
    baseline_coverage: tuple[BaselineCoverage, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InferredCause:
    statement: str
    confidence: str
    supporting_evidence_ids: tuple[str, ...]
    is_inference: bool = True


@dataclass(frozen=True, slots=True)
class DiagnosisNarrative:
    impact: str
    inferred_causes: tuple[InferredCause, ...]
    suggested_investigations: tuple[str, ...]
    evidence_sufficient: bool


@dataclass(frozen=True, slots=True)
class DiagnosisRecord:
    diagnosis_id: str
    run_id: str
    generated_at: str
    status: str
    provider: str
    observed_facts: tuple[str, ...]
    impact: str
    inferred_causes: tuple[InferredCause, ...]
    suggested_investigations: tuple[str, ...]
    evidence_sufficient: bool
    evidence: EvidencePackage

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DiagnosisRecord":
        evidence_payload = payload["evidence"]
        evidence = EvidencePackage(
            run_id=evidence_payload["run_id"],
            generated_at=evidence_payload["generated_at"],
            items=tuple(_evidence_from_dict(item) for item in evidence_payload["items"]),
            baseline_coverage=tuple(
                BaselineCoverage(
                    **{
                        **coverage,
                        "baseline_scope": BaselineKey(**coverage["baseline_scope"]),
                    }
                )
                for coverage in evidence_payload["baseline_coverage"]
            ),
        )
        return cls(
            **{
                key: value
                for key, value in payload.items()
                if key
                not in {
                    "evidence",
                    "inferred_causes",
                    "observed_facts",
                    "suggested_investigations",
                }
            },
            observed_facts=tuple(payload["observed_facts"]),
            inferred_causes=tuple(
                InferredCause(
                    **{
                        **cause,
                        "supporting_evidence_ids": tuple(cause["supporting_evidence_ids"]),
                    }
                )
                for cause in payload["inferred_causes"]
            ),
            suggested_investigations=tuple(payload["suggested_investigations"]),
            evidence=evidence,
        )


def _evidence_from_dict(payload: dict[str, Any]) -> EvidenceItem:
    comparison = payload.get("baseline_comparison")
    if comparison:
        comparison = BaselineComparison(
            **{
                **comparison,
                "baseline_scope": BaselineKey(**comparison["baseline_scope"]),
            }
        )
    return EvidenceItem(
        **{
            **payload,
            "graph_evidence": tuple(payload.get("graph_evidence", ())),
            "affected_node_ids": tuple(payload.get("affected_node_ids", ())),
            "baseline_comparison": comparison,
        }
    )
