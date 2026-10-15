import gzip
from io import BytesIO

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

from agent_runtime.telemetry.otlp import InvalidOtlpPayload

router = APIRouter(prefix="/telemetry/otlp", tags=["telemetry"])

PROTOBUF_MEDIA_TYPE = "application/x-protobuf"


@router.post("/v1/traces", response_class=Response)
async def export_traces(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != PROTOBUF_MEDIA_TYPE:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="OTLP trace ingestion requires application/x-protobuf",
        )

    max_bytes = request.app.state.settings.telemetry_max_request_bytes
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Payload too large",
        )
    body = await request.body()
    if len(body) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Payload too large",
        )
    payload = _decoded_body(body, request.headers.get("content-encoding", ""), max_bytes)

    try:
        result = await request.app.state.telemetry_ingestion.ingest_bronze(payload)
    except (InvalidOtlpPayload, DecodeError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bronze telemetry persistence unavailable",
        ) from error

    background_tasks.add_task(request.app.state.telemetry_ingestion.persist_silver, result.records)
    response = ExportTraceServiceResponse()
    return Response(content=response.SerializeToString(), media_type=PROTOBUF_MEDIA_TYPE)


def _decoded_body(body: bytes, content_encoding: str, max_bytes: int) -> bytes:
    encoding = content_encoding.strip().lower()
    if encoding in {"", "identity"}:
        return body
    if encoding != "gzip":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content encoding: {encoding}",
        )
    try:
        with gzip.GzipFile(fileobj=BytesIO(body)) as compressed:
            payload = compressed.read(max_bytes + 1)
    except (gzip.BadGzipFile, EOFError) as error:
        raise HTTPException(status_code=400, detail="Invalid gzip request body") from error
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Decompressed payload too large",
        )
    return payload

