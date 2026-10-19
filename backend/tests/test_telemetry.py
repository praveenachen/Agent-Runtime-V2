import asyncio
import gzip
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, ArrayValue, KeyValue, KeyValueList
from opentelemetry.proto.trace.v1.trace_pb2 import Status

from agent_runtime.config import Settings
from agent_runtime.main import create_app
from agent_runtime.telemetry.normalization import SemanticNormalizer
from agent_runtime.telemetry.records import BronzeSpanRecord
from agent_runtime.telemetry.storage.local import LocalJsonlTelemetryStore
from agent_runtime.telemetry.storage.memory import InMemoryTelemetryStore

TRACE_ID = bytes.fromhex("00112233445566778899aabbccddeeff")
EVENT_TYPES = ["RUN", "AGENT_STEP", "LLM_CALL", "TOOL_CALL", "HANDOFF", "DECISION", "ERROR"]


def test_otlp_ingestion_redacts_normalizes_and_preserves_relationships() -> None:
    store = InMemoryTelemetryStore()
    app = create_app(Settings(app_env="test", _env_file=None), telemetry_store=store)
    request = _trace_request()

    response = asyncio.run(_post_protobuf(app, request.SerializeToString()))

    assert response.status_code == 200
    ExportTraceServiceResponse.FromString(response.content)
    assert len(store.bronze) == len(EVENT_TYPES)
    assert {event.event_type for event in store.silver.values()} == set(EVENT_TYPES)

    tool = next(record for record in store.bronze.values() if record.span["name"] == "tool")
    assert tool.span["attributes"]["authorization"] == "[REDACTED]"
    assert tool.span["attributes"]["metadata"]["client_secret"] == "[REDACTED]"
    assert tool.span["attributes"]["note"] == "credential [REDACTED]"
    assert tool.resource["attributes"]["api_key"] == "[REDACTED]"

    agent_step = next(event for event in store.silver.values() if event.event_type == "AGENT_STEP")
    assert agent_step.parent_span_id == "0000000000000001"
    assert agent_step.workflow_name == "support-agent"

    tool_event = next(event for event in store.silver.values() if event.event_type == "TOOL_CALL")
    assert tool_event.semantic_attributes == {
        "tool_name": "customer_search",
        "side_effect": False,
        "replayable": True,
    }
    assert any(event.is_out_of_order for event in store.silver.values())


def test_repeated_collector_delivery_is_idempotent() -> None:
    store = InMemoryTelemetryStore()
    app = create_app(Settings(app_env="test", _env_file=None), telemetry_store=store)
    payload = _trace_request().SerializeToString()

    first = asyncio.run(_post_protobuf(app, payload))
    second = asyncio.run(_post_protobuf(app, payload))

    assert first.status_code == second.status_code == 200
    assert len(store.bronze) == len(EVENT_TYPES)
    assert len(store.silver) == len(EVENT_TYPES)


def test_collector_gzip_delivery_is_supported() -> None:
    store = InMemoryTelemetryStore()
    app = create_app(Settings(app_env="test", _env_file=None), telemetry_store=store)
    payload = gzip.compress(_trace_request().SerializeToString())

    response = asyncio.run(_post_protobuf(app, payload, content_encoding="gzip"))

    assert response.status_code == 200
    assert len(store.bronze) == len(EVENT_TYPES)


def test_invalid_and_unsupported_payloads_are_rejected() -> None:
    store = InMemoryTelemetryStore()
    app = create_app(Settings(app_env="test", _env_file=None), telemetry_store=store)

    invalid = asyncio.run(_post_protobuf(app, b"not-protobuf"))
    wrong_media_type = asyncio.run(_post(app, b"{}", "application/json"))

    assert invalid.status_code == 400
    assert wrong_media_type.status_code == 415
    assert not store.bronze


def test_local_jsonl_store_deduplicates_across_instances(tmp_path: Path) -> None:
    record = BronzeSpanRecord(
        record_id="trace:span",
        trace_id="trace",
        span_id="span",
        parent_span_id=None,
        received_at=datetime.now(UTC).isoformat(),
        source_format="test",
        resource={},
        instrumentation_scope={},
        span={},
    )

    first_store = LocalJsonlTelemetryStore(tmp_path)
    first = asyncio.run(first_store.append_bronze([record]))
    second_store = LocalJsonlTelemetryStore(tmp_path)
    second = asyncio.run(second_store.append_bronze([record]))

    assert first.accepted_ids == ("trace:span",)
    assert second.duplicate_ids == ("trace:span",)
    assert len((tmp_path / "bronze-spans.jsonl").read_text().splitlines()) == 1


def test_normalizer_records_late_arrival() -> None:
    received_at = datetime.now(UTC)
    started_at = received_at - timedelta(minutes=10)
    record = BronzeSpanRecord(
        record_id="trace:late",
        trace_id="trace",
        span_id="late",
        parent_span_id=None,
        received_at=received_at.isoformat(),
        source_format="test",
        resource={"attributes": {}},
        instrumentation_scope={},
        span={
            "start_time_unix_nano": int(started_at.timestamp() * 1_000_000_000),
            "end_time_unix_nano": int(started_at.timestamp() * 1_000_000_000),
            "status": {"code": "OK"},
            "attributes": {"agent.runtime.event_type": "RUN"},
        },
    )

    event = SemanticNormalizer(late_after_seconds=300).normalize(record)

    assert event is not None
    assert event.is_late is True
    assert event.observed_lag_ms >= 600_000


def test_normalizer_canonicalizes_integer_versions() -> None:
    _assert_normalized_versions(7)


def test_normalizer_preserves_string_versions_canonically() -> None:
    _assert_normalized_versions("7")


def _assert_normalized_versions(value: int | str) -> None:
    now = datetime.now(UTC)
    record = BronzeSpanRecord(
        record_id="trace:versions",
        trace_id="trace",
        span_id="versions",
        parent_span_id=None,
        received_at=now.isoformat(),
        source_format="test",
        resource={"attributes": {}},
        instrumentation_scope={},
        span={
            "start_time_unix_nano": int(now.timestamp() * 1_000_000_000),
            "end_time_unix_nano": int(now.timestamp() * 1_000_000_000),
            "status": {"code": "OK"},
            "attributes": {
                "agent.runtime.event_type": "TOOL_CALL",
                "agent.runtime.workflow.version": value,
                "agent.runtime.prompt.version": value,
                "agent.runtime.model.version": value,
                "agent.runtime.config.version": value,
                "agent.runtime.tool.version": value,
            },
        },
    )

    event = SemanticNormalizer().normalize(record)

    assert event is not None
    assert event.workflow_version == "7"
    assert event.prompt_version == "7"
    assert event.model == "7"
    assert event.attributes["agent.runtime.config.version"] == "7"
    assert event.attributes["agent.runtime.tool.version"] == "7"


async def _post_protobuf(app, payload: bytes, *, content_encoding: str | None = None):
    return await _post(app, payload, "application/x-protobuf", content_encoding=content_encoding)


async def _post(
    app,
    payload: bytes,
    content_type: str,
    *,
    content_encoding: str | None = None,
):
    headers = {"content-type": content_type}
    if content_encoding:
        headers["content-encoding"] = content_encoding
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/api/v1/telemetry/otlp/v1/traces",
            content=payload,
            headers=headers,
        )


def _trace_request() -> ExportTraceServiceRequest:
    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    resource_spans.schema_url = "https://opentelemetry.io/schemas/1.40.0"
    resource_spans.resource.attributes.extend(
        [
            _attribute("service.name", "synthetic-agent"),
            _attribute("workflow.name", "support-agent"),
            _attribute("deployment.environment.name", "test"),
            _attribute("api_key", "top-secret"),
        ]
    )
    scope_spans = resource_spans.scope_spans.add()
    scope_spans.scope.name = "agent-runtime-tests"
    now_nanos = int(datetime.now(UTC).timestamp() * 1_000_000_000)

    for index, event_type in enumerate(EVENT_TYPES, start=1):
        span = scope_spans.spans.add()
        span.trace_id = TRACE_ID
        span.span_id = index.to_bytes(8, "big")
        if index > 1:
            span.parent_span_id = (index - 1).to_bytes(8, "big")
        span.name = event_type.lower()
        # The final span deliberately arrives behind the watermark.
        offset = 1 if event_type == "ERROR" else index
        span.start_time_unix_nano = now_nanos + offset * 1_000_000
        span.end_time_unix_nano = span.start_time_unix_nano + 2_000_000
        span.status.code = (
            Status.STATUS_CODE_ERROR if event_type == "ERROR" else Status.STATUS_CODE_OK
        )
        span.attributes.append(_attribute("agent.runtime.event_type", event_type))
        span.attributes.append(_attribute("agent.name", "triage"))
        if event_type == "TOOL_CALL":
            span.name = "tool"
            span.attributes.extend(
                [
                    _attribute("tool.name", "customer_search"),
                    _attribute("side_effect", False),
                    _attribute("replayable", True),
                    _attribute("authorization", "Bearer abcdefghijklmnop"),
                    _attribute("metadata", {"client_secret": "nested-secret", "safe": "ok"}),
                    _attribute("note", "credential sk-abcdefghijklmno"),
                ]
            )
        elif event_type == "HANDOFF":
            span.attributes.extend(
                [_attribute("from_agent", "triage"), _attribute("to_agent", "billing")]
            )
        elif event_type == "DECISION":
            span.attributes.extend(
                [_attribute("decision", "escalate"), _attribute("confidence", 0.82)]
            )
        elif event_type == "ERROR":
            span.attributes.append(_attribute("error.type", "ToolTimeout"))
    return request


def _attribute(key: str, value: Any) -> KeyValue:
    return KeyValue(key=key, value=_any_value(value))


def _any_value(value: Any) -> AnyValue:
    if isinstance(value, bool):
        return AnyValue(bool_value=value)
    if isinstance(value, int):
        return AnyValue(int_value=value)
    if isinstance(value, float):
        return AnyValue(double_value=value)
    if isinstance(value, dict):
        return AnyValue(
            kvlist_value=KeyValueList(
                values=[_attribute(str(key), item) for key, item in value.items()]
            )
        )
    if isinstance(value, list):
        return AnyValue(array_value=ArrayValue(values=[_any_value(item) for item in value]))
    return AnyValue(string_value=str(value))
