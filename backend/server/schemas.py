"""API 请求模型、统一响应包装与业务错误码。

统一响应模型（全部端点共用，禁混用）：

    {"code": <int>, "message": <str>, "data": <Any>}

- 成功：code=0，message="ok"，业务负载在 data
- 失败：code 为下方集中定义的业务码；HTTP 状态码保持传输层语义一致
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from server.works import DEFAULT_PAGE_COUNT

# ---------------- 业务码表（集中定义，前后端共用；禁散落魔法数字） ----------------
# 规则：业务码 = 对应 HTTP 状态 * 100 + 两位序号
CODE_OK = 0
CODE_INVALID_PARAM = 40000  # 通用参数错误（缺 url 等）
CODE_INVALID_QUALITY = 40001  # 画质参数不在白名单
CODE_BATCH_LIMIT = 40002  # 批量提交超上限
CODE_LOGIN_REQUIRED = 40100  # 登录态失效/未登录
CODE_NOT_FOUND = 40400  # 资源不存在（job 等）
CODE_CONFLICT = 40900  # 状态冲突（auth 会话已存在/不存在）
CODE_VALIDATION = 42200  # 请求体校验失败（FastAPI RequestValidationError）
CODE_INTERNAL = 50000  # 未分类服务端错误
CODE_UPSTREAM_ERROR = 50200  # 抖音上游接口异常
CODE_DB_DISABLED = 50300  # 数据库未启用（config.database=false），历史类端点不可用
CODE_BROWSER_UNAVAILABLE = 50301  # 缺 Playwright 包或浏览器内核，无法自动获取下载参数


class ApiError(Exception):
    """业务异常：路由/服务层抛出，由全局 exception handler 转统一响应。"""

    def __init__(self, http_status: int, code: int, message: str):
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.message = message


def ok(data: Any = None) -> Dict[str, Any]:
    """成功响应包装。"""
    return {"code": CODE_OK, "message": "ok", "data": data}


def fail(code: int, message: str) -> Dict[str, Any]:
    """失败响应体（由 exception handler 调用）。"""
    return {"code": code, "message": message, "data": None}


# ---------------- 请求模型 ----------------


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


# ---------------- 共享常量与校验 ----------------

# 单次批量提交的上限，防止误勾选提交过量任务压垮队列
MAX_BATCH_URLS = 100

# 与 core.downloader_base 的 video_quality 语义一致：
# original = highest + 原画探测；<N>p 对应 _QUALITY_TARGET_WIDTH 支持的档位。
ALLOWED_VIDEO_QUALITIES = frozenset(
    {"original", "highest", "lowest", "1440p", "1080p", "720p", "540p", "480p", "360p"}
)


def normalize_quality(video_quality: Optional[str]) -> Optional[str]:
    """校验并规整画质参数；空/None 表示跟随全局配置。"""
    if video_quality is None:
        return None
    quality = video_quality.strip().lower()
    if not quality:
        return None
    if quality not in ALLOWED_VIDEO_QUALITIES:
        raise ApiError(
            400,
            CODE_INVALID_QUALITY,
            f"不支持的画质 {video_quality}，可选：{', '.join(sorted(ALLOWED_VIDEO_QUALITIES))}",
        )
    return quality
