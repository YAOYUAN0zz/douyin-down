"""设置端点测试：白名单、校验、热应用、落盘与密钥打码。

覆盖的核心保证：用户在 Web UI 改配置后 (a) 立即对后续下载生效、
(b) 落盘到 config.yml 从而重启后仍在、(c) 改不动不该改的键。
"""

from __future__ import annotations

import pytest
import yaml

try:
    from fastapi.testclient import TestClient  # type: ignore
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from config import ConfigLoader
from server.app import build_app


def _build(tmp_path, **overrides):
    """构造一个带真实 config.yml 路径的 app，以便验证落盘。"""
    config_path = tmp_path / "config.yml"
    config = ConfigLoader(str(config_path))
    config.update(path=str(tmp_path / "Downloaded"), database=False, **overrides)
    return build_app(config), config_path


def _put(client, payload):
    return client.put("/api/v1/settings", json=payload)


# ---------------- 读取 ----------------


def test_get_settings_returns_editable_keys(tmp_path):
    app, config_path = _build(tmp_path)
    with TestClient(app) as client:
        body = client.get("/api/v1/settings").json()

    assert body["code"] == 0
    data = body["data"]
    # 可编辑键齐全
    for key in ("path", "thread", "video_quality", "filename_template", "comments"):
        assert key in data["values"]
    # 敏感/运行时键不暴露
    assert "cookies" not in data["values"]
    assert "link" not in data["values"]
    assert data["config_path"] == str(config_path)
    assert data["requires_restart_keys"] == ["thread"]


# ---------------- 写入与落盘 ----------------


def test_put_settings_persists_to_yaml(tmp_path):
    app, config_path = _build(tmp_path)
    with TestClient(app) as client:
        body = _put(client, {"video_quality": "1080p", "cover": True}).json()

    assert body["code"] == 0
    assert body["data"]["saved"] is True
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["video_quality"] == "1080p"
    assert written["cover"] is True


def test_put_settings_survives_reload(tmp_path):
    """落盘的意义在于新进程能读回来——等价于重启服务。"""
    app, config_path = _build(tmp_path)
    with TestClient(app) as client:
        _put(client, {"thread": 9, "author_dir": "nickname_uid"})

    reloaded = ConfigLoader(str(config_path))
    assert reloaded.get("thread") == 9
    assert reloaded.get("author_dir") == "nickname_uid"


def test_put_settings_partial_update_keeps_other_keys(tmp_path):
    app, _ = _build(tmp_path)
    with TestClient(app) as client:
        before = client.get("/api/v1/settings").json()["data"]["values"]
        _put(client, {"cover": True})
        after = client.get("/api/v1/settings").json()["data"]["values"]

    assert after["cover"] is True
    assert after["video_quality"] == before["video_quality"]
    assert after["filename_template"] == before["filename_template"]


def test_put_settings_preserves_user_authored_keys(tmp_path):
    """用户手写的 link/cookies 不能因为 UI 保存就被抹掉。"""
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "link:\n  - https://www.douyin.com/video/123\ncookies:\n  ttwid: abc\n",
        encoding="utf-8",
    )
    config = ConfigLoader(str(config_path))
    config.update(path=str(tmp_path / "Downloaded"), database=False)
    app = build_app(config)

    with TestClient(app) as client:
        _put(client, {"thread": 6})

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["link"] == ["https://www.douyin.com/video/123"]
    assert written["cookies"] == {"ttwid": "abc"}
    assert written["thread"] == 6


# ---------------- 热应用 ----------------


def test_put_settings_hot_applies_runtime_components(tmp_path):
    """path/rate_limit/retry_times 必须同步到已构造的组件，否则改了不生效。"""
    app, _ = _build(tmp_path)
    new_dir = tmp_path / "elsewhere"

    with TestClient(app) as client:
        _put(client, {"path": str(new_dir), "rate_limit": 5.0, "retry_times": 7})

    deps = app.state.deps
    assert deps.file_manager.base_path == new_dir
    assert new_dir.is_dir()
    assert deps.rate_limiter.max_per_second == 5.0
    # 派生字段必须一起改，否则限速仍按旧值执行
    assert deps.rate_limiter.min_interval == pytest.approx(0.2)
    assert deps.retry_handler.max_retries == 7


def test_put_thread_reports_restart_required(tmp_path):
    """thread 烧在 Semaphore 里，不热改，但要如实告知前端。"""
    app, _ = _build(tmp_path, thread=5)
    with TestClient(app) as client:
        data = _put(client, {"thread": 12}).json()["data"]

    assert data["restart_required"] == ["thread"]
    assert data["values"]["thread"] == 12


def test_unchanged_thread_does_not_report_restart(tmp_path):
    app, _ = _build(tmp_path, thread=5)
    with TestClient(app) as client:
        data = _put(client, {"thread": 5}).json()["data"]

    assert data["restart_required"] == []


# ---------------- 校验与白名单 ----------------


@pytest.mark.parametrize(
    "payload,hint",
    [
        ({"thread": 0}, "1~32"),
        ({"thread": 99}, "1~32"),
        ({"thread": "5"}, "整数"),
        ({"thread": True}, "整数"),
        ({"retry_times": -1}, "0~10"),
        ({"rate_limit": 0}, "0.1~20"),
        ({"video_quality": "4k"}, "video_quality"),
        ({"author_dir": "whatever"}, "author_dir"),
        ({"path": "  "}, "不能为空"),
        ({"cover": "yes"}, "布尔"),
        ({"filename_template": "{title}"}, "{id}"),
        ({"folder_template": "{date}"}, "{id}"),
        ({"comments": {"page_size": 999}}, "1~50"),
        ({"comments": {"nope": 1}}, "不是可配置项"),
        ({"comments": "on"}, "必须是对象"),
        ({"notifications": {"providers": [{"type": "smoke"}]}}, "type"),
        ({"notifications": {"providers": [{"type": "bark"}]}}, "url"),
    ],
)
def test_put_settings_rejects_invalid_values(tmp_path, payload, hint):
    app, _ = _build(tmp_path)
    with TestClient(app) as client:
        resp = _put(client, payload)

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 40000
    assert hint in body["message"]
    assert body["data"] is None


@pytest.mark.parametrize(
    "key", ["cookies", "link", "database", "database_path", "mode", "transcript"]
)
def test_put_settings_rejects_non_editable_keys(tmp_path, key):
    """cookies/link 等运行时或敏感键不得经设置页写入。

    transcript 在此列是因为转写功能已整体移除——若它重新出现在白名单里，
    这条测试会立刻失败。
    """
    app, _ = _build(tmp_path)
    with TestClient(app) as client:
        resp = _put(client, {key: "whatever"})

    assert resp.status_code == 400
    assert resp.json()["code"] == 40000
    assert "不可配置" in resp.json()["message"]


def test_put_settings_rejects_empty_body(tmp_path):
    app, _ = _build(tmp_path)
    with TestClient(app) as client:
        assert _put(client, {}).status_code == 400


def test_invalid_value_does_not_partially_apply(tmp_path):
    """一个键非法时整个请求不落地，不能改一半。"""
    app, config_path = _build(tmp_path, thread=5)
    with TestClient(app) as client:
        _put(client, {"cover": True, "thread": 999})
        values = client.get("/api/v1/settings").json()["data"]["values"]

    assert values["thread"] == 5
    assert values["cover"] is False
    assert not config_path.exists()


def test_notifications_providers_roundtrip(tmp_path):
    app, config_path = _build(tmp_path)
    providers = [
        {"type": "bark", "url": "https://api.day.app/key", "sound": "bell"},
        {"type": "telegram", "bot_token": "123:ABC", "chat_id": "999"},
        {"type": "webhook", "url": "https://example.com/hook"},
    ]
    with TestClient(app) as client:
        resp = _put(client, {"notifications": {"enabled": True, "providers": providers}})

    assert resp.json()["code"] == 0
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["notifications"]["enabled"] is True
    assert written["notifications"]["providers"] == providers


# ---------------- 环境变量接管 ----------------


def test_env_overridden_keys_are_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUYIN_THREAD", "16")
    app, _ = _build(tmp_path)
    with TestClient(app) as client:
        data = client.get("/api/v1/settings").json()["data"]

    assert data["env_overrides"] == {"thread": "DOUYIN_THREAD"}


def test_env_overridden_key_rejects_update(tmp_path, monkeypatch):
    """env 优先级高于配置文件，改了也会被覆盖——拒绝而非假装保存成功。"""
    monkeypatch.setenv("DOUYIN_PATH", str(tmp_path / "from-env"))
    app, _ = _build(tmp_path)
    with TestClient(app) as client:
        resp = _put(client, {"path": str(tmp_path / "from-ui")})

    assert resp.status_code == 400
    assert "DOUYIN_PATH" in resp.json()["message"]


def test_env_override_does_not_block_other_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUYIN_PROXY", "http://127.0.0.1:7890")
    app, _ = _build(tmp_path)
    with TestClient(app) as client:
        assert _put(client, {"cover": True}).json()["code"] == 0


def test_no_env_overrides_by_default(tmp_path, monkeypatch):
    for var in ("DOUYIN_PATH", "DOUYIN_THREAD", "DOUYIN_PROXY"):
        monkeypatch.delenv(var, raising=False)
    app, _ = _build(tmp_path)
    with TestClient(app) as client:
        data = client.get("/api/v1/settings").json()["data"]

    assert data["env_overrides"] == {}


def test_settings_without_config_path_reports_not_saved(tmp_path):
    """内存态运行（ConfigLoader(None)）时改动仍生效，但如实报告未落盘。"""
    config = ConfigLoader(None)
    config.update(path=str(tmp_path), database=False)
    app = build_app(config)

    with TestClient(app) as client:
        data = _put(client, {"cover": True}).json()["data"]

    assert data["saved"] is False
    assert data["values"]["cover"] is True
    assert data["config_path"] is None
