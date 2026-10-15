from agent_runtime.config import Settings
from agent_runtime.telemetry.ports import TelemetryAnalyticsStore
from agent_runtime.telemetry.storage.local import LocalJsonlTelemetryStore


def create_telemetry_store(settings: Settings) -> TelemetryAnalyticsStore:
    if settings.telemetry_backend == "local":
        return LocalJsonlTelemetryStore(settings.telemetry_local_path)
    raise RuntimeError(
        "Databricks telemetry requires a DatabricksMergeWriter to be injected into "
        "DatabricksTelemetryStore by the production composition root"
    )

