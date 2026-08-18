"""历史记录端点：已下载作品的分页查询、统计与元数据详情。

数据源是 `storage.Database` 的 `aweme` 表（下载器在成功落盘后写入），
本层只做参数校验与响应包装，不做业务加工。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Request

from server.schemas import (
    CODE_DB_DISABLED,
    CODE_INVALID_PARAM,
    CODE_NOT_FOUND,
    ApiError,
    ok,
)
from storage import Database

router = APIRouter(tags=["history"])

# 分页与统计的边界值：与作品列表一致，避免一次拉全库
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20
MAX_TOP_AUTHORS = 50
DEFAULT_TOP_AUTHORS = 10

_SORT_FIELDS = frozenset({"download_time", "create_time"})


def _database(request: Request) -> Database:
    database = request.app.state.database
    if database is None:
        raise ApiError(503, CODE_DB_DISABLED, "数据库未启用，历史记录不可用（config.database）")
    return database


@router.get("/history")
async def list_history(
    request: Request,
    query: Optional[str] = None,
    author: Optional[str] = None,
    aweme_type: Optional[str] = None,
    author_sec_uid: Optional[str] = None,
    job_id: Optional[str] = None,
    sort: str = "download_time",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Dict[str, Any]:
    """已下载作品分页列表。`query` 为标题子串搜索（大小写不敏感）。"""
    if sort not in _SORT_FIELDS:
        raise ApiError(400, CODE_INVALID_PARAM, f"sort 只支持：{', '.join(sorted(_SORT_FIELDS))}")
    if page < 1:
        raise ApiError(400, CODE_INVALID_PARAM, "page 必须 ≥ 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ApiError(400, CODE_INVALID_PARAM, f"page_size 取值范围 1~{MAX_PAGE_SIZE}")

    result = await _database(request).get_aweme_history(
        page=page,
        size=page_size,
        title=(query or "").strip() or None,
        author=(author or "").strip() or None,
        aweme_type=(aweme_type or "").strip() or None,
        author_sec_uid=(author_sec_uid or "").strip() or None,
        job_id=(job_id or "").strip() or None,
        sort=sort,
    )
    return ok(
        {
            "items": result["items"],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["size"],
        }
    )


@router.get("/history/stats")
async def history_stats(request: Request, limit: int = DEFAULT_TOP_AUTHORS) -> Dict[str, Any]:
    """侧栏统计：总下载数 + 近 7/30 天作者 Top N。"""
    if limit < 1 or limit > MAX_TOP_AUTHORS:
        raise ApiError(400, CODE_INVALID_PARAM, f"limit 取值范围 1~{MAX_TOP_AUTHORS}")
    database = _database(request)
    # size=1 只为拿 total：get_aweme_history 的 COUNT 与列表共用同一套过滤规则，
    # 单独再写一个 count 查询会让「什么算已下载」出现第二处定义。
    total = (await database.get_aweme_history(page=1, size=1))["total"]
    return ok(
        {
            "total": total,
            "top_authors_7d": await database.get_top_authors(days=7, limit=limit),
            "top_authors_30d": await database.get_top_authors(days=30, limit=limit),
        }
    )


@router.get("/history/{aweme_id}")
async def history_detail(aweme_id: str, request: Request) -> Dict[str, Any]:
    """单条历史详情，含下载时捕获的完整元数据 JSON。"""
    detail = await _database(request).get_aweme_detail(aweme_id)
    if detail is None:
        raise ApiError(404, CODE_NOT_FOUND, "历史记录不存在")
    return ok(detail)
