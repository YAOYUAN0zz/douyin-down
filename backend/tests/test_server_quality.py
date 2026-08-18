"""画质相关测试：档位提取、per-job 画质覆盖与参数校验。"""

from typing import Dict

import pytest

try:
    from fastapi.testclient import TestClient  # type: ignore
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from config import ConfigLoader
from server.app import build_app
from server.deps import OverrideConfig
from server.works import extract_qualities, normalize_aweme


def _make_app(tmp_path):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path), database=False)
    app = build_app(config)

    async def fake_executor(job) -> Dict[str, int]:
        return {"total": 1, "success": 1, "failed": 0, "skipped": 0}

    app.state.job_manager.executor = fake_executor
    return app


_BIT_RATE_PAYLOAD = {
    "bit_rate": [
        {
            "gear_name": "normal_720_0",
            "bit_rate": 1500000,
            "FPS": 30,
            "format": "mp4",
            "play_addr": {"width": 720, "height": 1280, "data_size": 4000000},
        },
        {
            "gear_name": "normal_1080_0",
            "bit_rate": 3000000,
            "FPS": 30,
            "format": "mp4",
            "play_addr": {"width": 1080, "height": 1920, "data_size": 8000000},
        },
        {
            "gear_name": "lower_540_0",
            "bit_rate": 800000,
            "FPS": 30,
            "format": "mp4",
            "play_addr": {"width": 540, "height": 960, "data_size": 2000000},
        },
    ]
}


def test_extract_qualities_sorted_desc():
    qualities = extract_qualities(_BIT_RATE_PAYLOAD)
    assert [q["label"] for q in qualities] == ["1080p", "720p", "540p"]
    top = qualities[0]
    assert top["width"] == 1080
    assert top["height"] == 1920
    assert top["bit_rate"] == 3000000
    assert top["size_bytes"] == 8000000
    assert top["fps"] == 30
    assert top["format"] == "mp4"
    assert top["gear_name"] == "normal_1080_0"


def test_extract_qualities_handles_missing_ladder():
    assert extract_qualities(None) == []
    assert extract_qualities({}) == []
    assert extract_qualities({"bit_rate": "oops"}) == []


def test_normalize_aweme_includes_qualities_for_video():
    item = normalize_aweme(
        {
            "aweme_id": "1",
            "video": dict(_BIT_RATE_PAYLOAD, duration=10000),
        }
    )
    assert item is not None
    assert [q["label"] for q in item["qualities"]] == ["1080p", "720p", "540p"]


def test_normalize_aweme_images_have_no_qualities():
    item = normalize_aweme(
        {"aweme_id": "2", "images": [{"url_list": ["https://p3.douyinpic.com/i.jpg"]}]}
    )
    assert item is not None
    assert item["qualities"] == []


def test_override_config_shadows_only_given_keys(tmp_path):
    base = ConfigLoader(None)
    base.update(path=str(tmp_path), video_quality="highest", thread=7)
    view = OverrideConfig(base, {"video_quality": "720p"})

    assert view.get("video_quality") == "720p"
    assert view.get("thread") == 7
    assert view.get("nonexistent", "fallback") == "fallback"
    # 属性透传（如 config_path）
    assert view.config_path == base.config_path
    # 底层配置不被污染
    assert base.get("video_quality") == "highest"


def test_download_accepts_and_records_video_quality(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/download",
            json={"url": "https://www.douyin.com/video/1", "video_quality": "720p"},
        )
        assert resp.status_code == 200
        job_id = resp.json()["data"]["job_id"]
        detail = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        assert detail["options"] == {"video_quality": "720p"}


def test_download_without_quality_keeps_options_none(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post("/api/v1/download", json={"url": "https://www.douyin.com/video/1"})
        job_id = resp.json()["data"]["job_id"]
        assert client.get(f"/api/v1/jobs/{job_id}").json()["data"]["options"] is None


def test_download_rejects_unknown_quality(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/download",
            json={"url": "https://www.douyin.com/video/1", "video_quality": "4k"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == 40001
        assert "画质" in body["message"]


def test_batch_download_applies_quality_to_all_jobs(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/download/batch",
            json={
                "urls": ["https://www.douyin.com/video/1", "https://www.douyin.com/video/2"],
                "video_quality": "ORIGINAL",
            },
        )
        assert resp.status_code == 200
        listed = {j["job_id"]: j for j in client.get("/api/v1/jobs").json()["data"]["jobs"]}
        for job in resp.json()["data"]["jobs"]:
            assert listed[job["job_id"]]["options"] == {"video_quality": "original"}
