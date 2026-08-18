"""FastAPI REST 服务入口。

HTTP 层薄封装：
- 接收 URL，创建 job，返回 job_id
- 实际下载委托给 cli.main.download_url 的简化复用

fastapi/uvicorn 是**可选**依赖。若未安装，导入本模块会 ImportError。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from auth import CookieManager
from config import ConfigLoader
from control import QueueManager, RateLimiter, RetryHandler
from core import DouyinAPIClient, DownloaderFactory, LoginRequiredError, URLParser
from server.auth_flow import BrowserAuthFlow
from server.jobs import DownloadJob, JobManager, JobProgressReporter
from server.works import DEFAULT_PAGE_COUNT, WorksListError, list_works
from storage import FileManager
from tools.cookie_fetcher import REQUIRED_KEYS
from utils.logger import setup_logger
from utils.validators import is_short_url, normalize_short_url

logger = setup_logger("REST")


class DownloadRequest(BaseModel):
    url: str
    video_quality: Optional[str] = None


class BatchDownloadRequest(BaseModel):
    urls: List[str]
    video_quality: Optional[str] = None


class WorksListRequest(BaseModel):
    url: str
    cursor: int = 0
    count: int = DEFAULT_PAGE_COUNT


class JobResponse(BaseModel):
    job_id: str
    status: str
    url: str


# 单次批量提交的上限，防止误勾选提交过量任务压垮队列
MAX_BATCH_URLS = 100

# 与 core.downloader_base 的 video_quality 语义一致：
# original = highest + 原画探测；<N>p 对应 _QUALITY_TARGET_WIDTH 支持的档位。
ALLOWED_VIDEO_QUALITIES = frozenset(
    {"original", "highest", "lowest", "1440p", "1080p", "720p", "540p", "480p", "360p"}
)


def _normalize_quality(video_quality: Optional[str]) -> Optional[str]:
    """校验并规整画质参数；空/None 表示跟随全局配置。"""
    if video_quality is None:
        return None
    quality = video_quality.strip().lower()
    if not quality:
        return None
    if quality not in ALLOWED_VIDEO_QUALITIES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的画质 {video_quality}，可选：{', '.join(sorted(ALLOWED_VIDEO_QUALITIES))}",
        )
    return quality


class _OverrideConfig:
    """轻量配置视图：指定键取覆盖值，其余全部透传给底层 ConfigLoader。

    只用于单个下载任务的画质覆盖，不写回、不影响全局配置。
    """

    def __init__(self, base: ConfigLoader, overrides: Dict[str, Any]):
        self._base = base
        self._overrides = overrides

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        return self._base.get(key, default)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)


class _ServerDeps:
    """跨请求复用的重量级依赖。

    REST 服务在进程生命周期内只需要一份 FileManager / RateLimiter / RetryHandler /
    QueueManager / CookieManager；每个请求重新构造既浪费又会触发文件系统 mkdir。
    DouyinAPIClient 由于持有 aiohttp.ClientSession，依旧按请求创建，避免跨请求泄漏
    连接状态或触发 "Session is closed" 错误。
    """

    def __init__(self, config: ConfigLoader):
        self.config = config
        # Resolve the cookie file path relative to the config file's directory
        # so the sidecar can find it regardless of its working directory (which
        # on macOS is often '/' when launched by Electron).
        if config.config_path:
            cookie_file = str(Path(config.config_path).resolve().parent / ".cookies.json")
        else:
            cookie_file = ".cookies.json"
        self.cookie_manager = CookieManager(cookie_file=cookie_file)
        # Load cookies from the config (env var / YAML cookie key) first, then
        # fall back to whatever is already on disk in the cookie file. This
        # ensures that cookies saved by a previous session are picked up on
        # restart even when the config doesn't embed them inline.
        initial_cookies = config.get_cookies()
        if initial_cookies:
            self.cookie_manager.set_cookies(initial_cookies)
        else:
            # Trigger a load from disk so get_cookies() returns the persisted
            # session without requiring a fresh login on every app restart.
            self.cookie_manager.get_cookies()
        self.file_manager = FileManager(config.get("path"))
        self.rate_limiter = RateLimiter(max_per_second=float(config.get("rate_limit", 2) or 2))
        self.retry_handler = RetryHandler(max_retries=int(config.get("retry_times", 3) or 3))
        self.queue_manager = QueueManager(max_workers=int(config.get("thread", 5) or 5))


async def _execute_download(
    url: str,
    deps: "_ServerDeps",
    options: Optional[Dict[str, Any]] = None,
    *,
    progress_reporter: Optional[Any] = None,
    job_id: Optional[str] = None,
) -> Dict[str, int]:
    """简化版 download_url：只负责执行并返回成功/失败计数。

    有意不复用 cli.main.download_url —— 后者绑定了 progress_display 的 rich 状态。
    API client 仍按请求创建（aiohttp session 不跨请求复用）；其余重量级依赖从
    _ServerDeps 共享。
    """
    # 画质等 per-job 覆盖只作用于本次任务的配置视图
    config = deps.config
    if options and options.get("video_quality"):
        config = _OverrideConfig(deps.config, {"video_quality": options["video_quality"]})

    # proxy 与 cli.main.download_url 对齐:API 请求、短链解析和 CDN 媒体
    # 下载(downloader_base 读 api_client.proxy)统一走配置代理。
    async with DouyinAPIClient(
        deps.cookie_manager.get_cookies(),
        proxy=deps.config.get("proxy"),
    ) as api_client:
        if is_short_url(url):
            resolved = await api_client.resolve_short_url(normalize_short_url(url))
            if not resolved:
                raise RuntimeError(f"Failed to resolve short URL: {url}")
            url = resolved

        parsed = URLParser.parse(url)
        if not parsed:
            raise RuntimeError(f"Unsupported URL: {url}")

        downloader = DownloaderFactory.create(
            parsed["type"],
            config,
            api_client,
            deps.file_manager,
            deps.cookie_manager,
            None,  # database 不在 server 场景里启用，避免单例冲突
            deps.rate_limiter,
            deps.retry_handler,
            deps.queue_manager,
            progress_reporter=progress_reporter,
            job_id=job_id,
        )
        if downloader is None:
            raise RuntimeError(f"No downloader for url_type={parsed['type']}")

        result = await downloader.download(parsed)
        return {
            "total": result.total,
            "success": result.success,
            "failed": result.failed,
            "skipped": result.skipped,
        }


def build_app(config: ConfigLoader) -> FastAPI:
    deps = _ServerDeps(config)

    async def executor(job: DownloadJob) -> Dict[str, int]:
        return await _execute_download(
            job.url,
            deps,
            job.options,
            progress_reporter=JobProgressReporter(job),
            job_id=job.job_id,
        )

    server_cfg = config.get("server") or {}
    if not isinstance(server_cfg, dict):
        server_cfg = {}
    manager = JobManager(
        executor=executor,
        max_concurrency=int(config.get("thread", 2) or 2),
        max_jobs=int(server_cfg.get("max_jobs") or JobManager.DEFAULT_MAX_JOBS),
        job_ttl_seconds=float(
            server_cfg.get("job_ttl_seconds") or JobManager.DEFAULT_JOB_TTL_SECONDS
        ),
    )

    auth_flow_cfg = server_cfg.get("auth_flow") or {}
    if not isinstance(auth_flow_cfg, dict):
        auth_flow_cfg = {}
    auth_flow = BrowserAuthFlow(
        deps.cookie_manager,
        browser=str(auth_flow_cfg.get("browser") or "chromium"),
        headless=bool(auth_flow_cfg.get("headless", False)),
        timeout_seconds=float(auth_flow_cfg.get("timeout_seconds") or 600.0),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await auth_flow.shutdown()
        await manager.shutdown()

    app = FastAPI(
        title="Douyin Downloader API",
        version="1.0",
        description="REST API for dispatching Douyin download jobs.",
        lifespan=lifespan,
    )
    app.state.job_manager = manager
    app.state.deps = deps
    app.state.auth_flow = auth_flow

    webui_index = Path(__file__).resolve().parent / "webui" / "index.html"

    @app.get("/", include_in_schema=False)
    async def webui() -> FileResponse:
        if not webui_index.exists():
            raise HTTPException(status_code=404, detail="web UI not found")
        return FileResponse(webui_index, media_type="text/html")

    @app.get("/api/v1/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/download", response_model=JobResponse)
    async def create_job(req: DownloadRequest) -> JobResponse:
        if not req.url:
            raise HTTPException(status_code=400, detail="url is required")
        quality = _normalize_quality(req.video_quality)
        options = {"video_quality": quality} if quality else None
        job = await manager.submit(req.url, options=options)
        return JobResponse(job_id=job.job_id, status=job.status, url=job.url)

    @app.post("/api/v1/download/batch")
    async def create_batch_jobs(req: BatchDownloadRequest) -> Dict[str, List[Dict[str, Any]]]:
        urls = [u.strip() for u in req.urls if u and u.strip()]
        if not urls:
            raise HTTPException(status_code=400, detail="urls is required")
        if len(urls) > MAX_BATCH_URLS:
            raise HTTPException(status_code=400, detail=f"一次最多提交 {MAX_BATCH_URLS} 个链接")
        quality = _normalize_quality(req.video_quality)
        options = {"video_quality": quality} if quality else None
        jobs = [await manager.submit(u, options=options) for u in urls]
        return {"jobs": [{"job_id": j.job_id, "status": j.status, "url": j.url} for j in jobs]}

    @app.post("/api/v1/works/list")
    async def works_list(req: WorksListRequest) -> Dict[str, Any]:
        if not req.url or not req.url.strip():
            raise HTTPException(status_code=400, detail="url is required")
        try:
            return await list_works(
                req.url.strip(),
                cookies=deps.cookie_manager.get_cookies(),
                proxy=deps.config.get("proxy"),
                cursor=req.cursor,
                count=req.count,
            )
        except WorksListError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc))
        except LoginRequiredError as exc:
            raise HTTPException(
                status_code=401,
                detail=f"登录态失效，请先在「下载参数状态」中重新获取参数（{exc}）",
            )

    @app.get("/api/v1/jobs/{job_id}")
    async def get_job(job_id: str) -> Dict[str, Any]:
        job = await manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job.to_dict()

    @app.get("/api/v1/jobs")
    async def list_jobs() -> Dict[str, List[Dict[str, Any]]]:
        jobs = await manager.list_jobs()
        return {"jobs": [j.to_dict() for j in jobs]}

    @app.get("/api/v1/auth/status")
    async def auth_status() -> Dict[str, Any]:
        cookies = deps.cookie_manager.get_cookies()
        required = sorted(REQUIRED_KEYS)
        missing = [key for key in required if not (cookies.get(key) or "").strip()]
        return {
            "cookie_count": len(cookies),
            "required": required,
            "missing": missing,
            "ready": not missing,
            "has_session": bool((cookies.get("sessionid") or "").strip()),
        }

    @app.post("/api/v1/auth/fetch")
    async def auth_fetch_start() -> Dict[str, Any]:
        started = await auth_flow.start()
        if not started:
            raise HTTPException(status_code=409, detail="已有一个获取会话正在进行")
        return auth_flow.snapshot()

    @app.get("/api/v1/auth/fetch/status")
    async def auth_fetch_status() -> Dict[str, Any]:
        return auth_flow.snapshot()

    @app.post("/api/v1/auth/fetch/confirm")
    async def auth_fetch_confirm() -> Dict[str, Any]:
        confirmed = await auth_flow.confirm()
        if not confirmed:
            raise HTTPException(status_code=409, detail="当前没有正在进行的获取会话")
        return auth_flow.snapshot()

    @app.post("/api/v1/auth/fetch/cancel")
    async def auth_fetch_cancel() -> Dict[str, Any]:
        cancelled = await auth_flow.cancel()
        if not cancelled:
            raise HTTPException(status_code=409, detail="当前没有正在进行的获取会话")
        return auth_flow.snapshot()

    return app


async def run_server(config: ConfigLoader, *, host: str, port: int) -> None:
    import uvicorn

    app = build_app(config)
    uv_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(uv_config)
    await server.serve()
