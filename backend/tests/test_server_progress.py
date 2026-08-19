"""任务实时进度测试：JobProgressReporter 写入与 /jobs 下发。"""

import asyncio
from typing import Dict

import pytest

try:
    from fastapi.testclient import TestClient  # type: ignore
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from conftest import mark_credentials_ready

from config import ConfigLoader
from server.app import build_app
from server.jobs import DownloadJob, JobManager, JobProgressReporter


def test_reporter_writes_progress_into_job():
    job = DownloadJob(job_id="j1", url="https://www.douyin.com/user/x")
    reporter = JobProgressReporter(job)

    reporter.update_step("获取作品列表", "第 1 页")
    assert job.progress["step"] == "获取作品列表"
    assert job.progress["detail"] == "第 1 页"

    reporter.set_item_total(30, "主页批量下载")
    assert job.progress["items_total"] == 30
    assert job.progress["detail"] == "主页批量下载"

    reporter.on_author(nickname="作者A", sec_uid="MS4w")
    assert job.progress["author"] == "作者A"
    reporter.on_author(nickname=None)  # 空昵称不覆盖
    assert job.progress["author"] == "作者A"

    reporter.on_output_dir(path="D:/Downloaded/作者A")
    assert job.progress["output_dir"] == "D:/Downloaded/作者A"

    reporter.on_item_progress(aweme_id="123", bytes_read=1024, bytes_total=4096)
    assert job.progress["current"] == {
        "aweme_id": "123",
        "bytes_read": 1024,
        "bytes_total": 4096,
    }

    # 作品完成：计数 +1，字节进度清空
    reporter.advance_item("success", "123")
    assert job.progress["items_done"] == 1
    assert job.progress["current"] is None

    reporter.advance_item("failed", "456")
    assert job.progress["items_done"] == 2


def test_job_to_dict_contains_progress():
    job = DownloadJob(job_id="j2", url="u")
    JobProgressReporter(job).set_item_total(5)
    data = job.to_dict()
    assert data["progress"]["items_total"] == 5
    assert data["progress"]["items_done"] == 0
    assert data["progress"]["current"] is None


@pytest.mark.asyncio
async def test_executor_receives_job_and_can_report():
    async def executor(job) -> Dict[str, int]:
        reporter = JobProgressReporter(job)
        reporter.set_item_total(2)
        reporter.advance_item("success")
        reporter.advance_item("success")
        return {"total": 2, "success": 2, "failed": 0, "skipped": 0}

    manager = JobManager(executor=executor)
    job = await manager.submit("https://www.douyin.com/user/x")
    await asyncio.wait_for(job._task, timeout=2.0)
    assert job.status == "success"
    assert job.progress["items_total"] == 2
    assert job.progress["items_done"] == 2


def test_jobs_endpoint_exposes_progress(tmp_path):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path), database=False)
    app = build_app(config)

    async def fake_executor(job) -> Dict[str, int]:
        JobProgressReporter(job).set_item_total(3)
        return {"total": 3, "success": 3, "failed": 0, "skipped": 0}

    app.state.job_manager.executor = fake_executor
    mark_credentials_ready(app)

    with TestClient(app) as client:
        job_id = client.post(
            "/api/v1/download", json={"url": "https://www.douyin.com/video/1"}
        ).json()["data"]["job_id"]
        detail = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        assert "progress" in detail
        assert set(detail["progress"]) >= {"step", "items_total", "items_done", "current"}
