from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_runtime import __version__
from agent_runtime.analysis.explainers import DiagnosisExplainer
from agent_runtime.analysis.service import AnalysisService
from agent_runtime.api.router import api_router
from agent_runtime.config import Settings, get_settings
from agent_runtime.control.ports import (
    ControlRepository,
    LocalPermissiveAuthorizer,
    NoopRuntimeControlAdapter,
    ProjectAuthorizer,
    RuntimeControlAdapter,
)
from agent_runtime.control.repository import SqlAlchemyControlRepository
from agent_runtime.control.service import ControlService
from agent_runtime.db.session import create_database_engine, create_session_factory
from agent_runtime.replay.ports import (
    FrameworkReplayAdapter,
    GenericReplayAdapter,
    ReplayRequestRepository,
)
from agent_runtime.replay.repository import SqlAlchemyReplayRequestRepository
from agent_runtime.replay.service import ReplayService
from agent_runtime.runs.service import RunService
from agent_runtime.telemetry.factory import create_telemetry_store
from agent_runtime.telemetry.ports import TelemetryAnalyticsStore
from agent_runtime.telemetry.service import TelemetryIngestionService


def create_app(
    settings: Settings | None = None,
    telemetry_store: TelemetryAnalyticsStore | None = None,
    diagnosis_explainer: DiagnosisExplainer | None = None,
    replay_repository: ReplayRequestRepository | None = None,
    replay_adapter: FrameworkReplayAdapter | None = None,
    control_repository: ControlRepository | None = None,
    project_authorizer: ProjectAuthorizer | None = None,
    runtime_control_adapter: RuntimeControlAdapter | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="Agent Runtime API",
        summary="Debug and govern production AI agent behavior.",
        version=__version__,
    )
    application.state.settings = resolved_settings
    application.state.telemetry_store = telemetry_store or create_telemetry_store(resolved_settings)
    application.state.analysis_service = AnalysisService(
        application.state.telemetry_store,
        explainer=diagnosis_explainer,
    )
    application.state.run_service = RunService(
        application.state.telemetry_store,
        baseline_projector=application.state.analysis_service,
    )
    sessions = None
    if replay_repository is None or control_repository is None:
        engine = create_database_engine(resolved_settings)
        sessions = create_session_factory(engine)
    if replay_repository is None:
        replay_repository = SqlAlchemyReplayRequestRepository(sessions)
    application.state.replay_service = ReplayService(
        application.state.run_service,
        replay_repository,
        replay_adapter or GenericReplayAdapter(),
    )
    if control_repository is None:
        control_repository = SqlAlchemyControlRepository(sessions)
    application.state.control_service = ControlService(
        control_repository,
        project_authorizer or LocalPermissiveAuthorizer(),
        runtime_control_adapter or NoopRuntimeControlAdapter(),
        service_fail_closed=resolved_settings.policy_service_fail_closed,
        approval_ttl_seconds=resolved_settings.approval_ttl_seconds,
    )
    application.state.telemetry_ingestion = TelemetryIngestionService(
        application.state.telemetry_store,
        late_after_seconds=resolved_settings.telemetry_late_after_seconds,
        run_service=application.state.run_service,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=resolved_settings.api_prefix)
    return application


app = create_app()
