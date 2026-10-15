import base64
from datetime import UTC, datetime
from typing import Any

from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from agent_runtime.telemetry.records import BronzeSpanRecord
from agent_runtime.telemetry.redaction import AttributeRedactor


class InvalidOtlpPayload(ValueError):
    pass


def decode_otlp_traces(
    payload: bytes,
    redactor: AttributeRedactor,
    *,
    received_at: datetime | None = None,
) -> list[BronzeSpanRecord]:
    request = ExportTraceServiceRequest()
    try:
        request.ParseFromString(payload)
    except DecodeError as error:
        raise InvalidOtlpPayload("Request body is not a valid OTLP trace protobuf") from error

    received = (received_at or datetime.now(UTC)).isoformat()
    records: list[BronzeSpanRecord] = []
    for resource_spans in request.resource_spans:
        resource = {
            "schema_url": resource_spans.schema_url or None,
            "attributes": _attributes(resource_spans.resource.attributes),
            "dropped_attributes_count": resource_spans.resource.dropped_attributes_count,
        }
        for scope_spans in resource_spans.scope_spans:
            scope = {
                "schema_url": scope_spans.schema_url or None,
                "name": scope_spans.scope.name or None,
                "version": scope_spans.scope.version or None,
                "attributes": _attributes(scope_spans.scope.attributes),
                "dropped_attributes_count": scope_spans.scope.dropped_attributes_count,
            }
            for span in scope_spans.spans:
                trace_id = span.trace_id.hex()
                span_id = span.span_id.hex()
                if len(span.trace_id) != 16 or len(span.span_id) != 8:
                    raise InvalidOtlpPayload(
                        "Every span requires a 16-byte trace ID and 8-byte span ID"
                    )
                parent_span_id = span.parent_span_id.hex() or None
                raw_span = {
                    "name": span.name,
                    "trace_state": span.trace_state or None,
                    "kind": int(span.kind),
                    "start_time_unix_nano": span.start_time_unix_nano,
                    "end_time_unix_nano": span.end_time_unix_nano,
                    "attributes": _attributes(span.attributes),
                    "dropped_attributes_count": span.dropped_attributes_count,
                    "events": [
                        {
                            "name": event.name,
                            "time_unix_nano": event.time_unix_nano,
                            "attributes": _attributes(event.attributes),
                            "dropped_attributes_count": event.dropped_attributes_count,
                        }
                        for event in span.events
                    ],
                    "dropped_events_count": span.dropped_events_count,
                    "links": [
                        {
                            "trace_id": link.trace_id.hex(),
                            "span_id": link.span_id.hex(),
                            "trace_state": link.trace_state or None,
                            "attributes": _attributes(link.attributes),
                            "dropped_attributes_count": link.dropped_attributes_count,
                            "flags": link.flags,
                        }
                        for link in span.links
                    ],
                    "dropped_links_count": span.dropped_links_count,
                    "status": {
                        "code": _status_name(span.status.code),
                        "message": span.status.message or None,
                    },
                    "flags": span.flags,
                }
                records.append(
                    BronzeSpanRecord(
                        record_id=f"{trace_id}:{span_id}",
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                        received_at=received,
                        source_format="otlp_http_protobuf",
                        resource=redactor.redact(resource),
                        instrumentation_scope=redactor.redact(scope),
                        span=redactor.redact(raw_span),
                    )
                )
    return records


def _attributes(attributes: Any) -> dict[str, Any]:
    return {attribute.key: _any_value(attribute.value) for attribute in attributes}


def _any_value(value: Any) -> Any:
    field = value.WhichOneof("value")
    if field is None:
        return None
    if field == "array_value":
        return [_any_value(item) for item in value.array_value.values]
    if field == "kvlist_value":
        return _attributes(value.kvlist_value.values)
    if field == "bytes_value":
        return base64.b64encode(value.bytes_value).decode("ascii")
    return getattr(value, field)


def _status_name(code: int) -> str:
    return {0: "UNSET", 1: "OK", 2: "ERROR"}.get(code, "UNSET")

