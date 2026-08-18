"""作品列表预览与批量按需下载接口测试。

不触达真实 Douyin API：列表逻辑用 fake 替换，规整函数用构造 payload 直测。
"""

from typing import Dict

import pytest

try:
    from fastapi.testclient import TestClient  # type: ignore
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from config import ConfigLoader
from server.api import works as works_api
from server.app import build_app
from server.works import WorksListError, list_works, normalize_aweme


def _make_app(tmp_path):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path), database=False)
    app = build_app(config)

    async def fake_executor(job) -> Dict[str, int]:
        return {"total": 1, "success": 1, "failed": 0, "skipped": 0}

    app.state.job_manager.executor = fake_executor
    return app


# ---------------- normalize_aweme ----------------


def test_normalize_aweme_video():
    item = normalize_aweme(
        {
            "aweme_id": 7300000000000000001,
            "desc": " 测试视频 ",
            "create_time": 1723900000,
            "video": {
                "duration": 65500,
                "origin_cover": {"url_list": ["https://p3.douyinpic.com/cover.jpg"]},
            },
            "statistics": {"digg_count": 12345, "comment_count": 67, "collect_count": 8},
            "author": {"nickname": "作者A", "sec_uid": "MS4wLjABAAAA_x"},
        }
    )
    assert item is not None
    assert item["aweme_id"] == "7300000000000000001"
    assert item["desc"] == "测试视频"
    assert item["media_type"] == "video"
    assert item["duration_seconds"] == 65
    assert item["cover"] == "https://p3.douyinpic.com/cover.jpg"
    assert item["stats"]["digg_count"] == 12345
    assert item["author"] == "作者A"
    assert item["download_url"] == "https://www.douyin.com/video/7300000000000000001"


def test_normalize_aweme_images():
    item = normalize_aweme(
        {
            "aweme_id": "7300000000000000002",
            "desc": "图集",
            "images": [
                {"url_list": ["https://p3.douyinpic.com/img1.jpg"]},
                {"url_list": ["https://p3.douyinpic.com/img2.jpg"]},
            ],
        }
    )
    assert item is not None
    assert item["media_type"] == "images"
    assert item["image_count"] == 2
    assert item["cover"] == "https://p3.douyinpic.com/img1.jpg"
    assert item["download_url"] == "https://www.douyin.com/note/7300000000000000002"


def test_normalize_aweme_exposes_size_and_metadata():
    item = normalize_aweme(
        {
            "aweme_id": "7300000000000000003",
            "desc": "元数据",
            "video": {
                "duration": 10000,
                "bit_rate": [
                    {
                        "gear_name": "normal_1080_0",
                        "bit_rate": 3000000,
                        "play_addr": {"width": 1080, "height": 1920, "data_size": 8000000},
                    }
                ],
            },
            "statistics": {
                "digg_count": 10,
                "comment_count": 2,
                "collect_count": 3,
                "share_count": 4,
                "play_count": 500,
            },
            "text_extra": [
                {"hashtag_name": "旅行"},
                {"hashtag_name": "旅行"},  # 去重
                {"hashtag_name": ""},
                {"end": 3},  # 非话题条目
            ],
            "music": {"title": "原声 - 作者A"},
        }
    )
    assert item is not None
    assert item["size_bytes"] == 8000000
    assert item["stats"]["share_count"] == 4
    assert item["stats"]["play_count"] == 500
    assert item["tags"] == ["旅行"]
    assert item["music_title"] == "原声 - 作者A"


def test_normalize_aweme_images_size_zero():
    item = normalize_aweme(
        {"aweme_id": "4", "images": [{"url_list": ["https://p3.douyinpic.com/i.jpg"]}]}
    )
    assert item is not None
    assert item["size_bytes"] == 0
    assert item["tags"] == []
    assert item["music_title"] == ""


def test_normalize_aweme_rejects_missing_id():
    assert normalize_aweme({}) is None
    assert normalize_aweme(None) is None
    assert normalize_aweme({"aweme_id": "  "}) is None


# ---------------- list_works ----------------


@pytest.mark.asyncio
async def test_list_works_rejects_unsupported_url():
    with pytest.raises(WorksListError):
        await list_works("https://example.com/whatever", cookies={})


# ---------------- HTTP 端点 ----------------


def test_works_list_endpoint_returns_page(tmp_path, monkeypatch):
    app = _make_app(tmp_path)

    async def fake_list_works(url, **kwargs):
        assert url == "https://www.douyin.com/user/MS4wLjABAAAA_x"
        assert kwargs["cursor"] == 0
        return {
            "source_type": "user",
            "items": [{"aweme_id": "1", "download_url": "https://www.douyin.com/video/1"}],
            "has_more": True,
            "cursor": 1723900000,
        }

    monkeypatch.setattr(works_api, "list_works", fake_list_works)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/works/list",
            json={"url": "https://www.douyin.com/user/MS4wLjABAAAA_x"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["source_type"] == "user"
        assert data["has_more"] is True
        assert data["cursor"] == 1723900000
        assert len(data["items"]) == 1


def test_works_list_endpoint_maps_error_status(tmp_path, monkeypatch):
    app = _make_app(tmp_path)

    async def failing_list_works(url, **kwargs):
        raise WorksListError("上游接口返回异常", 502)

    monkeypatch.setattr(works_api, "list_works", failing_list_works)

    with TestClient(app) as client:
        resp = client.post("/api/v1/works/list", json={"url": "https://www.douyin.com/user/x"})
        assert resp.status_code == 502
        body = resp.json()
        assert body["code"] == 50200
        assert "上游" in body["message"]


def test_works_list_endpoint_rejects_empty_url(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/v1/works/list", json={"url": "  "}).status_code == 400


def test_batch_download_creates_jobs(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/download/batch",
            json={"urls": ["https://www.douyin.com/video/1", "https://www.douyin.com/note/2", " "]},
        )
        assert resp.status_code == 200
        jobs = resp.json()["data"]["jobs"]
        assert len(jobs) == 2
        assert {j["url"] for j in jobs} == {
            "https://www.douyin.com/video/1",
            "https://www.douyin.com/note/2",
        }
        # 任务应进入 job 列表
        listed = client.get("/api/v1/jobs").json()["data"]["jobs"]
        assert {j["job_id"] for j in jobs} <= {j["job_id"] for j in listed}


def test_batch_download_rejects_empty_and_oversized(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/v1/download/batch", json={"urls": []}).status_code == 400
        assert client.post("/api/v1/download/batch", json={"urls": ["  "]}).status_code == 400
        too_many = [f"https://www.douyin.com/video/{i}" for i in range(101)]
        assert client.post("/api/v1/download/batch", json={"urls": too_many}).status_code == 400
