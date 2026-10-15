from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from agent_runtime.control.engine import PolicyEvaluationError
from agent_runtime.control.models import RuntimeContext
from agent_runtime.control.repository import ApprovalConflictError
from agent_runtime.domain.models import ApprovalState, PolicyAction

router = APIRouter(tags=["control"])


class PolicyPayload(BaseModel):
    project_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    enabled: bool = True
    priority: int = Field(default=0, ge=0, le=10_000)
    action: PolicyAction
    conditions: dict[str, Any] = Field(default_factory=dict)
    fail_closed: bool = True


class EnabledPayload(BaseModel):
    enabled: bool


class EvaluationPayload(BaseModel):
    project_id: UUID
    run_id: str = Field(min_length=1, max_length=64)
    workflow_name: str | None = None
    agent_name: str | None = None
    tool_name: str | None = None
    action_name: str | None = None
    operation: str | None = None
    side_effect: bool | None = None
    replayable: bool | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    current_cost: float | None = Field(default=None, ge=0)
    tool_call_count: int | None = Field(default=None, ge=0)
    retry_count: int | None = Field(default=None, ge=0)
    repeated_transition_count: int | None = Field(default=None, ge=0)
    proposed_inputs: dict[str, Any] = Field(default_factory=dict)
    control_reference: str | None = None


class ResolutionPayload(BaseModel):
    reviewer_reference: str | None = Field(default=None, max_length=200)


def _principal(value: str | None) -> str:
    return value or "local-developer"


@router.get("/policies")
async def list_policies(
    request: Request,
    project_id: UUID,
    x_agent_runtime_principal: str | None = Header(default=None),
) -> dict[str, Any]:
    items = await request.app.state.control_service.list_policies(
        str(project_id), _principal(x_agent_runtime_principal)
    )
    return {"items": [item.to_dict() for item in items], "total": len(items)}


@router.post("/policies", status_code=status.HTTP_201_CREATED)
async def create_policy(
    body: PolicyPayload,
    request: Request,
    x_agent_runtime_principal: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _save_policy(None, body, request, x_agent_runtime_principal)


@router.get("/policies/{policy_id}")
async def get_policy(
    policy_id: str,
    request: Request,
    x_agent_runtime_principal: str | None = Header(default=None),
) -> dict[str, Any]:
    policy = await request.app.state.control_service.get_policy(
        policy_id, _principal(x_agent_runtime_principal)
    )
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy.to_dict()


@router.put("/policies/{policy_id}")
async def update_policy(
    policy_id: str,
    body: PolicyPayload,
    request: Request,
    x_agent_runtime_principal: str | None = Header(default=None),
) -> dict[str, Any]:
    if await request.app.state.control_service.get_policy(
        policy_id, _principal(x_agent_runtime_principal)
    ) is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return await _save_policy(policy_id, body, request, x_agent_runtime_principal)


@router.patch("/policies/{policy_id}/enabled")
async def set_policy_enabled(
    policy_id: str,
    body: EnabledPayload,
    request: Request,
    x_agent_runtime_principal: str | None = Header(default=None),
) -> dict[str, Any]:
    policy = await request.app.state.control_service.set_enabled(
        policy_id, body.enabled, _principal(x_agent_runtime_principal)
    )
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy.to_dict()


@router.post("/policies/evaluate")
async def evaluate_policy(
    body: EvaluationPayload,
    request: Request,
    x_agent_runtime_principal: str | None = Header(default=None),
) -> dict[str, Any]:
    context = RuntimeContext(**body.model_dump(mode="json"))
    result = await request.app.state.control_service.evaluate(
        context, _principal(x_agent_runtime_principal)
    )
    return result.to_dict()


@router.get("/approvals/pending/count")
async def pending_count(
    request: Request,
    project_id: UUID,
    x_agent_runtime_principal: str | None = Header(default=None),
) -> dict[str, int]:
    items = await request.app.state.control_service.list_approvals(
        str(project_id), ApprovalState.PENDING.value, _principal(x_agent_runtime_principal)
    )
    return {"count": len(items)}


@router.get("/approvals")
async def list_approvals(
    request: Request,
    project_id: UUID,
    state: ApprovalState | None = None,
    x_agent_runtime_principal: str | None = Header(default=None),
) -> dict[str, Any]:
    items = await request.app.state.control_service.list_approvals(
        str(project_id), state.value if state else None,
        _principal(x_agent_runtime_principal),
    )
    return {"items": [item.to_dict() for item in items], "total": len(items)}


@router.get("/approvals/{approval_id}")
async def get_approval(
    approval_id: str,
    request: Request,
    x_agent_runtime_principal: str | None = Header(default=None),
) -> dict[str, Any]:
    approval = await request.app.state.control_service.get_approval(
        approval_id, _principal(x_agent_runtime_principal)
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval.to_dict()


@router.post("/approvals/{approval_id}/approve")
async def approve(
    approval_id: str, body: ResolutionPayload, request: Request,
    x_agent_runtime_principal: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _resolve(
        approval_id, ApprovalState.APPROVED, body, request, x_agent_runtime_principal
    )


@router.post("/approvals/{approval_id}/reject")
async def reject(
    approval_id: str, body: ResolutionPayload, request: Request,
    x_agent_runtime_principal: str | None = Header(default=None),
) -> dict[str, Any]:
    return await _resolve(
        approval_id, ApprovalState.REJECTED, body, request, x_agent_runtime_principal
    )


async def _save_policy(
    policy_id: str | None, body: PolicyPayload, request: Request, principal: str | None
) -> dict[str, Any]:
    payload = body.model_dump()
    payload["project_id"] = str(body.project_id)
    try:
        policy = await request.app.state.control_service.save_policy(
            policy_id=policy_id, principal=_principal(principal),
            **payload,
        )
    except PolicyEvaluationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return policy.to_dict()


async def _resolve(
    approval_id: str, state: ApprovalState, body: ResolutionPayload,
    request: Request, principal: str | None,
) -> dict[str, Any]:
    try:
        result = await request.app.state.control_service.resolve(
            approval_id, state, body.reviewer_reference, _principal(principal)
        )
    except ApprovalConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return result.to_dict()
