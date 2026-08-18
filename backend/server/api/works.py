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
    await _mark_downloaded(page, request.app.state.database)
    return ok(page)


async def _mark_downloaded(page: Dict[str, Any], database: Any) -> None:
    """给每个作品打 `downloaded` 标记（历史库去重结果）。

    数据库关闭时全部标 False，前端据此不显示角标；一次批量查询，不逐条往返。
    """
    items = page.get("items") or []
    if database is None:
        for item in items:
            item["downloaded"] = False
        return
    downloaded = set(await database.filter_downloaded([item.get("aweme_id") for item in items]))
    for item in items:
        item["downloaded"] = item.get("aweme_id") in downloaded
