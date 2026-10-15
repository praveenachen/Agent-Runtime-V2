from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/runs", tags=["analysis"])


@router.get("/{run_id}/diagnosis")
async def get_run_diagnosis(run_id: str, request: Request) -> dict[str, Any]:
    return (await _diagnosis(run_id, request)).to_dict()


@router.get("/{run_id}/anomalies")
async def get_run_anomalies(run_id: str, request: Request) -> dict[str, Any]:
    diagnosis = await _diagnosis(run_id, request)
    return {
        "items": [item for item in diagnosis.to_dict()["evidence"]["items"]],
        "total": len(diagnosis.evidence.items),
    }


@router.get("/{run_id}/evidence")
async def get_run_evidence(run_id: str, request: Request) -> dict[str, Any]:
    return (await _diagnosis(run_id, request)).evidence.to_dict()


async def _diagnosis(run_id: str, request: Request):
    diagnosis = await request.app.state.analysis_service.diagnose(run_id)
    if diagnosis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return diagnosis
