from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_runtime import __version__
from agent_runtime.api.router import api_router
from agent_runtime.config import Settings, get_settings
from agent_runtime.runs.service import RunService
from agent_runtime.telemetry.factory import create_telemetry_store
from agent_runtime.telemetry.ports import TelemetryAnalyticsStore
from agent_runtime.telemetry.service import TelemetryIngestionService


def create_app(
    settings: Settings | None = None,
    telemetry_store: TelemetryAnalyticsStore | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="Agent Runtime API",
        summary="Debug and govern production AI agent behavior.",
        version=__version__,
    )
    application.state.settings = resolved_settings
    application.state.telemetry_store = telemetry_store or create_telemetry_store(resolved_settings)
    application.state.run_service = RunService(application.state.telemetry_store)
    application.state.telemetry_ingestion = TelemetryIngestionService(
        application.state.telemetry_store,
        late_after_seconds=resolved_settings.telemetry_late_after_seconds,
        run_service=application.state.run_service,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=resolved_settings.api_prefix)
    return application


app = create_app()
