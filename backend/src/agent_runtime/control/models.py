from dataclasses import asdict, dataclass, field
from typing import Any

from agent_runtime.domain.models import ApprovalState, PolicyAction


@dataclass(frozen=True, slots=True)
class PolicyRecord:
    id: str
    project_id: str
    name: str
    description: str | None
    enabled: bool
    priority: int
    action: PolicyAction
    conditions: dict[str, Any]
    fail_closed: bool
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    project_id: str
    run_id: str
    workflow_name: str | None = None
    agent_name: str | None = None
    tool_name: str | None = None
    action_name: str | None = None
    operation: str | None = None
    side_effect: bool | None = None
    replayable: bool | None = None
    confidence: float | None = None
    current_cost: float | None = None
    tool_call_count: int | None = None
    retry_count: int | None = None
    repeated_transition_count: int | None = None
    proposed_inputs: dict[str, Any] = field(default_factory=dict)
    control_reference: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PolicyMatch:
    policy_id: str
    policy_name: str
    action: PolicyAction
    priority: int
    explanation: tuple[str, ...]
    evaluation_failed: bool = False
    failure_behavior: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    decision_id: str | None
    action: PolicyAction
    matched_policies: tuple[PolicyMatch, ...]
    policy_failures: tuple[PolicyMatch, ...]
    reason: str
    approval_request_id: str | None
    evaluation_failed: bool
    decision_made: bool
    failure_behavior: str | None
    authorization_source: str = "direct_policy"
    authorizing_approval_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    id: str
    project_id: str
    run_id: str
    policy_id: str | None
    state: ApprovalState
    action_summary: str
    context: dict[str, Any]
    workflow_name: str | None
    agent_name: str | None
    tool_name: str | None
    operation: str | None
    confidence: float | None
    proposed_inputs: dict[str, Any]
    match_reason: str
    reviewer_reference: str | None
    resolved_at: str | None
    integration_reference: str | None
    created_at: str
    updated_at: str
    policy_revision: str | None = None
    control_reference: str | None = None
    context_hash: str | None = None
    expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ApprovalResolution:
    approval: ApprovalRecord
    idempotent: bool
    integration_status: str

    def to_dict(self) -> dict[str, Any]:
        payload = self.approval.to_dict()
        payload.update(
            idempotent=self.idempotent,
            integration_status=self.integration_status,
        )
        return payload
