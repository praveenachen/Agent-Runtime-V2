import logging
from dataclasses import dataclass

from agent_runtime.runs.service import RunService
from agent_runtime.telemetry.normalization import SemanticNormalizer
from agent_runtime.telemetry.otlp import decode_otlp_traces
from agent_runtime.telemetry.ports import AppendResult, TelemetryAnalyticsStore
from agent_runtime.telemetry.records import BronzeSpanRecord
from agent_runtime.telemetry.redaction import AttributeRedactor

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    records: tuple[BronzeSpanRecord, ...]
    bronze_result: AppendResult


class TelemetryIngestionService:
    def __init__(
        self,
        store: TelemetryAnalyticsStore,
        *,
        late_after_seconds: int = 300,
        run_service: RunService | None = None,
    ) -> None:
        self._store = store
        self._redactor = AttributeRedactor()
        self._normalizer = SemanticNormalizer(late_after_seconds=late_after_seconds)
        self._run_service = run_service

    async def ingest_bronze(self, payload: bytes) -> IngestionResult:
        records = tuple(decode_otlp_traces(payload, self._redactor))
        result = await self._store.append_bronze(records)
        return IngestionResult(records=records, bronze_result=result)

    async def persist_silver(self, records: tuple[BronzeSpanRecord, ...]) -> None:
        try:
            events = tuple(
                event
                for record in records
                if (event := self._normalizer.normalize(record)) is not None
            )
            if events:
                await self._store.append_silver(events)
                if self._run_service is not None:
                    await self._run_service.materialize(
                        sorted({event.trace_id for event in events})
                    )
        except Exception:
            # Bronze is already durable and remains the recovery/reprocessing source.
            logger.exception("Silver normalization or persistence failed")
