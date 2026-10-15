from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from agent_runtime.domain.models import ReplayCapability, ReplayMode

router = APIRouter(tags=["replay"])


class CreateReplayRequest(BaseModel):
    source_run_id: str = Field(min_length=1, max_length=64)
    mode: ReplayMode
    capability: ReplayCapability = ReplayCapability.FULL_RERUN
    checkpoint_id: str | None = Field(default=None, max_length=200)
    requested_changes: dict[str, Any] = Field(default_factory=dict)


@router.get("/runs/{run_id}/replay-capabilities")
async def get_replay_capabilities(run_id: str, request: Request) -> dict[str, Any]:
    capabilities = await request.app.state.replay_service.capabilities(run_id)
    if capabilities is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return capabilities.to_dict()


@router.post("/replays", status_code=status.HTTP_201_CREATED)
async def create_replay(body: CreateReplayRequest, request: Request) -> dict[str, Any]:
    record = await request.app.state.replay_service.create_request(
        source_run_id=body.source_run_id,
        mode=body.mode,
        requested_capability=body.capability,
        checkpoint_id=body.checkpoint_id,
        requested_changes=body.requested_changes,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return record.to_dict()


@router.get("/replays/{request_id}")
async def get_replay(request_id: str, request: Request) -> dict[str, Any]:
    record = await request.app.state.replay_service.get_request(request_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replay not found")
    return record.to_dict()


@router.get("/runtime-diff")
async def get_runtime_diff(
    request: Request,
    original_run_id: str = Query(min_length=1),
    comparison_run_id: str = Query(min_length=1),
) -> dict[str, Any]:
    result = await request.app.state.replay_service.compare(original_run_id, comparison_run_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both runs were not found",
        )
    return result.to_dict()
