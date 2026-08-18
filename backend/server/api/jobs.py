"""任务查询端点。"""

from typing import Any, Dict

from fastapi import APIRouter, Request

from server.schemas import CODE_NOT_FOUND, ApiError, ok

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> Dict[str, Any]:
    job = await request.app.state.job_manager.get(job_id)
    if job is None:
        raise ApiError(404, CODE_NOT_FOUND, "job not found")
    return ok(job.to_dict())


@router.get("/jobs")
async def list_jobs(request: Request) -> Dict[str, Any]:
    jobs = await request.app.state.job_manager.list_jobs()
    return ok({"jobs": [j.to_dict() for j in jobs]})
