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
            evaluated = await client.post("/api/v1/policies/evaluate", json={
                "project_id": PROJECT, "run_id": "run-1", "tool_name": "email",
                "operation": "send", "side_effect": True,
                "proposed_inputs": {"password": "do-not-store"},
            })
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
            return created, listing, disabled, evaluated, pending, count, approved

    responses = asyncio.run(requests())
    assert all(item.status_code in {200, 201} for item in responses)
    assert responses[1].json()["total"] == 1
    assert responses[2].json()["enabled"] is False
    assert responses[3].json()["action"] == "REQUIRE_APPROVAL"
    assert responses[4].json()["items"][0]["proposed_inputs"]["password"] == "[REDACTED]"
    assert responses[5].json()["count"] == 1
    assert responses[6].json()["state"] == "approved"


def _service():
    repository = InMemoryControlRepository()
    return (
        ControlService(repository, LocalPermissiveAuthorizer(), NoopRuntimeControlAdapter()),
        repository,
    )


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
