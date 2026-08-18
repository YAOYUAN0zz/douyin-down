"""跨请求复用的重量级依赖与下载执行体（Service 层）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from auth import CookieManager
from config import ConfigLoader
from control import QueueManager, RateLimiter, RetryHandler
from core import DouyinAPIClient, DownloaderFactory, URLParser
from storage import FileManager
from utils.validators import is_short_url, normalize_short_url


class OverrideConfig:
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


class ServerDeps:
    """跨请求复用的重量级依赖。

    REST 服务在进程生命周期内只需要一份 FileManager / RateLimiter / RetryHandler /
    QueueManager / CookieManager；每个请求重新构造既浪费又会触发文件系统 mkdir。
    DouyinAPIClient 由于持有 aiohttp.ClientSession，依旧按请求创建，避免跨请求泄漏
    连接状态或触发 "Session is closed" 错误。
    """

    def __init__(self, config: ConfigLoader):
        self.config = config
        # cookie 文件相对 config 文件目录解析，保证工作目录无关
        if config.config_path:
            cookie_file = str(Path(config.config_path).resolve().parent / ".cookies.json")
        else:
            cookie_file = ".cookies.json"
        self.cookie_manager = CookieManager(cookie_file=cookie_file)
        # 磁盘 cookie 文件优先：它是「活的」会话存储（Web UI 自动获取 / CLI
        # 重登都写它）。若启动时反过来用 config 内嵌 cookies 覆盖它，上一次
        # 登录抓到的新鲜会话会被 config.yml 里的陈旧值清掉。config 内嵌
        # cookies 只在首次运行（cookie 文件还不存在/为空）时作为种子导入。
        disk_cookies = self.cookie_manager.get_cookies()
        if not disk_cookies:
            initial_cookies = config.get_cookies()
            if initial_cookies:
                self.cookie_manager.set_cookies(initial_cookies)
        self.file_manager = FileManager(config.get("path"))
        self.rate_limiter = RateLimiter(max_per_second=float(config.get("rate_limit", 2) or 2))
        self.retry_handler = RetryHandler(max_retries=int(config.get("retry_times", 3) or 3))
        self.queue_manager = QueueManager(max_workers=int(config.get("thread", 5) or 5))


async def execute_download(
    url: str,
    deps: ServerDeps,
    options: Optional[Dict[str, Any]] = None,
    *,
    progress_reporter: Optional[Any] = None,
    job_id: Optional[str] = None,
) -> Dict[str, int]:
    """简化版 download_url：只负责执行并返回成功/失败计数。

    有意不复用 cli.main.download_url —— 后者绑定了 progress_display 的 rich 状态。
    API client 仍按请求创建（aiohttp session 不跨请求复用）；其余重量级依赖从
    ServerDeps 共享。
    """
    # 画质等 per-job 覆盖只作用于本次任务的配置视图
    config: Any = deps.config
    if options and options.get("video_quality"):
        config = OverrideConfig(deps.config, {"video_quality": options["video_quality"]})

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
