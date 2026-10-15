import asyncio

from httpx import ASGITransport, AsyncClient

from agent_runtime.config import Settings
from agent_runtime.main import create_app


def test_health_reports_service_state() -> None:
    app = create_app(Settings(app_env="test", _env_file=None))

    async def request_health():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/api/v1/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "agent-runtime-api",
        "version": "0.1.0",
        "environment": "test",
    }

