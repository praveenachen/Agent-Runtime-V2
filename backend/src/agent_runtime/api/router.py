from fastapi import APIRouter

from agent_runtime.api.routes.health import router as health_router
from agent_runtime.api.routes.runs import router as runs_router
from agent_runtime.api.routes.telemetry import router as telemetry_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(runs_router)
api_router.include_router(telemetry_router)
