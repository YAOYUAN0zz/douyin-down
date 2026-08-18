"""FastAPI 应用工厂：只做装配（依赖、路由、异常处理、静态资源）。

分层：server.api（路由）→ server.jobs / server.works / server.auth_flow /
server.deps（服务）→ storage（存储）。

fastapi/uvicorn 是**可选**依赖。若未安装，导入本模块会 ImportError。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import ConfigLoader
from server.api import api_router
from server.auth_flow import BrowserAuthFlow
from server.deps import ServerDeps, execute_download
from server.jobs import DownloadJob, JobManager, JobProgressReporter
from server.schemas import CODE_VALIDATION, ApiError, fail
from utils.logger import setup_logger

logger = setup_logger("REST")

# 前端构建产物目录（frontend/dist），由 Vite 构建输出
_WEBUI_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

_PLACEHOLDER_HTML = """<!doctype html>
<meta charset="utf-8">
<title>Douyin Downloader</title>
<body style="font-family: system-ui; padding: 48px; line-height: 1.8">
<h1>Douyin Downloader API 已就绪</h1>
<p>未找到 Web UI 构建产物（frontend/dist）。请先构建前端：</p>
<pre>cd frontend &amp;&amp; pnpm install &amp;&amp; pnpm build</pre>
<p>或使用 <code>./start-dev.sh</code> 启动开发模式。API 文档见 <a href="/docs">/docs</a>。</p>
</body>"""


def build_app(config: ConfigLoader) -> FastAPI:
    deps = ServerDeps(config)

    async def executor(job: DownloadJob) -> Dict[str, int]:
        return await execute_download(
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
        version="2.0",
        description="REST API for dispatching Douyin download jobs.",
        lifespan=lifespan,
    )
    app.state.job_manager = manager
    app.state.deps = deps
    app.state.auth_flow = auth_flow

    # ---------------- 统一响应模型的异常处理 ----------------

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=fail(exc.code, exc.message))

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        # 框架内部抛出的 HTTPException（404/405 等）也收敛到统一响应模型
        return JSONResponse(
            status_code=exc.status_code,
            content=fail(exc.status_code * 100, str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content=fail(CODE_VALIDATION, str(exc)))

    # ---------------- 路由与静态资源 ----------------

    app.include_router(api_router)

    if _WEBUI_DIST.is_dir():
        # Vue Router 使用 hash 模式，无需 SPA fallback；html=True 服务 index.html
        app.mount("/", StaticFiles(directory=str(_WEBUI_DIST), html=True), name="webui")
    else:

        @app.get("/", include_in_schema=False)
        async def webui_placeholder() -> HTMLResponse:
            return HTMLResponse(_PLACEHOLDER_HTML)

    return app


async def run_server(config: ConfigLoader, *, host: str, port: int) -> None:
    import uvicorn

    app = build_app(config)
    uv_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(uv_config)
    await server.serve()
