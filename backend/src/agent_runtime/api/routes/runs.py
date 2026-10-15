from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
async def list_runs(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    workflow: str | None = None,
    environment: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    records, total = await request.app.state.run_service.list_runs(
        status=status_filter,
        workflow=workflow,
        environment=environment,
        limit=limit,
        offset=offset,
    )
    return {"items": [record.summary_dict() for record in records], "total": total}


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    return (await _record(run_id, request)).to_dict()


@router.get("/{run_id}/graph")
async def get_run_graph(run_id: str, request: Request) -> dict[str, Any]:
    return (await _record(run_id, request)).to_dict()["graph"]


@router.get("/{run_id}/metrics")
async def get_run_metrics(run_id: str, request: Request) -> dict[str, Any]:
    return (await _record(run_id, request)).to_dict()["metrics"]


@router.get("/{run_id}/events")
async def get_run_events(run_id: str, request: Request) -> dict[str, Any]:
    record = await _record(run_id, request)
    return {"items": list(record.events), "total": len(record.events)}


async def _record(run_id: str, request: Request):
    record = await request.app.state.run_service.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return record
