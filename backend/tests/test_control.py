import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from agent_runtime.config import Settings
from agent_runtime.control.models import PolicyRecord, RuntimeContext
from agent_runtime.control.ports import LocalPermissiveAuthorizer, NoopRuntimeControlAdapter
from agent_runtime.control.repository import (
    ApprovalConflictError,
    InMemoryControlRepository,
)
from agent_runtime.control.service import ControlService
from agent_runtime.domain.models import ApprovalState, PolicyAction
from agent_runtime.main import create_app
from agent_runtime.telemetry.storage.memory import InMemoryTelemetryStore

PROJECT = str(uuid4())
OTHER_PROJECT = str(uuid4())


def test_allow_when_no_policy_matches_and_disabled_policy_is_ignored() -> None:
    service, repository = _service()
    repository.policies["disabled"] = _policy(
        "disabled", PolicyAction.BLOCK, {"side_effect": True}, enabled=False
    )

    result = asyncio.run(service.evaluate(_context(side_effect=True), "test"))

    assert result.action == PolicyAction.ALLOW
    assert result.matched_policies == ()


@pytest.mark.parametrize(
    ("action", "conditions", "context"),
    [
        (PolicyAction.BLOCK, {"disallowed_operations": ["delete"]}, {"operation": "delete"}),
        (PolicyAction.PAUSE, {"retry_count_gte": 2}, {"retry_count": 2}),
        (PolicyAction.REQUIRE_APPROVAL, {"side_effect": True}, {"side_effect": True}),
        (PolicyAction.BLOCK, {"confidence_lt": 0.7}, {"confidence": 0.6}),
        (
            PolicyAction.BLOCK,
            {"tool_name": "shell", "operation": "execute"},
            {"tool_name": "shell", "operation": "execute"},
        ),
    ],
)
def test_deterministic_policy_conditions(action, conditions, context) -> None:
    service, repository = _service()
    repository.policies["policy"] = _policy("policy", action, conditions)

    result = asyncio.run(service.evaluate(_context(**context), "test"))

    assert result.action == action
    assert result.matched_policies[0].explanation


def test_conflict_resolution_uses_safety_precedence_before_priority() -> None:
    service, repository = _service()
    repository.policies["allow"] = _policy(
        "allow", PolicyAction.ALLOW, {"side_effect": True}, priority=999
    )
    repository.policies["approval"] = _policy(
        "approval", PolicyAction.REQUIRE_APPROVAL, {"side_effect": True}, priority=20
    )
    repository.policies["block"] = _policy(
        "block", PolicyAction.BLOCK, {"side_effect": True}, priority=1
    )

    result = asyncio.run(service.evaluate(_context(side_effect=True), "test"))

    assert result.action == PolicyAction.BLOCK
    assert [item.action for item in result.matched_policies] == [
        PolicyAction.BLOCK, PolicyAction.REQUIRE_APPROVAL, PolicyAction.ALLOW
    ]


def test_project_isolation() -> None:
    service, repository = _service()
    repository.policies["other"] = replace(
        _policy("other", PolicyAction.BLOCK, {}), project_id=OTHER_PROJECT
    )

    result = asyncio.run(service.evaluate(_context(), "test"))

    assert result.action == PolicyAction.ALLOW


@pytest.mark.parametrize(
    ("fail_closed", "expected"),
    [(False, PolicyAction.ALLOW), (True, PolicyAction.BLOCK)],
)
def test_per_policy_fail_open_and_fail_closed(fail_closed, expected) -> None:
    service, repository = _service()
    repository.policies["broken"] = _policy(
        "broken", PolicyAction.BLOCK, {"confidence_lt": "invalid"},
        fail_closed=fail_closed,
    )

    result = asyncio.run(service.evaluate(_context(confidence=0.2), "test"))

    assert result.action == expected
    assert result.evaluation_failed
    assert result.policy_failures[0].policy_id == "broken"
    assert result.decision_made is (not fail_closed)


def test_service_failure_reports_fallback_without_claiming_decision() -> None:
    service = ControlService(
        FailingRepository(), LocalPermissiveAuthorizer(), NoopRuntimeControlAdapter(),
        service_fail_closed=False,
    )

    result = asyncio.run(service.evaluate(_context(), "test"))

    assert result.action == PolicyAction.ALLOW
    assert not result.decision_made
    assert result.failure_behavior == "fail_open"


def test_approval_creation_redaction_accept_reject_and_idempotency() -> None:
    service, repository = _service()
    repository.policies["approval"] = _policy(
        "approval", PolicyAction.REQUIRE_APPROVAL, {"side_effect": True}
    )
    context = _context(
        side_effect=True,
        proposed_inputs={"recipient": "dev@example.com", "api_key": "secret-value"},
    )
    result = asyncio.run(service.evaluate(context, "test"))
    approval_id = result.approval_request_id

    assert approval_id is not None
    approval = repository.approvals[approval_id]
    assert approval.proposed_inputs["api_key"] == "[REDACTED]"
    accepted = asyncio.run(
        service.resolve(approval_id, ApprovalState.APPROVED, "reviewer", "test")
    )
    repeated = asyncio.run(
        service.resolve(approval_id, ApprovalState.APPROVED, "reviewer", "test")
    )
    assert accepted is not None and accepted.approval.state == ApprovalState.APPROVED
    assert repeated is not None and repeated.idempotent
    with pytest.raises(ApprovalConflictError):
        asyncio.run(service.resolve(approval_id, ApprovalState.REJECTED, "reviewer", "test"))

    second = asyncio.run(service.evaluate(context, "test"))
    rejected = asyncio.run(
        service.resolve(second.approval_request_id, ApprovalState.REJECTED, "reviewer", "test")
    )
    assert rejected is not None and rejected.approval.state == ApprovalState.REJECTED


def test_approved_same_action_retry_is_authorized_idempotently() -> None:
    service, repository = _approval_service()
    context = _context(
        side_effect=True,
        operation="send",
        control_reference="relay-action-1",
        proposed_inputs={"recipient": "dev@example.com", "api_key": "secret-value"},
    )
    initial = asyncio.run(service.evaluate(context, "test"))
    asyncio.run(
        service.resolve(initial.approval_request_id, ApprovalState.APPROVED, "reviewer", "test")
    )

    first_retry = asyncio.run(service.evaluate(context, "test"))
    second_retry = asyncio.run(service.evaluate(context, "test"))

    assert first_retry.action == second_retry.action == PolicyAction.ALLOW
    assert first_retry.authorization_source == "existing_approved_approval"
    assert first_retry.authorizing_approval_id == initial.approval_request_id
    assert second_retry.authorizing_approval_id == initial.approval_request_id
    assert first_retry.approval_request_id is None
    assert len(repository.approvals) == 1
    approval = repository.approvals[initial.approval_request_id]
    assert approval.context_hash
    assert approval.policy_revision
    assert approval.control_reference == "relay-action-1"
    assert approval.expires_at is not None
    assert "secret-value" not in approval.context_hash


def test_changed_control_reference_requires_new_approval() -> None:
    service, repository, context, approval_id = _approved_action()

    result = asyncio.run(
        service.evaluate(replace(context, control_reference="relay-action-2"), "test")
    )

    assert result.action == PolicyAction.REQUIRE_APPROVAL
    assert result.authorization_source == "new_approval"
    assert result.approval_request_id != approval_id
    assert len(repository.approvals) == 2


def test_changed_sanitized_context_hash_requires_new_approval() -> None:
    service, repository, context, approval_id = _approved_action()

    result = asyncio.run(service.evaluate(replace(context, operation="archive"), "test"))

    assert result.action == PolicyAction.REQUIRE_APPROVAL
    assert result.approval_request_id != approval_id
    assert repository.approvals[result.approval_request_id].context_hash != (
        repository.approvals[approval_id].context_hash
    )


def test_policy_revision_change_requires_new_approval() -> None:
    service, repository, context, approval_id = _approved_action()
    current = repository.policies["approval"]
    repository.policies["approval"] = replace(
        current, updated_at="2099-01-01T00:00:00+00:00"
    )

    result = asyncio.run(service.evaluate(context, "test"))

    assert result.action == PolicyAction.REQUIRE_APPROVAL
    assert result.approval_request_id != approval_id
    assert repository.approvals[result.approval_request_id].policy_revision != (
        repository.approvals[approval_id].policy_revision
    )


def test_expired_approval_requires_new_approval() -> None:
    service, repository, context, approval_id = _approved_action()
    repository.approvals[approval_id] = replace(
        repository.approvals[approval_id], expires_at="2000-01-01T00:00:00+00:00"
    )

    result = asyncio.run(service.evaluate(context, "test"))

    assert result.action == PolicyAction.REQUIRE_APPROVAL
    assert result.approval_request_id != approval_id
    assert repository.approvals[approval_id].state == ApprovalState.EXPIRED


def test_rejected_approval_does_not_authorize_retry() -> None:
    service, repository = _approval_service()
    context = _context(side_effect=True, control_reference="relay-action-1")
    initial = asyncio.run(service.evaluate(context, "test"))
    asyncio.run(
        service.resolve(initial.approval_request_id, ApprovalState.REJECTED, "reviewer", "test")
    )

    result = asyncio.run(service.evaluate(context, "test"))

    assert result.action == PolicyAction.REQUIRE_APPROVAL
    assert result.authorization_source == "new_approval"
    assert result.authorizing_approval_id is None
    assert len(repository.approvals) == 2


def test_approved_binding_is_project_isolated() -> None:
    service, repository, context, approval_id = _approved_action()
    repository.approvals[approval_id] = replace(
        repository.approvals[approval_id], project_id=OTHER_PROJECT
    )

    result = asyncio.run(service.evaluate(context, "test"))

    assert result.action == PolicyAction.REQUIRE_APPROVAL
    assert result.authorization_source == "new_approval"
    assert result.approval_request_id != approval_id


def test_control_apis_cover_management_evaluation_and_approval() -> None:
    repository = InMemoryControlRepository()
    app = create_app(
        Settings(app_env="test", _env_file=None),
        telemetry_store=InMemoryTelemetryStore(),
        control_repository=repository,
    )

    async def requests():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post("/api/v1/policies", json={
                "project_id": PROJECT, "name": "Protect writes", "enabled": True,
                "priority": 10, "action": "REQUIRE_APPROVAL",
                "conditions": {"side_effect": True}, "fail_closed": True,
            })
            policy_id = created.json()["id"]
            listing = await client.get("/api/v1/policies", params={"project_id": PROJECT})
            disabled = await client.patch(
                f"/api/v1/policies/{policy_id}/enabled", json={"enabled": False}
            )
            await client.patch(f"/api/v1/policies/{policy_id}/enabled", json={"enabled": True})
            evaluation_payload = {
                "project_id": PROJECT, "run_id": "run-1", "tool_name": "email",
                "operation": "send", "side_effect": True,
                "proposed_inputs": {"password": "do-not-store"},
                "control_reference": "relay-action-1",
            }
            evaluated = await client.post(
                "/api/v1/policies/evaluate", json=evaluation_payload
            )
            approval_id = evaluated.json()["approval_request_id"]
            pending = await client.get(
                "/api/v1/approvals", params={"project_id": PROJECT, "state": "pending"}
            )
            count = await client.get(
                "/api/v1/approvals/pending/count", params={"project_id": PROJECT}
            )
            approved = await client.post(
                f"/api/v1/approvals/{approval_id}/approve",
                json={"reviewer_reference": "local"},
            )
            retry = await client.post(
                "/api/v1/policies/evaluate", json=evaluation_payload
            )
            return created, listing, disabled, evaluated, pending, count, approved, retry

    responses = asyncio.run(requests())
    assert all(item.status_code in {200, 201} for item in responses)
    assert responses[1].json()["total"] == 1
    assert responses[2].json()["enabled"] is False
    assert responses[3].json()["action"] == "REQUIRE_APPROVAL"
    assert responses[3].json()["authorization_source"] == "new_approval"
    assert responses[4].json()["items"][0]["proposed_inputs"]["password"] == "[REDACTED]"
    assert responses[5].json()["count"] == 1
    assert responses[6].json()["state"] == "approved"
    assert responses[7].json()["action"] == "ALLOW"
    assert responses[7].json()["authorization_source"] == "existing_approved_approval"
    assert responses[7].json()["authorizing_approval_id"] == responses[3].json()[
        "approval_request_id"
    ]


def _service():
    repository = InMemoryControlRepository()
    return (
        ControlService(repository, LocalPermissiveAuthorizer(), NoopRuntimeControlAdapter()),
        repository,
    )


def _approval_service():
    service, repository = _service()
    repository.policies["approval"] = _policy(
        "approval", PolicyAction.REQUIRE_APPROVAL, {"side_effect": True}
    )
    return service, repository


def _approved_action():
    service, repository = _approval_service()
    context = _context(
        side_effect=True,
        operation="send",
        control_reference="relay-action-1",
        proposed_inputs={"recipient": "dev@example.com"},
    )
    initial = asyncio.run(service.evaluate(context, "test"))
    asyncio.run(
        service.resolve(initial.approval_request_id, ApprovalState.APPROVED, "reviewer", "test")
    )
    return service, repository, context, initial.approval_request_id


def _policy(
    policy_id, action, conditions, *, enabled=True, priority=0, fail_closed=True
):
    now = datetime.now(UTC).isoformat()
    return PolicyRecord(
        policy_id, PROJECT, policy_id, None, enabled, priority, action, conditions,
        fail_closed, now, now,
    )


def _context(**changes):
    values = {"project_id": PROJECT, "run_id": "run-1"}
    values.update(changes)
    return RuntimeContext(**values)


class FailingRepository(InMemoryControlRepository):
    async def list_policies(self, project_id):
        raise RuntimeError("database unavailable")
