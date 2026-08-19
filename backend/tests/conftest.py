"""测试共享装置。

下载端点自 feat/preflight-checks 起做凭据前置校验（见 server/preflight.py），
凡是期望「提交成功」的用例都需要先让 app 处于凭据齐全状态。
"""

from typing import Any, Dict

from tools.cookie_fetcher import REQUIRED_KEYS

# 必需键齐全的假 cookie：只用于通过前置校验，不触达真实上游
READY_COOKIES: Dict[str, str] = {key: f"test-{key}" for key in sorted(REQUIRED_KEYS)}


def mark_credentials_ready(app: Any) -> None:
    """让 app 通过下载端点的凭据前置校验。"""
    app.state.deps.cookie_manager.cookies = dict(READY_COOKIES)
