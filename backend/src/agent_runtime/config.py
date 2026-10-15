from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENT_RUNTIME_",
        extra="ignore",
    )

    app_env: Literal["development", "test", "staging", "production"] = "development"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+psycopg://agent_runtime:agent_runtime@localhost:5432/agent_runtime"
    )

    telemetry_backend: Literal["local", "databricks"] = "local"
    telemetry_local_path: Path = Path(".data/telemetry")
    telemetry_max_request_bytes: int = 10 * 1024 * 1024
    telemetry_late_after_seconds: int = 300

    databricks_enabled: bool = False
    databricks_host: str | None = None
    databricks_http_path: str | None = None
    databricks_catalog: str | None = None
    databricks_schema: str | None = None

    @model_validator(mode="after")
    def validate_databricks_settings(self) -> "Settings":
        if self.app_env == "production" and self.telemetry_backend == "local":
            raise ValueError("Local telemetry storage is not allowed in production")
        if self.telemetry_backend == "databricks" and not self.databricks_enabled:
            raise ValueError("The Databricks telemetry backend requires Databricks to be enabled")
        if self.databricks_enabled:
            required = {
                "databricks_host": self.databricks_host,
                "databricks_http_path": self.databricks_http_path,
                "databricks_catalog": self.databricks_catalog,
                "databricks_schema": self.databricks_schema,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(
                    "Databricks is enabled but settings are missing: " + ", ".join(missing)
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

