from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from agent_runtime import __version__

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["agent-runtime-api"]
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="agent-runtime-api",
        version=__version__,
        environment=request.app.state.settings.app_env,
    )

