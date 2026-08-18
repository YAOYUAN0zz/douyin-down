"""M4 历史记录测试：列表分页/搜索/筛选/排序、统计、详情、数据库关闭降级，
以及作品列表的「已下载」标记。

不触达真实 Douyin API：库表用独立 Database 实例预置，作品列表逻辑用 fake 替换。
"""

import asyncio
from typing import Any, Dict, List

import pytest

try:
    from fastapi.testclient import TestClient  # type: ignore
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from config import ConfigLoader
from server.api import works as works_api
from server.app import build_app
from storage import Database

_ROWS: List[Dict[str, Any]] = [
    {
        "aweme_id": "v1",
        "aweme_type": "video",
        "title": "猫咪日常 alpha",
        "author_id": "u1",
        "author_name": "喵星人",
        "author_sec_uid": "SEC_A",
        "create_time": 1_700_000_300,
        "file_path": "/downloads/v1",
        "metadata": '{"aweme_id": "v1", "desc": "猫咪日常 alpha"}',
        "job_id": "JOB_A",
    },
    {
        "aweme_id": "v2",
        "aweme_type": "video",
        "title": "猫咪日常 beta",
        "author_id": "u1",
        "author_name": "喵星人",
        "author_sec_uid": "SEC_A",
        "create_time": 1_700_000_200,
        "file_path": "/downloads/v2",
        "metadata": "{}",
        "job_id": "JOB_B",
    },
    {
        "aweme_id": "g1",
        "aweme_type": "gallery",
        "title": "旅行图集",
        "author_id": "u2",
        "author_name": "旅行者",
        "author_sec_uid": "SEC_B",
        "create_time": 1_700_000_100,
        "file_path": "/downloads/g1",
        "metadata": "not-json",
        "job_id": "",
    },
    {
        # 无落盘产物：历史是下载日志，这行必须被全部查询排除
        "aweme_id": "ghost",
        "aweme_type": "video",
        "title": "未下载",
        "author_id": "u3",
        "author_name": "幽灵",
        "author_sec_uid": "SEC_C",
        "create_time": 1_700_000_400,
        "file_path": "",
        "metadata": "{}",
    },
]


def _seed(db_path: str) -> None:
    """在建 app 之前把历史行写好（独立连接，避免抢 TestClient 的 event loop）。"""

    async def run() -> None:
        db = Database(db_path=db_path)
        await db.initialize()
        for row in _ROWS:
            await db.add_aweme(row)
        await db.close()

    asyncio.run(run())


def _make_app(tmp_path, *, database: bool = True):
    db_path = str(tmp_path / "history.db")
    if database:
        _seed(db_path)
    config = ConfigLoader(None)
    config.update(path=str(tmp_path), database=database, database_path=db_path)
    app = build_app(config)

    async def fake_executor(job) -> Dict[str, int]:
        return {"total": 1, "success": 1, "failed": 0, "skipped": 0}

    app.state.job_manager.executor = fake_executor
    return app


# ---------------- GET /history ----------------


def test_history_list_excludes_rows_without_artifact(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        data = client.get("/api/v1/history").json()["data"]
        assert data["total"] == 3
        assert {item["aweme_id"] for item in data["items"]} == {"v1", "v2", "g1"}
        assert data["page"] == 1
        assert data["page_size"] == 20


def test_history_list_paginates(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        page1 = client.get("/api/v1/history?page=1&page_size=2").json()["data"]
        page2 = client.get("/api/v1/history?page=2&page_size=2").json()["data"]
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 1
        assert page1["total"] == page2["total"] == 3
        assert page2["page"] == 2


def test_history_list_filters(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        by_title = client.get("/api/v1/history?query=alpha").json()["data"]
        assert [item["aweme_id"] for item in by_title["items"]] == ["v1"]

        by_author = client.get("/api/v1/history?author=旅行").json()["data"]
        assert [item["aweme_id"] for item in by_author["items"]] == ["g1"]

        by_type = client.get("/api/v1/history?aweme_type=gallery").json()["data"]
        assert [item["aweme_id"] for item in by_type["items"]] == ["g1"]

        by_sec_uid = client.get("/api/v1/history?author_sec_uid=SEC_A").json()["data"]
        assert {item["aweme_id"] for item in by_sec_uid["items"]} == {"v1", "v2"}

        by_job = client.get("/api/v1/history?job_id=JOB_A").json()["data"]
        assert [item["aweme_id"] for item in by_job["items"]] == ["v1"]


def test_history_list_sorts_by_create_time(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        data = client.get("/api/v1/history?sort=create_time").json()["data"]
        assert [item["aweme_id"] for item in data["items"]] == ["v1", "v2", "g1"]


@pytest.mark.parametrize(
    "query",
    ["sort=title", "page=0", "page_size=0", "page_size=101"],
)
def test_history_list_rejects_invalid_params(tmp_path, query):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.get(f"/api/v1/history?{query}")
        assert resp.status_code == 400
        assert resp.json()["code"] == 40000


# ---------------- GET /history/stats ----------------


def test_history_stats(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        data = client.get("/api/v1/history/stats").json()["data"]
        assert data["total"] == 3
        # 预置行的 create_time 是 2023 年，落在 7/30 天窗口之外
        assert data["top_authors_7d"] == []
        assert data["top_authors_30d"] == []


def test_history_stats_counts_recent_authors(tmp_path):
    import time

    db_path = str(tmp_path / "history.db")

    async def seed_recent() -> None:
        db = Database(db_path=db_path)
        await db.initialize()
        now = int(time.time())
        for idx in range(2):
            await db.add_aweme(
                {
                    "aweme_id": f"recent{idx}",
                    "aweme_type": "video",
                    "title": f"新作品{idx}",
                    "author_id": "u9",
                    "author_name": "近期作者",
                    "author_sec_uid": "SEC_RECENT",
                    "create_time": now - 3600,
                    "file_path": f"/downloads/recent{idx}",
                    "metadata": "{}",
                }
            )
        await db.close()

    asyncio.run(seed_recent())
    config = ConfigLoader(None)
    config.update(path=str(tmp_path), database=True, database_path=db_path)
    app = build_app(config)
    with TestClient(app) as client:
        data = client.get("/api/v1/history/stats?limit=5").json()["data"]
        assert data["top_authors_7d"] == [
            {"sec_uid": "SEC_RECENT", "author_name": "近期作者", "download_count": 2}
        ]


def test_history_stats_rejects_invalid_limit(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/v1/history/stats?limit=0")
        assert resp.status_code == 400
        assert resp.json()["code"] == 40000


# ---------------- GET /history/{aweme_id} ----------------


def test_history_detail_returns_metadata(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        data = client.get("/api/v1/history/v1").json()["data"]
        assert data["aweme_id"] == "v1"
        assert data["author_name"] == "喵星人"
        assert data["metadata"] == {"aweme_id": "v1", "desc": "猫咪日常 alpha"}


def test_history_detail_tolerates_broken_metadata(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        data = client.get("/api/v1/history/g1").json()["data"]
        assert data["metadata"] is None


def test_history_detail_404(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/v1/history/nope")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40400


# ---------------- 数据库关闭时降级 ----------------


@pytest.mark.parametrize("path", ["/api/v1/history", "/api/v1/history/stats", "/api/v1/history/v1"])
def test_history_endpoints_503_when_database_disabled(tmp_path, path):
    app = _make_app(tmp_path, database=False)
    with TestClient(app) as client:
        resp = client.get(path)
        assert resp.status_code == 503
        assert resp.json()["code"] == 50300


# ---------------- 作品列表「已下载」标记 ----------------


def test_works_list_marks_downloaded(tmp_path, monkeypatch):
    app = _make_app(tmp_path)

    async def fake_list_works(url, **kwargs):
        return {
            "source_type": "user",
            "items": [
                {"aweme_id": "v1", "download_url": "https://www.douyin.com/video/v1"},
                {"aweme_id": "new", "download_url": "https://www.douyin.com/video/new"},
                {"aweme_id": "ghost", "download_url": "https://www.douyin.com/video/ghost"},
            ],
            "has_more": False,
            "cursor": 0,
        }

    monkeypatch.setattr(works_api, "list_works", fake_list_works)
    with TestClient(app) as client:
        items = client.post(
            "/api/v1/works/list", json={"url": "https://www.douyin.com/user/x"}
        ).json()["data"]["items"]
        assert {item["aweme_id"]: item["downloaded"] for item in items} == {
            "v1": True,
            "new": False,
            # 无落盘产物的行不算已下载
            "ghost": False,
        }


def test_works_list_downloaded_false_when_database_disabled(tmp_path, monkeypatch):
    app = _make_app(tmp_path, database=False)

    async def fake_list_works(url, **kwargs):
        return {
            "source_type": "video",
            "items": [{"aweme_id": "v1", "download_url": "https://www.douyin.com/video/v1"}],
            "has_more": False,
            "cursor": 0,
        }

    monkeypatch.setattr(works_api, "list_works", fake_list_works)
    with TestClient(app) as client:
        items = client.post(
            "/api/v1/works/list", json={"url": "https://www.douyin.com/video/v1"}
        ).json()["data"]["items"]
        assert items[0]["downloaded"] is False
