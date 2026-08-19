"""提交前置校验：环境与凭据不满足时**立刻拒绝**，不让任务半路失败。

设计动机：缺 Playwright、缺浏览器内核、缺下载参数（cookie）这三类问题，
如果放任请求进入异步任务再失败，用户看到的只是某个 job 变成 failed，
真正的原因散落在日志/快照里，难以排错。这里把判定前移到端点入口，
同步返回带修复命令的错误响应。

各检查函数成对提供：
- ``*_problem()`` 返回 ``None`` 或人类可读的原因，供状态类端点如实展示；
- ``ensure_*()`` 在有问题时抛 ApiError，供动作类端点拦截。
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any, List, Optional

from server.schemas import (
    CODE_BROWSER_UNAVAILABLE,
    CODE_LOGIN_REQUIRED,
    ApiError,
)
from tools.cookie_fetcher import REQUIRED_KEYS

# 装包与装内核是两条独立命令，缺哪条就提示哪条，不让用户盲试
INSTALL_PACKAGE_HINT = (
    "未安装 Playwright。请执行：\n"
    "  uv sync --project backend --extra browser --inexact\n"
    "  uv run --project backend python -m playwright install chromium\n"
    "或确认 .env.dev 的 UV_EXTRAS 含 browser 后重新运行启动脚本，依赖会在启动时自动补齐。"
)
INSTALL_BROWSER_HINT = (
    "Playwright 已安装但缺少 {browser} 浏览器内核。请执行：\n"
    "  uv run --project backend python -m playwright install {browser}\n"
    "或确认 .env.dev 的 UV_EXTRAS 含 browser 后重新运行启动脚本，内核会在启动时自动下载。"
)


# ---------------------------------------------------------------- 凭据


def missing_credentials(cookie_manager: Any) -> List[str]:
    """返回缺失的必需 cookie 键（已排序）；空列表表示下载参数齐全。"""
    cookies = cookie_manager.get_cookies() or {}
    return sorted(key for key in REQUIRED_KEYS if not (cookies.get(key) or "").strip())


def ensure_credentials(cookie_manager: Any) -> None:
    """下载类端点入口调用：缺下载参数就别让任务排队。"""
    missing = missing_credentials(cookie_manager)
    if not missing:
        return
    raise ApiError(
        401,
        CODE_LOGIN_REQUIRED,
        f"缺少下载参数：{', '.join(missing)}。请先在「获取参数」中完成抖音登录后再提交下载。",
    )


# ---------------------------------------------------------------- 浏览器环境


def browser_package_problem() -> Optional[str]:
    """只查 Python 包是否装上（零开销），供状态类端点高频轮询使用。"""
    if importlib.util.find_spec("playwright") is None:
        return INSTALL_PACKAGE_HINT
    return None


async def browser_env_problem(browser: str = "chromium") -> Optional[str]:
    """检查浏览器自动获取所需环境；就绪返回 None，否则返回可执行的修复提示。

    分两级：先查 Python 包（零开销），再起一次 driver 读内核路径。后者约
    数百毫秒，只在用户主动发起获取时付出一次，换取「点下去就知道行不行」。
    """
    package_problem = browser_package_problem()
    if package_problem:
        return package_problem

    from playwright.async_api import async_playwright  # type: ignore

    try:
        async with async_playwright() as p:
            executable = getattr(p, browser).executable_path
    except Exception as exc:  # noqa: BLE001 — driver 起不来也是环境问题，原样透出
        return f"Playwright 运行环境不可用：{type(exc).__name__}: {exc}"

    if not executable or not os.path.exists(executable):
        return INSTALL_BROWSER_HINT.format(browser=browser)
    return None


async def ensure_browser_env(browser: str = "chromium") -> None:
    """获取参数端点入口调用：环境没装齐就别进入 running 状态。"""
    problem = await browser_env_problem(browser)
    if problem:
        raise ApiError(503, CODE_BROWSER_UNAVAILABLE, problem)
