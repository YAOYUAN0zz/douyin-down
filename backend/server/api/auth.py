"""下载参数（cookie）状态与浏览器自动获取流程端点。"""

from typing import Any, Dict

from fastapi import APIRouter, Request

from server.preflight import browser_package_problem, ensure_browser_env
from server.schemas import CODE_CONFLICT, ApiError, ok
from tools.cookie_fetcher import REQUIRED_KEYS

router = APIRouter(tags=["auth"])


@router.get("/auth/status")
async def auth_status(request: Request) -> Dict[str, Any]:
    cookies = request.app.state.deps.cookie_manager.get_cookies()
    required = sorted(REQUIRED_KEYS)
    missing = [key for key in required if not (cookies.get(key) or "").strip()]
    # 这里只做轻量包检查：前端会周期性刷新状态，不适合每次都起 Playwright
    # driver；内核缺失由 /auth/fetch 的完整前置校验兜住。
    browser_problem = browser_package_problem()
    return ok(
        {
            "cookie_count": len(cookies),
            "required": required,
            "missing": missing,
            "ready": not missing,
            "has_session": bool((cookies.get("sessionid") or "").strip()),
            "browser_ready": browser_problem is None,
            "browser_hint": browser_problem,
        }
    )


@router.post("/auth/fetch")
async def auth_fetch_start(request: Request) -> Dict[str, Any]:
    auth_flow = request.app.state.auth_flow
    # 环境没装齐就不该进入 running 状态：否则前端只看到一个瞬间失败的会话，
    # 真正的原因要翻快照才知道
    await ensure_browser_env(auth_flow.browser)
    started = await auth_flow.start()
    if not started:
        raise ApiError(409, CODE_CONFLICT, "已有一个获取会话正在进行")
    return ok(auth_flow.snapshot())


@router.get("/auth/fetch/status")
async def auth_fetch_status(request: Request) -> Dict[str, Any]:
    return ok(request.app.state.auth_flow.snapshot())


@router.post("/auth/fetch/confirm")
async def auth_fetch_confirm(request: Request) -> Dict[str, Any]:
    auth_flow = request.app.state.auth_flow
    confirmed = await auth_flow.confirm()
    if not confirmed:
        raise ApiError(409, CODE_CONFLICT, "当前没有正在进行的获取会话")
    return ok(auth_flow.snapshot())


@router.post("/auth/fetch/cancel")
async def auth_fetch_cancel(request: Request) -> Dict[str, Any]:
    auth_flow = request.app.state.auth_flow
    cancelled = await auth_flow.cancel()
    if not cancelled:
        raise ApiError(409, CODE_CONFLICT, "当前没有正在进行的获取会话")
    return ok(auth_flow.snapshot())
