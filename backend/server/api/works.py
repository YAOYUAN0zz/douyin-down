"""作品列表预览端点（按需下载）。"""

from typing import Any, Dict

from fastapi import APIRouter, Request

from core import LoginRequiredError
from server.schemas import (
    CODE_INVALID_PARAM,
    CODE_LOGIN_REQUIRED,
    ApiError,
    WorksListRequest,
    ok,
)
from server.works import WorksListError, list_works

router = APIRouter(tags=["works"])


@router.post("/works/list")
async def works_list(req: WorksListRequest, request: Request) -> Dict[str, Any]:
    if not req.url or not req.url.strip():
        raise ApiError(400, CODE_INVALID_PARAM, "url is required")
    deps = request.app.state.deps
    try:
        page = await list_works(
            req.url.strip(),
            cookies=deps.cookie_manager.get_cookies(),
            proxy=deps.config.get("proxy"),
            cursor=req.cursor,
            count=req.count,
        )
    except WorksListError as exc:
        # 业务码 = 上游 HTTP 状态 * 100（WorksListError 自带状态码）
        raise ApiError(exc.status_code, exc.status_code * 100, str(exc))
    except LoginRequiredError as exc:
        raise ApiError(
            401,
            CODE_LOGIN_REQUIRED,
            f"登录态失效，请重新获取下载参数（{exc}）",
        )
    return ok(page)
