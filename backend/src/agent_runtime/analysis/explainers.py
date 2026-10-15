from typing import Protocol

from agent_runtime.analysis.models import (
    DiagnosisNarrative,
    EvidencePackage,
    InferredCause,
)


class DiagnosisExplainer(Protocol):
    provider_name: str

    async def explain(self, evidence: EvidencePackage) -> DiagnosisNarrative: ...


class DeterministicDiagnosisExplainer:
    provider_name = "deterministic-fallback"

    async def explain(self, evidence: EvidencePackage) -> DiagnosisNarrative:
        if not evidence.items:
            return DiagnosisNarrative(
                impact="No rule or baseline anomaly was detected in the available evidence.",
                inferred_causes=(),
                suggested_investigations=(
                    "Continue collecting comparable run history to improve baseline coverage.",
                ),
                evidence_sufficient=False,
            )
        severity = {item.severity for item in evidence.items}
        impact = (
            "The run failed or contains high-severity behavioral evidence."
            if severity & {"critical", "high"}
            else "The run completed with behavior that warrants investigation."
        )
        causes = tuple(
            cause
            for item in evidence.items
            if (cause := _inference(item.anomaly_type, item.evidence_id)) is not None
        )
        recommendations = tuple(
            dict.fromkeys(
                item.recommendation for item in evidence.items if item.recommendation is not None
            )
        )
        return DiagnosisNarrative(
            impact=impact,
            inferred_causes=causes,
            suggested_investigations=recommendations,
            evidence_sufficient=True,
        )


def _inference(anomaly_type: str, evidence_id: str) -> InferredCause | None:
    statement = {
        "excessive_retries": (
            "An unstable dependency or unmet completion condition may be causing retries."
        ),
        "repeated_transition": (
            "The workflow may be revisiting a step because an exit condition was not met."
        ),
        "excessive_tool_calls": "The workflow may be making redundant tool choices.",
        "approval_wait": "Reviewer availability or approval routing may be delaying completion.",
        "missing_validation_step": (
            "A branch may have bypassed the configured validation checkpoint."
        ),
        "latency_spike": (
            "A slower dependency or changed execution path may have increased latency."
        ),
        "cost_spike": "Higher model usage or a longer execution path may have increased cost.",
        "token_spike": "A larger context or response may have increased token usage.",
        "unusual_tool_call_count": "A changed decision path may have increased tool usage.",
        "unusual_retry_count": "A less stable operation may have increased retries.",
        "unusual_handoff_count": "A changed routing path may have increased agent handoffs.",
        "unusual_step_count": "A changed or repeated path may have increased run steps.",
        "unusual_path_depth": "A deeper execution branch may have changed run behavior.",
    }.get(anomaly_type)
    if statement is None:
        return None
    return InferredCause(
        statement=statement,
        confidence="low",
        supporting_evidence_ids=(evidence_id,),
    )
