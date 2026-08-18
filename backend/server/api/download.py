"""下载任务提交端点：单链接与批量。"""

from typing import Any, Dict

from fastapi import APIRouter, Request

from server.schemas import (
    CODE_BATCH_LIMIT,
    CODE_INVALID_PARAM,
    MAX_BATCH_URLS,
    ApiError,
    BatchDownloadRequest,
    DownloadRequest,
    normalize_quality,
    ok,
)

router = APIRouter(tags=["download"])


@router.post("/download")
async def create_job(req: DownloadRequest, request: Request) -> Dict[str, Any]:
    if not req.url:
        raise ApiError(400, CODE_INVALID_PARAM, "url is required")
    quality = normalize_quality(req.video_quality)
    options = {"video_quality": quality} if quality else None
    job = await request.app.state.job_manager.submit(req.url, options=options)
    return ok({"job_id": job.job_id, "status": job.status, "url": job.url})


@router.post("/download/batch")
async def create_batch_jobs(req: BatchDownloadRequest, request: Request) -> Dict[str, Any]:
    urls = [u.strip() for u in req.urls if u and u.strip()]
    if not urls:
        raise ApiError(400, CODE_INVALID_PARAM, "urls is required")
    if len(urls) > MAX_BATCH_URLS:
        raise ApiError(400, CODE_BATCH_LIMIT, f"一次最多提交 {MAX_BATCH_URLS} 个链接")
    quality = normalize_quality(req.video_quality)
    options = {"video_quality": quality} if quality else None
    manager = request.app.state.job_manager
    jobs = [await manager.submit(u, options=options) for u in urls]
    return ok({"jobs": [{"job_id": j.job_id, "status": j.status, "url": j.url} for j in jobs]})
