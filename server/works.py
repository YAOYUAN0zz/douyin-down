"""作品列表获取与条目规整（CLI-only：Web UI「先看列表、按需下载」用）。

只做只读预览，不落盘、不去重；实际下载仍走 JobManager 的既有下载管线。
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from core import DouyinAPIClient, URLParser
from core.metadata import extract_video_cover_urls
from utils.validators import is_short_url, normalize_short_url

MAX_PAGE_COUNT = 50
DEFAULT_PAGE_COUNT = 20

# 支持列表预览的链接类型；live / live_replay 等流式内容没有"作品列表"概念
_PAGED_TYPES = frozenset({"user", "collection", "music"})
_SINGLE_TYPES = frozenset({"video", "gallery"})


class WorksListError(Exception):
    """列表获取的业务错误，附带建议的 HTTP 状态码。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def extract_qualities(video: Any) -> List[Dict[str, Any]]:
    """从 ``video.bit_rate`` 阶梯提取所有可用画质档，按分辨率/码率降序。

    与 core.downloader_base 的选档逻辑同源（play_addr 宽高定短边），但这里
    只做只读展示，不挑选、不签名。原画（original）不在阶梯里——它是下载期
    通过 ratio=default 探测的档位，由 UI 侧作为固定选项呈现。
    """
    if not isinstance(video, Mapping):
        return []
    entries = video.get("bit_rate")
    if not isinstance(entries, list):
        return []

    qualities: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        play_addr = entry.get("play_addr")
        play_addr = play_addr if isinstance(play_addr, Mapping) else {}

        def _to_int(value: Any) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        width = _to_int(play_addr.get("width") or entry.get("width"))
        height = _to_int(play_addr.get("height") or entry.get("height"))
        short_edge = min(width, height) if width > 0 and height > 0 else max(width, height)
        qualities.append(
            {
                "label": f"{short_edge}p" if short_edge > 0 else "unknown",
                "width": width,
                "height": height,
                "bit_rate": _to_int(entry.get("bit_rate")),
                "size_bytes": _to_int(play_addr.get("data_size")),
                "fps": _to_int(entry.get("FPS")),
                "format": str(entry.get("format") or ""),
                "gear_name": str(entry.get("gear_name") or ""),
            }
        )

    qualities.sort(key=lambda q: (min(q["width"], q["height"]), q["bit_rate"]), reverse=True)
    return qualities


def normalize_aweme(aweme: Any) -> Optional[Dict[str, Any]]:
    """把上游 aweme payload 规整为 UI 需要的最小字段集；无 aweme_id 返回 None。"""
    if not isinstance(aweme, Mapping):
        return None
    aweme_id = str(aweme.get("aweme_id") or "").strip()
    if not aweme_id:
        return None

    images = aweme.get("images")
    is_images = isinstance(images, list) and len(images) > 0
    media_type = "images" if is_images else "video"

    cover = ""
    cover_urls = extract_video_cover_urls(aweme)
    if cover_urls:
        cover = cover_urls[0]
    elif is_images and isinstance(images[0], Mapping):
        url_list = images[0].get("url_list")
        if isinstance(url_list, list) and url_list and isinstance(url_list[0], str):
            cover = url_list[0]

    duration_seconds = 0
    video = aweme.get("video")
    if not is_images and isinstance(video, Mapping):
        try:
            duration_seconds = int(video.get("duration") or 0) // 1000
        except (TypeError, ValueError):
            duration_seconds = 0

    try:
        create_time = int(aweme.get("create_time") or 0)
    except (TypeError, ValueError):
        create_time = 0

    statistics = aweme.get("statistics")
    stats: Dict[str, int] = {}
    if isinstance(statistics, Mapping):
        for key in ("digg_count", "comment_count", "collect_count"):
            try:
                stats[key] = int(statistics.get(key) or 0)
            except (TypeError, ValueError):
                stats[key] = 0

    author = aweme.get("author")
    author_name = ""
    if isinstance(author, Mapping):
        author_name = str(author.get("nickname") or "").strip()

    qualities = [] if is_images else extract_qualities(video)

    path_kind = "note" if is_images else "video"
    return {
        "qualities": qualities,
        "aweme_id": aweme_id,
        "desc": str(aweme.get("desc") or "").strip(),
        "media_type": media_type,
        "image_count": len(images) if is_images else 0,
        "cover": cover,
        "duration_seconds": duration_seconds,
        "create_time": create_time,
        "author": author_name,
        "stats": stats,
        "download_url": f"https://www.douyin.com/{path_kind}/{aweme_id}",
    }


async def list_works(
    url: str,
    *,
    cookies: Dict[str, str],
    proxy: Optional[str] = None,
    cursor: int = 0,
    count: int = DEFAULT_PAGE_COUNT,
) -> Dict[str, Any]:
    """按链接类型拉一页作品列表，返回 {source_type, items, has_more, cursor}。

    - user / collection / music：分页（cursor 透传上游 max_cursor）
    - video / gallery：单作品，直接取详情
    """
    count = max(1, min(int(count or DEFAULT_PAGE_COUNT), MAX_PAGE_COUNT))
    cursor = max(0, int(cursor or 0))

    async with DouyinAPIClient(cookies, proxy=proxy) as api_client:
        if is_short_url(url):
            resolved = await api_client.resolve_short_url(normalize_short_url(url))
            if not resolved:
                raise WorksListError(f"短链解析失败：{url}", 502)
            url = resolved

        parsed = URLParser.parse(url)
        if not parsed:
            raise WorksListError(f"不支持的链接：{url}")
        url_type = parsed["type"]

        if url_type in _SINGLE_TYPES:
            aweme_id = parsed.get("aweme_id") or parsed.get("note_id")
            if not aweme_id:
                raise WorksListError("链接中未解析出作品 ID")
            detail = await api_client.get_video_detail(str(aweme_id))
            item = normalize_aweme(detail)
            if item is None:
                raise WorksListError("获取作品详情失败，作品可能已删除或不可见", 502)
            return {"source_type": url_type, "items": [item], "has_more": False, "cursor": 0}

        if url_type not in _PAGED_TYPES:
            raise WorksListError(f"该链接类型（{url_type}）不支持作品列表预览")

        if url_type == "user":
            page = await api_client.get_user_post(parsed["sec_uid"], max_cursor=cursor, count=count)
        elif url_type == "collection":
            page = await api_client.get_mix_aweme(parsed["mix_id"], cursor=cursor, count=count)
        else:  # music
            page = await api_client.get_music_aweme(parsed["music_id"], cursor=cursor, count=count)

        raw_items = page.get("items") or []
        items: List[Dict[str, Any]] = []
        for raw in raw_items:
            item = normalize_aweme(raw)
            if item is not None:
                items.append(item)

        if not items and not page.get("has_more"):
            status_code = page.get("status_code")
            if status_code:
                raise WorksListError(f"上游接口返回异常（status_code={status_code}）", 502)

        return {
            "source_type": url_type,
            "items": items,
            "has_more": bool(page.get("has_more")),
            "cursor": int(page.get("max_cursor") or 0),
        }
