from fastapi import FastAPI

from agent_runtime import __version__
from agent_runtime.api.router import api_router
from agent_runtime.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="Agent Runtime API",
        summary="Debug and govern production AI agent behavior.",
        version=__version__,
    )
    application.state.settings = resolved_settings
    application.include_router(api_router, prefix=resolved_settings.api_prefix)
    return application


app = create_app()

