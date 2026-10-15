from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent_runtime.control.engine import PolicyEvaluationError, match_policy, validate_conditions
from agent_runtime.control.models import (
    ApprovalRecord,
    ApprovalResolution,
    EvaluationResult,
    PolicyMatch,
    PolicyRecord,
    RuntimeContext,
)
from agent_runtime.control.ports import (
    ControlRepository,
    ProjectAuthorizer,
    RuntimeControlAdapter,
)
from agent_runtime.control.repository import ApprovalConflictError
from agent_runtime.domain.models import ApprovalState, PolicyAction
from agent_runtime.telemetry.redaction import AttributeRedactor

_ACTION_RANK = {
    PolicyAction.ALLOW: 0,
    PolicyAction.PAUSE: 1,
    PolicyAction.REQUIRE_APPROVAL: 2,
    PolicyAction.BLOCK: 3,
}


class ControlService:
    def __init__(
        self,
        repository: ControlRepository,
        authorizer: ProjectAuthorizer,
        adapter: RuntimeControlAdapter,
        *,
        service_fail_closed: bool = True,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._adapter = adapter
        self._service_fail_closed = service_fail_closed
        self._redactor = AttributeRedactor()

    async def list_policies(self, project_id: str, principal: str) -> list[PolicyRecord]:
        self._authorizer.authorize(principal, project_id, "policy:list")
        return await self._repository.list_policies(project_id)

    async def get_policy(self, policy_id: str, principal: str) -> PolicyRecord | None:
        policy = await self._repository.get_policy(policy_id)
        if policy:
            self._authorizer.authorize(principal, policy.project_id, "policy:read")
        return policy

    async def save_policy(
        self,
        *,
        policy_id: str | None,
        project_id: str,
        name: str,
        description: str | None,
        enabled: bool,
        priority: int,
        action: PolicyAction,
        conditions: dict[str, Any],
        fail_closed: bool,
        principal: str,
    ) -> PolicyRecord:
        self._authorizer.authorize(principal, project_id, "policy:write")
        validate_conditions(conditions)
        existing = await self._repository.get_policy(policy_id) if policy_id else None
        if existing and existing.project_id != project_id:
            raise PermissionError("Policy belongs to another project")
        now = datetime.now(UTC).isoformat()
        record = PolicyRecord(
            id=policy_id or "", project_id=project_id, name=name, description=description,
            enabled=enabled, priority=priority, action=action, conditions=conditions,
            fail_closed=fail_closed, created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        return await self._repository.save_policy(record)

    async def set_enabled(
        self, policy_id: str, enabled: bool, principal: str
    ) -> PolicyRecord | None:
        policy = await self.get_policy(policy_id, principal)
        if policy is None:
            return None
        return await self._repository.save_policy(replace(policy, enabled=enabled))

    async def evaluate(self, context: RuntimeContext, principal: str) -> EvaluationResult:
        self._authorizer.authorize(principal, context.project_id, "policy:evaluate")
        try:
            policies = await self._repository.list_policies(context.project_id)
        except Exception:
            return self._service_failure()
        matches: list[PolicyMatch] = []
        failures: list[PolicyMatch] = []
        for policy in policies:
            if not policy.enabled:
                continue
            try:
                matched = match_policy(policy, context)
                if matched:
                    matches.append(matched)
            except PolicyEvaluationError as exc:
                failure = PolicyMatch(
                    policy.id, policy.name,
                    PolicyAction.BLOCK if policy.fail_closed else PolicyAction.ALLOW,
                    policy.priority, (str(exc),), True,
                    "fail_closed" if policy.fail_closed else "fail_open",
                )
                failures.append(failure)
                if policy.fail_closed:
                    matches.append(failure)
        matches.sort(key=lambda item: (-_ACTION_RANK[item.action], -item.priority, item.policy_id))
        action = matches[0].action if matches else PolicyAction.ALLOW
        reason = _reason(action, matches, failures)
        approval = (
            self._approval(context, matches[0], reason)
            if action == PolicyAction.REQUIRE_APPROVAL
            else None
        )
        sanitized = self._redactor.redact(context.to_dict())
        decision_id = str(uuid4())
        decision = {
            "id": decision_id,
            "project_id": context.project_id,
            "run_id": context.run_id,
            "action": action,
            "matched_policy_ids": [item.policy_id for item in matches],
            "reason": reason,
            "context": sanitized,
            "evaluation_failed": bool(failures),
            "decision_made": not any(item.failure_behavior == "fail_closed" for item in failures),
            "failure_behavior": _failure_summary(failures),
        }
        await self._repository.record_evaluation(decision, approval)
        return EvaluationResult(
            decision_id, action, tuple(matches), tuple(failures), reason,
            approval.id if approval else None, bool(failures), decision["decision_made"],
            decision["failure_behavior"],
        )

    async def list_approvals(
        self, project_id: str, state: str | None, principal: str
    ) -> list[ApprovalRecord]:
        self._authorizer.authorize(principal, project_id, "approval:list")
        return await self._repository.list_approvals(project_id, state)

    async def get_approval(self, approval_id: str, principal: str) -> ApprovalRecord | None:
        approval = await self._repository.get_approval(approval_id)
        if approval:
            self._authorizer.authorize(principal, approval.project_id, "approval:read")
        return approval

    async def resolve(
        self, approval_id: str, state: ApprovalState, reviewer: str | None, principal: str
    ) -> ApprovalResolution | None:
        approval = await self.get_approval(approval_id, principal)
        if approval is None:
            return None
        self._authorizer.authorize(principal, approval.project_id, "approval:resolve")
        resolved, idempotent = await self._repository.resolve_approval(
            approval_id, state.value, reviewer, None
        )
        if idempotent:
            return ApprovalResolution(resolved, True, "already_applied")
        try:
            reference = (
                await self._adapter.resume(resolved)
                if state == ApprovalState.APPROVED
                else await self._adapter.stop(resolved)
            )
        except Exception:
            return ApprovalResolution(resolved, False, "adapter_failed")
        if reference:
            resolved = await self._repository.attach_integration_reference(approval_id, reference)
            return ApprovalResolution(resolved, False, "adapter_accepted")
        return ApprovalResolution(resolved, False, "not_configured")

    def _approval(
        self, context: RuntimeContext, matched: PolicyMatch, reason: str
    ) -> ApprovalRecord:
        now = datetime.now(UTC).isoformat()
        summary = context.tool_name or context.action_name or context.operation or "proposed action"
        return ApprovalRecord(
            id=str(uuid4()), project_id=context.project_id, run_id=context.run_id,
            policy_id=matched.policy_id, state=ApprovalState.PENDING,
            action_summary=summary, context=self._redactor.redact(context.to_dict()),
            workflow_name=context.workflow_name, agent_name=context.agent_name,
            tool_name=context.tool_name, operation=context.operation,
            confidence=context.confidence,
            proposed_inputs=self._redactor.redact(context.proposed_inputs),
            match_reason=reason, reviewer_reference=None, resolved_at=None,
            integration_reference=None, created_at=now, updated_at=now,
        )

    def _service_failure(self) -> EvaluationResult:
        action = PolicyAction.BLOCK if self._service_fail_closed else PolicyAction.ALLOW
        behavior = "fail_closed" if self._service_fail_closed else "fail_open"
        return EvaluationResult(
            None, action, (), (),
            f"Policy service failed; {behavior} fallback applied. No policy decision was made.",
            None, True, False, behavior,
        )


def _reason(action: PolicyAction, matches: list[PolicyMatch], failures: list[PolicyMatch]) -> str:
    if not matches:
        names = ", ".join(item.policy_name for item in failures)
        suffix = f" Failed policies skipped open: {names}." if failures else ""
        return "No enabled policy matched; default ALLOW." + suffix
    winner = matches[0]
    return (
        f"{winner.policy_name} selected {action.value}. All matches are returned; "
        "safety action precedence resolved conflicts before policy priority."
    )


def _failure_summary(failures: list[PolicyMatch]) -> str | None:
    if not failures:
        return None
    has_closed_failure = any(item.failure_behavior == "fail_closed" for item in failures)
    return "fail_closed" if has_closed_failure else "fail_open"


__all__ = ["ApprovalConflictError", "ControlService"]
