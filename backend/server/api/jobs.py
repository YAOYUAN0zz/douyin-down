"""任务查询与操作端点：列表（筛选/分页）、详情、取消/重试/删除/清空、SSE 实时推送。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from server.jobs import DownloadJob, JobStatus
from server.schemas import CODE_CONFLICT, CODE_INVALID_PARAM, CODE_NOT_FOUND, ApiError, ok

router = APIRouter(tags=["jobs"])

# status 查询参数取值：单一状态、active（pending+running）、all
_STATUS_FILTERS = frozenset(
    {"all", "active", "pending", "running", "success", "partial", "failed", "cancelled"}
)

# SSE 推送节奏：有活动任务时高频（跟进度条），空闲时低频（当心跳）
_SSE_ACTIVE_INTERVAL = 1.0
_SSE_IDLE_INTERVAL = 10.0


def _filter_jobs(jobs: List[DownloadJob], status: str) -> List[DownloadJob]:
    if status == "all":
        return jobs
    if status == "active":
        return [j for j in jobs if j.status in (JobStatus.PENDING, JobStatus.RUNNING)]
    return [j for j in jobs if j.status == status]


async def _snapshot(request: Request, status: str = "all") -> List[Dict[str, Any]]:
    jobs = await request.app.state.job_manager.list_jobs()
    jobs = _filter_jobs(jobs, status)
    # 服务端统一按创建时间倒序
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return [j.to_dict() for j in jobs]


@router.get("/jobs")
async def list_jobs(
    request: Request,
    status: str = "all",
    page: int = 1,
    page_size: int = 0,
) -> Dict[str, Any]:
    if status not in _STATUS_FILTERS:
        raise ApiError(
            400, CODE_INVALID_PARAM, f"status 只支持：{', '.join(sorted(_STATUS_FILTERS))}"
        )
    items = await _snapshot(request, status)
    total = len(items)
    if page_size > 0:
        page = max(1, page)
        start = (page - 1) * page_size
        items = items[start : start + page_size]
    return ok({"jobs": items, "total": total, "page": page, "page_size": page_size})


@router.get("/jobs/events")
async def jobs_events(request: Request, limit: int = 0) -> StreamingResponse:
    """SSE：持续推送任务快照。有活动任务时每秒推送，空闲时降频为心跳。

    limit>0 时推送 N 次后正常结束（供测试与 curl 调试使用）。
    """

    async def stream() -> AsyncIterator[str]:
        sent = 0
        while True:
            if await request.is_disconnected():
                return
            items = await _snapshot(request)
            active = any(j["status"] in ("pending", "running") for j in items)
            payload = json.dumps({"jobs": items}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            sent += 1
            if limit > 0 and sent >= limit:
                return
            # 分段 sleep：断开后最多 0.5s 内感知并退出，避免挂住测试与关停
            interval = _SSE_ACTIVE_INTERVAL if active else _SSE_IDLE_INTERVAL
            slept = 0.0
            while slept < interval:
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.5)
                slept += 0.5

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> Dict[str, Any]:
    job = await request.app.state.job_manager.get(job_id)
    if job is None:
        raise ApiError(404, CODE_NOT_FOUND, "job not found")
    return ok(job.to_dict())


def _job_or_404(job: Optional[DownloadJob]) -> DownloadJob:
    if job is None:
        raise ApiError(404, CODE_NOT_FOUND, "job not found")
    return job


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request) -> Dict[str, Any]:
    try:
        job = await request.app.state.job_manager.cancel(job_id)
    except ValueError:
        raise ApiError(409, CODE_CONFLICT, "任务已结束，无法取消")
    return ok(_job_or_404(job).to_dict())


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, request: Request) -> Dict[str, Any]:
    try:
        new_job = await request.app.state.job_manager.retry(job_id)
    except ValueError:
        raise ApiError(409, CODE_CONFLICT, "任务尚未结束，无法重试")
    return ok(_job_or_404(new_job).to_dict())


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, request: Request) -> Dict[str, Any]:
    try:
        job = await request.app.state.job_manager.delete(job_id)
    except ValueError:
        raise ApiError(409, CODE_CONFLICT, "任务进行中，请先取消再删除")
    return ok({"deleted": _job_or_404(job).job_id})


@router.post("/jobs/clear")
async def clear_jobs(request: Request) -> Dict[str, Any]:
    count = await request.app.state.job_manager.clear_finished()
    return ok({"deleted": count})
