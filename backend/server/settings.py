"""设置服务：读取 / 校验 / 热应用 / 持久化 UI 可编辑配置。

分层职责：路由（`server/api/settings.py`）只做请求解包与响应包装，本模块
负责「哪些键可改、值合不合法、改完怎么让它生效」。

**生效模型**（决定了前端要不要提示「重启后生效」）：

- *立即生效*：绝大多数键在每次下载时才从 ConfigLoader 实例读取，改内存即生效。
- *热应用*：`path` / `rate_limit` / `retry_times` 被启动时构造的组件持有，但都
  只是普通属性且每次调用重读，可安全改写（见 `_apply_runtime`）。
- *需重启*：`thread` 被烧进 `asyncio.Semaphore`（QueueManager 与 JobManager 各
  一份）。在途任务正持有信号量，替换会让并发计数错乱，故不热改，交由前端提示。
"""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from server.schemas import ALLOWED_VIDEO_QUALITIES, CODE_INVALID_PARAM, ApiError
from utils.logger import setup_logger

logger = setup_logger("Settings")

# 改这些键需要重启服务才能生效，随响应返回给前端做提示。
REQUIRES_RESTART = ("thread",)

# 环境变量在 ConfigLoader._load_config 里**后于**配置文件合并，优先级更高。
# 这些键被对应环境变量接管时，写进 config.yml 也会在重启后被重新覆盖 ——
# 那是「保存成功却不生效」的陷阱，故直接拒绝修改并让前端禁用编辑。
ENV_OVERRIDES = {
    "path": "DOUYIN_PATH",
    "thread": "DOUYIN_THREAD",
    "proxy": "DOUYIN_PROXY",
}


def _active_env_overrides() -> Dict[str, str]:
    """当前实际生效的环境变量接管关系：{配置键: 环境变量名}。"""
    return {key: env for key, env in ENV_OVERRIDES.items() if os.getenv(env)}

# 作者目录命名方式，与 config.example.yml 的 author_dir 注释保持一致。
ALLOWED_AUTHOR_DIR = frozenset({"nickname", "sec_uid", "nickname_uid"})

# 通知渠道类型，与 utils/notifier.py 支持的 provider 对齐。
ALLOWED_NOTIFY_TYPES = frozenset({"bark", "telegram", "webhook"})


def _invalid(message: str) -> ApiError:
    return ApiError(400, CODE_INVALID_PARAM, message)


def _as_bool(key: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise _invalid(f"{key} 必须是布尔值")
    return value


def _as_int(key: str, value: Any, *, minimum: int, maximum: int) -> int:
    # 显式排除 bool：Python 里 bool 是 int 的子类，True 会被当成 1 混过去。
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid(f"{key} 必须是整数")
    if not minimum <= value <= maximum:
        raise _invalid(f"{key} 需在 {minimum}~{maximum} 之间")
    return value


def _as_float(key: str, value: Any, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(f"{key} 必须是数字")
    number = float(value)
    if not minimum <= number <= maximum:
        raise _invalid(f"{key} 需在 {minimum}~{maximum} 之间")
    return number


def _as_str(key: str, value: Any, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise _invalid(f"{key} 必须是字符串")
    text = value.strip()
    if not text and not allow_empty:
        raise _invalid(f"{key} 不能为空")
    return text


def _as_choice(key: str, value: Any, allowed: Any) -> str:
    text = _as_str(key, value, allow_empty=False).lower()
    if text not in allowed:
        raise _invalid(f"{key} 只能是：{', '.join(sorted(allowed))}")
    return text


def _as_template(key: str, value: Any) -> str:
    """命名模板必须含 {id}，否则同作者下重名作品会互相覆盖。"""
    text = _as_str(key, value, allow_empty=False)
    if "{id}" not in text:
        raise _invalid(f"{key} 必须包含 {{id}} 占位符，否则重名作品会互相覆盖")
    return text


def _as_path(key: str, value: Any) -> str:
    return _as_str(key, value, allow_empty=False)


def _sub_model(
    key: str,
    value: Any,
    fields: Dict[str, Callable[[Any], Any]],
) -> Dict[str, Any]:
    """校验嵌套配置段（comments/live/notifications）。

    只接受 fields 中声明的子键；未提供的子键保持原值不动（ConfigLoader.update
    对 dict 做的是浅合并），因此前端可以只提交改动的那部分。
    """
    if not isinstance(value, dict):
        raise _invalid(f"{key} 必须是对象")
    cleaned: Dict[str, Any] = {}
    for sub_key, raw in value.items():
        validator = fields.get(sub_key)
        if validator is None:
            raise _invalid(f"{key}.{sub_key} 不是可配置项")
        cleaned[sub_key] = validator(raw)
    return cleaned


def _validate_notify_providers(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        raise _invalid("notifications.providers 必须是数组")
    cleaned: List[Dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _invalid(f"notifications.providers[{index}] 必须是对象")
        kind = _as_choice(f"notifications.providers[{index}].type", item.get("type"), ALLOWED_NOTIFY_TYPES)
        provider: Dict[str, Any] = {"type": kind}
        if kind == "telegram":
            provider["bot_token"] = _as_str(
                f"notifications.providers[{index}].bot_token", item.get("bot_token"), allow_empty=False
            )
            provider["chat_id"] = _as_str(
                f"notifications.providers[{index}].chat_id", item.get("chat_id"), allow_empty=False
            )
        else:
            # bark / webhook 都以 url 为必填主参数
            provider["url"] = _as_str(
                f"notifications.providers[{index}].url", item.get("url"), allow_empty=False
            )
            if kind == "bark" and item.get("sound"):
                provider["sound"] = _as_str(f"notifications.providers[{index}].sound", item["sound"])
        cleaned.append(provider)
    return cleaned


# 可配置键 → 校验器。这是**唯一**的白名单来源：不在表里的键一律拒绝，
# 避免前端误传把 cookies / link 等运行时或敏感值写进 config.yml。
#
# 注意与 ConfigLoader._UI_PERSISTED_KEYS 的关系：那里决定「save() 时写哪些键」，
# 这里决定「HTTP 层允许改哪些键」。两者需保持一致，author_dir 已同步补入。
_VALIDATORS: Dict[str, Callable[[Any], Any]] = {
    # 下载与存储
    "path": lambda v: _as_path("path", v),
    "video_quality": lambda v: _as_choice("video_quality", v, ALLOWED_VIDEO_QUALITIES),
    "thread": lambda v: _as_int("thread", v, minimum=1, maximum=32),
    "rate_limit": lambda v: _as_float("rate_limit", v, minimum=0.1, maximum=20.0),
    "retry_times": lambda v: _as_int("retry_times", v, minimum=0, maximum=10),
    "proxy": lambda v: _as_str("proxy", v),
    # 保存内容
    "video": lambda v: _as_bool("video", v),
    "cover": lambda v: _as_bool("cover", v),
    "music": lambda v: _as_bool("music", v),
    "avatar": lambda v: _as_bool("avatar", v),
    "json": lambda v: _as_bool("json", v),
    "download_pinned": lambda v: _as_bool("download_pinned", v),
    "homepage_screenshot": lambda v: _as_bool("homepage_screenshot", v),
    # 命名与目录
    "folderstyle": lambda v: _as_bool("folderstyle", v),
    "author_dir": lambda v: _as_choice("author_dir", v, ALLOWED_AUTHOR_DIR),
    "filename_template": lambda v: _as_template("filename_template", v),
    "folder_template": lambda v: _as_template("folder_template", v),
    # 嵌套段
    "comments": lambda v: _sub_model(
        "comments",
        v,
        {
            "enabled": lambda x: _as_bool("comments.enabled", x),
            "include_replies": lambda x: _as_bool("comments.include_replies", x),
            "max_comments": lambda x: _as_int("comments.max_comments", x, minimum=0, maximum=100000),
            "page_size": lambda x: _as_int("comments.page_size", x, minimum=1, maximum=50),
        },
    ),
    "live": lambda v: _sub_model(
        "live",
        v,
        {
            "max_duration_seconds": lambda x: _as_int(
                "live.max_duration_seconds", x, minimum=0, maximum=86400
            ),
            "chunk_size": lambda x: _as_int("live.chunk_size", x, minimum=1024, maximum=1048576),
            "idle_timeout_seconds": lambda x: _as_int(
                "live.idle_timeout_seconds", x, minimum=5, maximum=600
            ),
        },
    ),
    "notifications": lambda v: _sub_model(
        "notifications",
        v,
        {
            "enabled": lambda x: _as_bool("notifications.enabled", x),
            "on_success": lambda x: _as_bool("notifications.on_success", x),
            "on_failure": lambda x: _as_bool("notifications.on_failure", x),
            "providers": _validate_notify_providers,
        },
    ),
}

EDITABLE_KEYS: Tuple[str, ...] = tuple(_VALIDATORS)

def read_settings(config: Any) -> Dict[str, Any]:
    """当前生效配置的快照（仅可编辑键）。"""
    values: Dict[str, Any] = {}
    for key in EDITABLE_KEYS:
        value = config.get(key)
        values[key] = deepcopy(value) if isinstance(value, (dict, list)) else value
    return {
        "values": values,
        "config_path": str(config.config_path) if getattr(config, "config_path", None) else None,
        "requires_restart_keys": list(REQUIRES_RESTART),
        "env_overrides": _active_env_overrides(),
    }


def _apply_runtime(deps: Any, patch: Dict[str, Any]) -> None:
    """把已落到 config 的改动同步给启动时构造的运行时组件。

    只改普通属性，不重建对象——重建会让在途任务持有的旧实例与新实例并存。
    `thread` 有意不在此处理，见模块 docstring。
    """
    if "path" in patch:
        try:
            base = Path(patch["path"])
            base.mkdir(parents=True, exist_ok=True)
            deps.file_manager.base_path = base
        except OSError as exc:
            raise _invalid(f"下载目录不可用：{exc}")

    if "rate_limit" in patch:
        limiter = deps.rate_limiter
        limiter.max_per_second = patch["rate_limit"]
        # min_interval 是构造时从 max_per_second 派生的，必须同步改写
        limiter.min_interval = 1.0 / patch["rate_limit"]

    if "retry_times" in patch:
        deps.retry_handler.max_retries = patch["retry_times"]


def update_settings(config: Any, deps: Any, patch: Dict[str, Any]) -> Dict[str, Any]:
    """校验 → 写内存 → 热应用 → 落盘。

    返回更新后的快照，并附 `saved`（是否写入了文件）与 `restart_required`
    （本次改动中需要重启才生效的键）。
    """
    if not isinstance(patch, dict) or not patch:
        raise _invalid("请求体必须是非空对象")

    unknown = [key for key in patch if key not in _VALIDATORS]
    if unknown:
        raise _invalid(f"不可配置的键：{', '.join(sorted(unknown))}")

    env_taken = _active_env_overrides()
    blocked = sorted(key for key in patch if key in env_taken)
    if blocked:
        detail = "、".join(f"{key}（{env_taken[key]}）" for key in blocked)
        raise _invalid(
            f"{detail} 由环境变量接管，改动会在重启后被覆盖；"
            "请改环境变量本身，或取消设置后再回来改。"
        )

    cleaned = {key: _VALIDATORS[key](value) for key, value in patch.items()}

    changed_restart_keys = [
        key for key in REQUIRES_RESTART if key in cleaned and cleaned[key] != config.get(key)
    ]

    config.update(**cleaned)
    _apply_runtime(deps, cleaned)
    saved = config.save()
    if not saved:
        # 没有 config_path 时属预期（内存态运行）；写失败则 ConfigLoader 已记日志
        logger.warning("settings_not_persisted: config_path=%r", getattr(config, "config_path", None))

    return {
        **read_settings(config),
        "saved": saved,
        "restart_required": changed_restart_keys,
    }
