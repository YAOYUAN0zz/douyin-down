"""下载参数（cookie）状态与浏览器自动获取流程端点。"""

from typing import Any, Dict

from fastapi import APIRouter, Request

from server.schemas import CODE_CONFLICT, ApiError, ok
from tools.cookie_fetcher import REQUIRED_KEYS

router = APIRouter(tags=["auth"])


@router.get("/auth/status")
async def auth_status(request: Request) -> Dict[str, Any]:
    cookies = request.app.state.deps.cookie_manager.get_cookies()
    required = sorted(REQUIRED_KEYS)
    missing = [key for key in required if not (cookies.get(key) or "").strip()]
    return ok(
        {
            "cookie_count": len(cookies),
            "required": required,
            "missing": missing,
            "ready": not missing,
            "has_session": bool((cookies.get("sessionid") or "").strip()),
        }
    )


@router.post("/auth/fetch")
async def auth_fetch_start(request: Request) -> Dict[str, Any]:
    auth_flow = request.app.state.auth_flow
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
