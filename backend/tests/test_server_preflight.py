"""前置校验测试：环境/凭据不满足时端点必须同步拒绝，不产生半路失败的任务。

不触达真实 Playwright——环境检查通过 monkeypatch 模拟。
"""

from typing import Dict

import pytest

try:
    from fastapi.testclient import TestClient  # type: ignore
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from conftest import READY_COOKIES, mark_credentials_ready

from config import ConfigLoader
from server import preflight
from server.api import auth as auth_api
from server.app import build_app
from server.schemas import CODE_BROWSER_UNAVAILABLE, CODE_LOGIN_REQUIRED


def _make_app(tmp_path):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path), database=False)
    app = build_app(config)

    async def fake_executor(job) -> Dict[str, int]:
        return {"total": 1, "success": 1, "failed": 0, "skipped": 0}

    app.state.job_manager.executor = fake_executor
    return app


# ---------------------------------------------------------------- 凭据


def test_download_rejected_without_credentials(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post("/api/v1/download", json={"url": "https://www.douyin.com/video/1"})
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == CODE_LOGIN_REQUIRED
        # 报错要指名缺哪些键，否则用户无从下手
        assert "msToken" in body["message"]
        # 关键：不能留下一个注定失败的任务
        assert client.get("/api/v1/jobs").json()["data"]["jobs"] == []


def test_batch_download_rejected_without_credentials(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/download/batch",
            json={"urls": ["https://www.douyin.com/video/1", "https://www.douyin.com/video/2"]},
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == CODE_LOGIN_REQUIRED
        assert client.get("/api/v1/jobs").json()["data"]["jobs"] == []


def test_download_rejected_when_credentials_partially_missing(tmp_path):
    app = _make_app(tmp_path)
    partial = dict(READY_COOKIES)
    partial.pop("odin_tt")
    partial["msToken"] = "   "  # 空白值等同缺失
    app.state.deps.cookie_manager.cookies = partial

    with TestClient(app) as client:
        resp = client.post("/api/v1/download", json={"url": "https://www.douyin.com/video/1"})
        assert resp.status_code == 401
        message = resp.json()["message"]
        assert "odin_tt" in message and "msToken" in message
        assert "ttwid" not in message


def test_download_accepted_with_credentials(tmp_path):
    app = _make_app(tmp_path)
    mark_credentials_ready(app)
    with TestClient(app) as client:
        resp = client.post("/api/v1/download", json={"url": "https://www.douyin.com/video/1"})
        assert resp.status_code == 200


def test_param_errors_take_precedence_over_credentials(tmp_path):
    """参数错误调用方立刻可改，应先于凭据校验返回，避免先改登录再发现参数还错。"""
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/download",
            json={"url": "https://www.douyin.com/video/1", "video_quality": "4k"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------- 浏览器环境


def test_auth_fetch_rejected_when_browser_env_missing(tmp_path, monkeypatch):
    app = _make_app(tmp_path)

    async def broken_env(browser="chromium"):
        return "未安装 Playwright。请执行：uv sync ..."

    # ensure_browser_env 在模块内以全局名查找 browser_env_problem，patch 后者即可
    monkeypatch.setattr(preflight, "browser_env_problem", broken_env)

    with TestClient(app) as client:
        resp = client.post("/api/v1/auth/fetch")
        assert resp.status_code == 503
        body = resp.json()
        assert body["code"] == CODE_BROWSER_UNAVAILABLE
        assert "uv sync" in body["message"]  # 报错须自带修复命令
        # 关键：不能进入 running 状态，否则真正的原因要翻快照才看得到
        assert client.get("/api/v1/auth/fetch/status").json()["data"]["status"] == "idle"


def test_auth_status_reports_browser_readiness(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    monkeypatch.setattr(preflight, "browser_package_problem", lambda: None)
    monkeypatch.setattr(auth_api, "browser_package_problem", lambda: None)

    with TestClient(app) as client:
        data = client.get("/api/v1/auth/status").json()["data"]
        assert data["browser_ready"] is True
        assert data["browser_hint"] is None

    monkeypatch.setattr(auth_api, "browser_package_problem", lambda: "未安装 Playwright。")
    with TestClient(app) as client:
        data = client.get("/api/v1/auth/status").json()["data"]
        assert data["browser_ready"] is False
        assert "Playwright" in data["browser_hint"]


@pytest.mark.asyncio
async def test_browser_env_problem_detects_missing_package(monkeypatch):
    monkeypatch.setattr(preflight.importlib.util, "find_spec", lambda name: None)
    problem = await preflight.browser_env_problem()
    assert problem is not None
    assert "uv sync" in problem


@pytest.mark.asyncio
async def test_missing_credentials_treats_blank_as_absent(tmp_path):
    class _Manager:
        def get_cookies(self):
            return {"msToken": "m", "ttwid": "", "odin_tt": "  ", "passport_csrf_token": "p"}

    assert preflight.missing_credentials(_Manager()) == ["odin_tt", "ttwid"]
