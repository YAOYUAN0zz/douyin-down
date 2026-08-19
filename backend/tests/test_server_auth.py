"""Web UI 认证接口测试：/api/v1/auth/* 与首页静态页。

不触达真实浏览器/Playwright——通过替换 BrowserAuthFlow 的内部执行体来驱动状态机。
"""

import asyncio

import pytest

try:
    from fastapi.testclient import TestClient  # type: ignore
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from auth import CookieManager
from config import ConfigLoader
from server.api import auth as auth_api
from server.app import build_app
from server.auth_flow import AuthFlowStatus, BrowserAuthFlow


def _make_app(tmp_path):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path), database=False)
    return build_app(config)


def test_webui_index_served(tmp_path):
    """根路径始终返回 HTML：有 frontend/dist 时服务构建产物，否则返回占位页。"""
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


def test_auth_status_reports_missing_keys(tmp_path):
    app = _make_app(tmp_path)
    app.state.deps.cookie_manager.cookies = {"ttwid": "t", "msToken": "m"}

    with TestClient(app) as client:
        resp = client.get("/api/v1/auth/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["ready"] is False
        assert "odin_tt" in data["missing"]
        assert "passport_csrf_token" in data["missing"]
        assert "ttwid" not in data["missing"]
        assert data["has_session"] is False
        assert data["cookie_count"] == 2


def test_auth_status_ready_when_all_required_present(tmp_path):
    app = _make_app(tmp_path)
    app.state.deps.cookie_manager.cookies = {
        "msToken": "m",
        "ttwid": "t",
        "odin_tt": "o",
        "passport_csrf_token": "p",
        "sessionid": "s",
    }

    with TestClient(app) as client:
        data = client.get("/api/v1/auth/status").json()["data"]
        assert data["ready"] is True
        assert data["missing"] == []
        assert data["has_session"] is True


def test_disk_cookies_survive_restart_over_config_cookies(tmp_path):
    """自动获取写盘的 cookie 不应在重启时被 config 内嵌 cookies 覆盖。"""
    import json

    cookie_file = tmp_path / ".cookies.json"
    fresh = {"msToken": "fresh", "ttwid": "fresh", "sessionid": "fresh"}
    cookie_file.write_text(json.dumps(fresh), encoding="utf-8")

    config = ConfigLoader(None)
    config.update(path=str(tmp_path), database=False, cookies={"msToken": "stale", "ttwid": "stale"})
    config.config_path = str(tmp_path / "config.yml")

    app = build_app(config)
    assert app.state.deps.cookie_manager.get_cookies() == fresh
    # 磁盘文件未被覆盖
    assert json.loads(cookie_file.read_text(encoding="utf-8")) == fresh


def test_config_cookies_seed_first_run(tmp_path):
    """首次运行（无 cookie 文件）时，config 内嵌 cookies 作为种子导入并落盘。"""
    import json

    config = ConfigLoader(None)
    config.update(path=str(tmp_path), database=False, cookies={"msToken": "seed", "ttwid": "seed"})
    config.config_path = str(tmp_path / "config.yml")

    app = build_app(config)
    assert app.state.deps.cookie_manager.get_cookies() == {"msToken": "seed", "ttwid": "seed"}
    cookie_file = tmp_path / ".cookies.json"
    assert json.loads(cookie_file.read_text(encoding="utf-8")) == {
        "msToken": "seed",
        "ttwid": "seed",
    }


def test_auth_fetch_confirm_without_session_returns_409(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post("/api/v1/auth/fetch/confirm")
        assert resp.status_code == 409
        assert resp.json()["code"] == 40900
        assert client.post("/api/v1/auth/fetch/cancel").status_code == 409
        status = client.get("/api/v1/auth/fetch/status").json()["data"]
        assert status["status"] == "idle"


def test_auth_fetch_start_rejects_concurrent_sessions(tmp_path, monkeypatch):
    app = _make_app(tmp_path)

    # 绕开浏览器环境前置校验：本用例只关心会话并发语义，且不应依赖本机是否装了
    # Playwright 内核（前置校验本身由 test_server_preflight.py 覆盖）
    async def skip_browser_check(browser="chromium"):
        return None

    monkeypatch.setattr(auth_api, "ensure_browser_env", skip_browser_check)

    async def slow_run(self):
        # 等待 cancel 信号（由 lifespan 关停时的 auth_flow.shutdown() 触发）
        try:
            await self._sleep_or_cancel(30.0)
        except Exception:
            pass
        self.status = AuthFlowStatus.CANCELLED

    monkeypatch.setattr(BrowserAuthFlow, "_run", slow_run)

    with TestClient(app) as client:
        assert client.post("/api/v1/auth/fetch").status_code == 200
        # 第二次启动应被拒绝
        assert client.post("/api/v1/auth/fetch").status_code == 409
        assert client.get("/api/v1/auth/fetch/status").json()["data"]["status"] == "running"


@pytest.mark.asyncio
async def test_flow_finish_with_cookies_saves_and_reports(tmp_path):
    manager = CookieManager(cookie_file=str(tmp_path / ".cookies.json"))
    flow = BrowserAuthFlow(manager)

    flow._finish_with_cookies(
        {"msToken": "m", "ttwid": "t", "odin_tt": "o", "passport_csrf_token": "p"}
    )

    assert flow.status == AuthFlowStatus.SUCCESS
    assert flow.missing == []
    assert flow.captured_count == 4
    assert manager.get_cookies()["msToken"] == "m"
    assert (tmp_path / ".cookies.json").exists()


@pytest.mark.asyncio
async def test_flow_finish_with_cookies_reports_missing_required(tmp_path):
    manager = CookieManager(cookie_file=str(tmp_path / ".cookies.json"))
    flow = BrowserAuthFlow(manager)

    flow._finish_with_cookies({"ttwid": "t"})

    assert flow.status == AuthFlowStatus.SUCCESS
    assert set(flow.missing) == {"msToken", "odin_tt", "passport_csrf_token"}
    assert "缺少" in (flow.message or "")


@pytest.mark.asyncio
async def test_flow_finish_with_empty_cookies_raises(tmp_path):
    manager = CookieManager(cookie_file=str(tmp_path / ".cookies.json"))
    flow = BrowserAuthFlow(manager)
    with pytest.raises(RuntimeError):
        flow._finish_with_cookies({})


@pytest.mark.asyncio
async def test_flow_run_marks_failed_on_error(tmp_path, monkeypatch):
    manager = CookieManager(cookie_file=str(tmp_path / ".cookies.json"))
    flow = BrowserAuthFlow(manager)

    async def boom(self):
        raise RuntimeError("browser exploded")

    monkeypatch.setattr(BrowserAuthFlow, "_run_browser_session", boom)

    assert await flow.start() is True
    await asyncio.wait_for(flow._task, timeout=2.0)
    assert flow.status == AuthFlowStatus.FAILED
    assert "browser exploded" in (flow.message or "")
    assert flow.finished_at is not None


@pytest.mark.asyncio
async def test_flow_cancel_marks_cancelled(tmp_path, monkeypatch):
    manager = CookieManager(cookie_file=str(tmp_path / ".cookies.json"))
    flow = BrowserAuthFlow(manager)

    async def wait_forever(self):
        await self._sleep_or_cancel(30.0)

    monkeypatch.setattr(BrowserAuthFlow, "_run_browser_session", wait_forever)

    assert await flow.start() is True
    assert await flow.cancel() is True
    await asyncio.wait_for(flow._task, timeout=2.0)
    assert flow.status == AuthFlowStatus.CANCELLED
    # 会话结束后 confirm/cancel 均应报告无会话
    assert await flow.confirm() is False
    assert await flow.cancel() is False
