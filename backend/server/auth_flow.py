"""Web UI 驱动的浏览器登录 + 下载参数自动获取流程。

复用 tools.cookie_fetcher 的抓取逻辑（msToken 提取 / cookie 过滤），
但把「终端按 Enter 确认」替换为：
- 自动检测：轮询浏览器 cookie，出现 sessionid 即认为登录完成，自动抓取；
- 手动确认：Web UI 的「我已完成登录」按钮触发 confirm()。

CLI-only 模块：desktop 项目有自己的 GUI 登录面，不共享本文件。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from auth import CookieManager
from server.preflight import INSTALL_PACKAGE_HINT
from tools.cookie_fetcher import (
    DEFAULT_URL,
    REQUIRED_KEYS,
    extract_ms_token_from_text,
    filter_cookies,
    goto_with_fallback,
    try_extract_ms_token,
)
from utils.cookie_utils import parse_cookie_header, sanitize_cookies
from utils.logger import setup_logger

logger = setup_logger("AuthFlow")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AuthFlowStatus:
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

    TERMINAL = frozenset({SUCCESS, FAILED, CANCELLED})


class BrowserAuthFlow:
    """单例式浏览器登录流程：同一时刻最多一个抓取会话。

    登录完成判定（满足其一即抓取）：
    1. 轮询发现 douyin.com 域下出现 ``sessionid`` cookie（自动检测）；
    2. confirm() 被调用（用户在 Web UI 点击「我已完成登录」）。
    """

    # 检测到 sessionid 后再等一小段时间，让携带 msToken 的请求落地
    _GRACE_AFTER_LOGIN_SECONDS = 3.0

    def __init__(
        self,
        cookie_manager: CookieManager,
        *,
        url: str = DEFAULT_URL,
        browser: str = "chromium",
        headless: bool = False,
        poll_interval: float = 2.0,
        timeout_seconds: float = 600.0,
    ):
        self.cookie_manager = cookie_manager
        self.url = url
        self.browser = browser
        self.headless = headless
        self.poll_interval = poll_interval
        self.timeout_seconds = timeout_seconds

        self.status = AuthFlowStatus.IDLE
        self.message: Optional[str] = None
        self.missing: List[str] = []
        self.captured_count = 0
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None

        self._task: Optional[asyncio.Task] = None
        self._confirm_event = asyncio.Event()
        self._cancel_event = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> bool:
        """启动抓取会话；已有会话在跑时返回 False。"""
        async with self._lock:
            if self.is_running:
                return False
            self.status = AuthFlowStatus.RUNNING
            self.message = "正在启动浏览器，请在弹出的窗口中完成抖音登录。"
            self.missing = []
            self.captured_count = 0
            self.started_at = _now_iso()
            self.finished_at = None
            self._confirm_event = asyncio.Event()
            self._cancel_event = asyncio.Event()
            self._task = asyncio.create_task(self._run())
            return True

    async def confirm(self) -> bool:
        """用户声明已完成登录；无会话在跑时返回 False。"""
        if not self.is_running:
            return False
        self._confirm_event.set()
        return True

    async def cancel(self) -> bool:
        if not self.is_running:
            return False
        self._cancel_event.set()
        return True

    def snapshot(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "missing": list(self.missing),
            "captured_count": self.captured_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    async def shutdown(self) -> None:
        if self.is_running:
            self._cancel_event.set()
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=15.0)
            except Exception:  # noqa: BLE001 — 关停尽力而为
                pass

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        try:
            await self._run_browser_session()
        except _FlowCancelled:
            self.status = AuthFlowStatus.CANCELLED
            self.message = "已取消获取。"
        except Exception as exc:  # noqa: BLE001 — 失败原因要透给 UI
            logger.error("Auth fetch flow failed: %s", exc)
            self.status = AuthFlowStatus.FAILED
            self.message = f"获取失败：{type(exc).__name__}: {exc}"
        finally:
            self.finished_at = _now_iso()
            if self.status == AuthFlowStatus.RUNNING:  # pragma: no cover - 防御
                self.status = AuthFlowStatus.FAILED
                self.message = self.message or "获取流程异常结束。"

    async def _run_browser_session(self) -> None:
        # 正常路径下 /auth/fetch 已在入口做过完整前置校验，这里是 CLI 直调或
        # 环境中途被破坏时的兜底，文案与前置校验统一（见 server.preflight）
        try:
            from playwright.async_api import async_playwright  # type: ignore
        except ImportError:
            raise RuntimeError(INSTALL_PACKAGE_HINT)

        observed_cookie_headers: List[str] = []
        observed_mstokens: List[str] = []

        async with async_playwright() as p:
            browser_factory = getattr(p, self.browser)
            browser = await browser_factory.launch(headless=self.headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                page.on(
                    "request",
                    lambda request: self._observe_request(
                        request, observed_cookie_headers, observed_mstokens
                    ),
                )

                self.message = "浏览器已打开，请在窗口中完成抖音登录（登录后会自动抓取参数）。"
                nav_task = asyncio.create_task(goto_with_fallback(page, self.url))
                try:
                    await self._wait_for_login(context)
                finally:
                    if not nav_task.done():
                        nav_task.cancel()
                    try:
                        await nav_task
                    except (Exception, asyncio.CancelledError):  # noqa: BLE001
                        pass

                self.message = "登录完成，正在抓取下载参数……"
                cookies = await self._capture_cookies(
                    context, page, observed_cookie_headers, observed_mstokens
                )
            finally:
                try:
                    await browser.close()
                except Exception:  # noqa: BLE001 — 浏览器可能已被用户关闭
                    pass

        self._finish_with_cookies(cookies)

    def _observe_request(
        self,
        request: Any,
        observed_cookie_headers: List[str],
        observed_mstokens: List[str],
    ) -> None:
        try:
            headers = request.headers or {}
            cookie_header = headers.get("cookie")
            if cookie_header:
                observed_cookie_headers.append(cookie_header)
            token = extract_ms_token_from_text(request.url or "")
            if token:
                observed_mstokens.append(token)
        except Exception:  # noqa: BLE001 — 观察失败不影响主流程
            return

    async def _wait_for_login(self, context: Any) -> None:
        """轮询直到自动检测到登录 / 用户确认 / 取消 / 超时。"""
        deadline = asyncio.get_event_loop().time() + self.timeout_seconds
        while True:
            if self._cancel_event.is_set():
                raise _FlowCancelled()
            if self._confirm_event.is_set():
                return
            if asyncio.get_event_loop().time() > deadline:
                raise RuntimeError(
                    f"等待登录超时（{int(self.timeout_seconds)}s），请重新发起获取。"
                )
            try:
                cookie_list = await context.cookies("https://www.douyin.com")
            except Exception as exc:  # noqa: BLE001
                # 浏览器/上下文被用户关闭
                raise RuntimeError(f"浏览器已关闭，登录未完成（{exc}）。")
            by_name = {c.get("name"): c.get("value") for c in cookie_list or []}
            if (by_name.get("sessionid") or "").strip():
                # 已登录：给携带 msToken 的请求留一点时间
                await self._sleep_or_cancel(self._GRACE_AFTER_LOGIN_SECONDS)
                return
            await self._sleep_or_cancel(self.poll_interval)

    async def _sleep_or_cancel(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._cancel_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return
        raise _FlowCancelled()

    async def _capture_cookies(
        self,
        context: Any,
        page: Any,
        observed_cookie_headers: List[str],
        observed_mstokens: List[str],
    ) -> Dict[str, str]:
        storage = await context.storage_state()
        cookies = {
            cookie["name"]: cookie["value"]
            for cookie in storage.get("cookies", [])
            if str(cookie.get("domain", "")).endswith("douyin.com")
        }
        cookies = sanitize_cookies(cookies)

        ms_token = await try_extract_ms_token(
            page, cookies, observed_cookie_headers, observed_mstokens
        )
        if ms_token and not cookies.get("msToken"):
            cookies["msToken"] = ms_token

        # 兜底：storage_state 偶尔缺 HttpOnly cookie 时，从请求头里补齐
        for header in reversed(observed_cookie_headers):
            for key, value in parse_cookie_header(header).items():
                cookies.setdefault(key, value)

        return sanitize_cookies(filter_cookies(cookies))

    def _finish_with_cookies(self, cookies: Dict[str, str]) -> None:
        if not cookies:
            raise RuntimeError("未抓取到任何 cookie，请确认已在浏览器中登录抖音。")

        self.cookie_manager.set_cookies(cookies)
        self.captured_count = len(cookies)
        self.missing = sorted(REQUIRED_KEYS - cookies.keys())
        self.status = AuthFlowStatus.SUCCESS
        if self.missing:
            self.message = (
                f"已保存 {self.captured_count} 个 cookie，但仍缺少：{', '.join(self.missing)}。"
                "部分下载模式可能受限，可重新获取。"
            )
        else:
            self.message = f"已保存 {self.captured_count} 个 cookie，下载参数齐全。"


class _FlowCancelled(Exception):
    """内部信号：用户取消了抓取会话。"""
