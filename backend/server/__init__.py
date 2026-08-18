"""REST API 服务模式（可选）。

依赖：fastapi, uvicorn（可选 extra：`uv sync --extra server`）

用法：
    douyin-dl --serve --serve-host 127.0.0.1 --serve-port 8000

分层：server.api（路由，/api/v1 前缀）→ server.jobs / server.works /
server.auth_flow / server.deps（服务）→ storage（存储）。
响应统一为 {"code", "message", "data"}，成功 code=0；码表见 server.schemas。
"""
