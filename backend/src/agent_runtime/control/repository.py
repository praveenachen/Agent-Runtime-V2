from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from agent_runtime.control.models import ApprovalRecord, PolicyRecord
from agent_runtime.domain.models import (
    Approval,
    ApprovalAuditEvent,
    ApprovalState,
    Policy,
    PolicyDecision,
)


class ApprovalConflictError(RuntimeError):
    pass


class InMemoryControlRepository:
    def __init__(self) -> None:
        self.policies: dict[str, PolicyRecord] = {}
        self.approvals: dict[str, ApprovalRecord] = {}
        self.decisions: dict[str, dict] = {}
        self.audit_events: list[dict] = []

    async def list_policies(self, project_id: str) -> list[PolicyRecord]:
        return [item for item in self.policies.values() if item.project_id == project_id]

    async def get_policy(self, policy_id: str) -> PolicyRecord | None:
        return self.policies.get(policy_id)

    async def save_policy(self, policy: PolicyRecord) -> PolicyRecord:
        now = datetime.now(UTC).isoformat()
        stored = replace(
            policy,
            id=policy.id or str(uuid4()),
            created_at=policy.created_at or now,
            updated_at=now,
        )
        self.policies[stored.id] = stored
        return stored

    async def delete_policy(self, policy_id: str) -> None:
        self.policies.pop(policy_id, None)

    async def record_evaluation(self, decision: dict, approval: ApprovalRecord | None) -> str:
        identifier = decision.get("id") or str(uuid4())
        self.decisions[identifier] = {**decision, "id": identifier}
        if approval:
            now = datetime.now(UTC).isoformat()
            stored = replace(
                approval,
                id=approval.id or str(uuid4()),
                created_at=approval.created_at or now,
                updated_at=now,
            )
            self.approvals[stored.id] = stored
            self.audit_events.append({"approval_id": stored.id, "event_type": "created"})
        return identifier

    async def list_approvals(self, project_id: str, state: str | None) -> list[ApprovalRecord]:
        return [
            item for item in self.approvals.values()
            if item.project_id == project_id and (state is None or item.state.value == state)
        ]

    async def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        return self.approvals.get(approval_id)

    async def resolve_approval(
        self, approval_id: str, state: str, reviewer: str | None,
        integration_reference: str | None,
    ) -> tuple[ApprovalRecord, bool]:
        record = self.approvals[approval_id]
        desired = ApprovalState(state)
        if record.state == desired:
            return record, True
        if record.state != ApprovalState.PENDING:
            raise ApprovalConflictError("Approval has already been resolved differently")
        now = datetime.now(UTC).isoformat()
        resolved = replace(
            record, state=desired, reviewer_reference=reviewer, resolved_at=now,
            integration_reference=integration_reference, updated_at=now,
        )
        self.approvals[approval_id] = resolved
        self.audit_events.append(
            {"approval_id": approval_id, "event_type": state, "actor": reviewer}
        )
        return resolved, False

    async def attach_integration_reference(
        self, approval_id: str, reference: str
    ) -> ApprovalRecord:
        record = replace(self.approvals[approval_id], integration_reference=reference)
        self.approvals[approval_id] = record
        return record


class SqlAlchemyControlRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    async def list_policies(self, project_id: str) -> list[PolicyRecord]:
        with self._sessions() as session:
            entities = session.scalars(
                select(Policy).where(Policy.project_id == UUID(project_id))
                .order_by(Policy.priority.desc(), Policy.name)
            ).all()
            return [_policy(entity) for entity in entities]

    async def get_policy(self, policy_id: str) -> PolicyRecord | None:
        with self._sessions() as session:
            entity = session.get(Policy, _uuid(policy_id))
            return _policy(entity) if entity else None

    async def save_policy(self, policy: PolicyRecord) -> PolicyRecord:
        with self._sessions.begin() as session:
            entity = session.get(Policy, _uuid(policy.id)) if policy.id else None
            if entity is None:
                entity = Policy(id=_uuid(policy.id) or uuid4(), project_id=UUID(policy.project_id))
                session.add(entity)
            entity.name = policy.name
            entity.description = policy.description
            entity.active = policy.enabled
            entity.priority = policy.priority
            entity.action = policy.action
            entity.conditions = policy.conditions
            entity.fail_closed = policy.fail_closed
            session.flush()
            session.refresh(entity)
            result = _policy(entity)
        return result

    async def delete_policy(self, policy_id: str) -> None:
        with self._sessions.begin() as session:
            entity = session.get(Policy, _uuid(policy_id))
            if entity:
                session.delete(entity)

    async def record_evaluation(self, decision: dict, approval: ApprovalRecord | None) -> str:
        identifier = _uuid(decision.get("id")) or uuid4()
        with self._sessions.begin() as session:
            values = {key: value for key, value in decision.items() if key != "id"}
            session.add(PolicyDecision(id=identifier, **values))
            if approval:
                approval_id = _uuid(approval.id) or uuid4()
                entity = Approval(
                    id=approval_id,
                    project_id=UUID(approval.project_id),
                    run_id=approval.run_id,
                    policy_id=_uuid(approval.policy_id),
                    state=approval.state,
                    action_summary=approval.action_summary,
                    context=approval.context,
                    reviewer_reference=approval.reviewer_reference,
                    workflow_name=approval.workflow_name,
                    agent_name=approval.agent_name,
                    tool_name=approval.tool_name,
                    operation=approval.operation,
                    confidence=approval.confidence,
                    proposed_inputs=approval.proposed_inputs,
                    match_reason=approval.match_reason,
                    resolved_at=None,
                    integration_reference=None,
                )
                session.add(entity)
                session.add(_audit(approval_id, "created", None, {"state": "pending"}))
        return str(identifier)

    async def list_approvals(self, project_id: str, state: str | None) -> list[ApprovalRecord]:
        with self._sessions() as session:
            statement = select(Approval).where(Approval.project_id == UUID(project_id))
            if state:
                statement = statement.where(Approval.state == ApprovalState(state))
            entities = session.scalars(statement.order_by(Approval.created_at.desc())).all()
            return [_approval(entity) for entity in entities]

    async def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        with self._sessions() as session:
            entity = session.get(Approval, _uuid(approval_id))
            return _approval(entity) if entity else None

    async def resolve_approval(
        self, approval_id: str, state: str, reviewer: str | None,
        integration_reference: str | None,
    ) -> tuple[ApprovalRecord, bool]:
        desired = ApprovalState(state)
        with self._sessions.begin() as session:
            entity = session.scalar(
                select(Approval).where(Approval.id == _uuid(approval_id)).with_for_update()
            )
            if entity is None:
                raise KeyError(approval_id)
            if entity.state == desired:
                return _approval(entity), True
            if entity.state != ApprovalState.PENDING:
                raise ApprovalConflictError("Approval has already been resolved differently")
            entity.state = desired
            entity.reviewer_reference = reviewer
            entity.resolved_at = datetime.now(UTC)
            entity.integration_reference = integration_reference
            session.add(_audit(entity.id, state, reviewer, {}))
            session.flush()
            session.refresh(entity)
            result = _approval(entity)
        return result, False

    async def attach_integration_reference(
        self, approval_id: str, reference: str
    ) -> ApprovalRecord:
        with self._sessions.begin() as session:
            entity = session.get(Approval, _uuid(approval_id))
            if entity is None:
                raise KeyError(approval_id)
            entity.integration_reference = reference
            session.flush()
            session.refresh(entity)
            result = _approval(entity)
        return result


def _policy(entity: Policy) -> PolicyRecord:
    return PolicyRecord(
        id=str(entity.id), project_id=str(entity.project_id), name=entity.name,
        description=entity.description, enabled=entity.active, priority=entity.priority,
        action=entity.action, conditions=entity.conditions, fail_closed=entity.fail_closed,
        created_at=entity.created_at.isoformat(), updated_at=entity.updated_at.isoformat(),
    )


def _approval(entity: Approval) -> ApprovalRecord:
    return ApprovalRecord(
        id=str(entity.id), project_id=str(entity.project_id), run_id=entity.run_id,
        policy_id=str(entity.policy_id) if entity.policy_id else None, state=entity.state,
        action_summary=entity.action_summary, context=entity.context,
        workflow_name=entity.workflow_name, agent_name=entity.agent_name,
        tool_name=entity.tool_name, operation=entity.operation, confidence=entity.confidence,
        proposed_inputs=entity.proposed_inputs, match_reason=entity.match_reason,
        reviewer_reference=entity.reviewer_reference,
        resolved_at=entity.resolved_at.isoformat() if entity.resolved_at else None,
        integration_reference=entity.integration_reference,
        created_at=entity.created_at.isoformat(), updated_at=entity.updated_at.isoformat(),
    )


def _audit(
    approval_id: UUID, event_type: str, actor: str | None, details: dict
) -> ApprovalAuditEvent:
    return ApprovalAuditEvent(
        approval_id=approval_id, event_type=event_type, actor_reference=actor,
        details=details, created_at=datetime.now(UTC),
    )


def _uuid(value: str | None) -> UUID | None:
    try:
        return UUID(value) if value else None
    except (TypeError, ValueError):
        return None
