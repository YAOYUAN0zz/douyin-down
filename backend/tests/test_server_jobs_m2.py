"""M2 任务中心测试：partial 状态、取消/重试/删除/清空、筛选分页、持久化恢复。"""

import asyncio
from typing import Dict

import pytest

try:
    from fastapi.testclient import TestClient  # type: ignore
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from config import ConfigLoader
from server.app import build_app
from server.jobs import JobManager, JobStatus
from storage import Database


def _make_app(tmp_path, **config_extra):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path), database=False, **config_extra)
    app = build_app(config)

    async def fake_executor(job) -> Dict[str, int]:
        return {"total": 1, "success": 1, "failed": 0, "skipped": 0}

    app.state.job_manager.executor = fake_executor
    return app


# ---------------- 状态映射 ----------------


@pytest.mark.asyncio
async def test_partial_status_when_some_items_fail():
    async def executor(job) -> Dict[str, int]:
        return {"total": 3, "success": 2, "failed": 1, "skipped": 0}

    manager = JobManager(executor=executor)
    job = await manager.submit("u")
    await asyncio.wait_for(job._task, timeout=2.0)
    assert job.status == JobStatus.PARTIAL


@pytest.mark.asyncio
async def test_failed_status_when_all_items_fail():
    async def executor(job) -> Dict[str, int]:
        return {"total": 2, "success": 0, "failed": 2, "skipped": 0}

    manager = JobManager(executor=executor)
    job = await manager.submit("u")
    await asyncio.wait_for(job._task, timeout=2.0)
    assert job.status == JobStatus.FAILED


@pytest.mark.asyncio
async def test_partial_status_when_failed_but_skipped():
    async def executor(job) -> Dict[str, int]:
        return {"total": 2, "success": 0, "failed": 1, "skipped": 1}

    manager = JobManager(executor=executor)
    job = await manager.submit("u")
    await asyncio.wait_for(job._task, timeout=2.0)
    assert job.status == JobStatus.PARTIAL


# ---------------- 取消 / 重试 / 删除 / 清空（JobManager 层） ----------------


@pytest.mark.asyncio
async def test_cancel_running_job():
    started = asyncio.Event()

    async def slow_executor(job) -> Dict[str, int]:
        started.set()
        await asyncio.sleep(30)
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

    manager = JobManager(executor=slow_executor)
    job = await manager.submit("u")
    await asyncio.wait_for(started.wait(), timeout=2.0)

    cancelled = await manager.cancel(job.job_id)
    assert cancelled is not None
    assert cancelled.status == JobStatus.CANCELLED
    assert cancelled.finished_at is not None


@pytest.mark.asyncio
async def test_cancel_finished_job_raises():
    async def executor(job) -> Dict[str, int]:
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

    manager = JobManager(executor=executor)
    job = await manager.submit("u")
    await asyncio.wait_for(job._task, timeout=2.0)
    with pytest.raises(ValueError):
        await manager.cancel(job.job_id)
    assert await manager.cancel("missing") is None


@pytest.mark.asyncio
async def test_retry_creates_new_job_with_same_options():
    async def executor(job) -> Dict[str, int]:
        return {"total": 1, "success": 0, "failed": 1, "skipped": 0}

    manager = JobManager(executor=executor)
    job = await manager.submit("u", options={"video_quality": "720p"})
    await asyncio.wait_for(job._task, timeout=2.0)

    new_job = await manager.retry(job.job_id)
    assert new_job is not None
    assert new_job.job_id != job.job_id
    assert new_job.url == "u"
    assert new_job.options == {"video_quality": "720p"}
    await asyncio.wait_for(new_job._task, timeout=2.0)


@pytest.mark.asyncio
async def test_delete_and_clear_finished():
    async def executor(job) -> Dict[str, int]:
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

    manager = JobManager(executor=executor)
    j1 = await manager.submit("u1")
    j2 = await manager.submit("u2")
    await asyncio.wait_for(j1._task, timeout=2.0)
    await asyncio.wait_for(j2._task, timeout=2.0)

    deleted = await manager.delete(j1.job_id)
    assert deleted is not None
    assert await manager.get(j1.job_id) is None

    cleared = await manager.clear_finished()
    assert cleared == 1
    assert await manager.list_jobs() == []


# ---------------- HTTP 端点 ----------------


def test_jobs_filter_and_pagination(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        for i in range(3):
            client.post("/api/v1/download", json={"url": f"https://www.douyin.com/video/{i}"})
        data = client.get("/api/v1/jobs?status=all&page=1&page_size=2").json()["data"]
        assert data["total"] == 3
        assert len(data["jobs"]) == 2
        # 服务端按创建时间倒序
        assert data["jobs"][0]["created_at"] >= data["jobs"][1]["created_at"]

        assert client.get("/api/v1/jobs?status=bogus").status_code == 400


def test_jobs_cancel_retry_delete_clear_endpoints(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        job_id = client.post(
            "/api/v1/download", json={"url": "https://www.douyin.com/video/1"}
        ).json()["data"]["job_id"]

        # 等 job 落终态（fake executor 立即完成）
        for _ in range(50):
            detail = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
            if detail["status"] in ("success", "partial", "failed", "cancelled"):
                break

        # 终态取消 → 409
        assert client.post(f"/api/v1/jobs/{job_id}/cancel").status_code == 409
        # 重试 → 新 job
        retried = client.post(f"/api/v1/jobs/{job_id}/retry")
        assert retried.status_code == 200
        new_id = retried.json()["data"]["job_id"]
        assert new_id != job_id
        # 不存在的 job
        assert client.post("/api/v1/jobs/nope/cancel").status_code == 404
        assert client.post("/api/v1/jobs/nope/retry").status_code == 404
        assert client.delete("/api/v1/jobs/nope").status_code == 404

        # 等重试的 job 结束后删除原 job、清空
        for _ in range(50):
            detail = client.get(f"/api/v1/jobs/{new_id}").json()["data"]
            if detail["status"] in ("success", "partial", "failed", "cancelled"):
                break
        assert client.delete(f"/api/v1/jobs/{job_id}").status_code == 200
        assert client.get(f"/api/v1/jobs/{job_id}").status_code == 404
        cleared = client.post("/api/v1/jobs/clear").json()["data"]
        assert cleared["deleted"] >= 1


def test_jobs_events_sse_endpoint(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        with client.stream("GET", "/api/v1/jobs/events?limit=1") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            seen_data = False
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    assert '"jobs"' in line
                    seen_data = True
            assert seen_data


# ---------------- 持久化 ----------------


@pytest.mark.asyncio
async def test_terminal_jobs_persist_and_restore(tmp_path):
    db = Database(str(tmp_path / "jobs.db"))
    await db.initialize()

    async def executor(job) -> Dict[str, int]:
        return {"total": 3, "success": 2, "failed": 1, "skipped": 0}

    manager = JobManager(executor=executor, database=db)
    job = await manager.submit("https://www.douyin.com/video/1", options={"video_quality": "720p"})
    await asyncio.wait_for(job._task, timeout=2.0)
    assert job.status == JobStatus.PARTIAL

    # 模拟重启：新 manager 从同一 db 恢复
    manager2 = JobManager(executor=executor, database=db)
    restored = await manager2.load_persisted()
    assert restored == 1
    loaded = await manager2.get(job.job_id)
    assert loaded is not None
    assert loaded.status == JobStatus.PARTIAL
    assert loaded.total == 3
    assert loaded.options == {"video_quality": "720p"}

    # 删除同步落库
    await manager2.delete(job.job_id)
    manager3 = JobManager(executor=executor, database=db)
    assert await manager3.load_persisted() == 0
    await db.close()
