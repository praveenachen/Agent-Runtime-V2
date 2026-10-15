import pytest
from pydantic import ValidationError

from agent_runtime.config import Settings


def test_defaults_are_local_development_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.api_prefix == "/api/v1"
    assert settings.databricks_enabled is False


def test_databricks_requires_connection_metadata_when_enabled() -> None:
    with pytest.raises(ValidationError, match="Databricks is enabled"):
        Settings(databricks_enabled=True, _env_file=None)


def test_databricks_accepts_complete_connection_metadata() -> None:
    settings = Settings(
        databricks_enabled=True,
        databricks_host="https://workspace.example",
        databricks_http_path="/sql/1.0/warehouses/example",
        databricks_catalog="agent_runtime",
        databricks_schema="telemetry",
        _env_file=None,
    )

    assert settings.databricks_catalog == "agent_runtime"


def test_production_rejects_local_telemetry_storage() -> None:
    with pytest.raises(ValidationError, match="Local telemetry storage is not allowed"):
        Settings(app_env="production", _env_file=None)


def test_databricks_backend_requires_databricks_to_be_enabled() -> None:
    with pytest.raises(ValidationError, match="requires Databricks to be enabled"):
        Settings(telemetry_backend="databricks", _env_file=None)

