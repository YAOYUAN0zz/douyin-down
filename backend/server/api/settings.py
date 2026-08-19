"""设置端点：读取与修改 UI 可编辑配置，免去用户手改 config.yml。"""

from typing import Any, Dict

from fastapi import APIRouter, Request

from server.schemas import ok
from server.settings import read_settings, update_settings

router = APIRouter(tags=["settings"])


@router.get("/settings")
async def get_settings(request: Request) -> Dict[str, Any]:
    return ok(read_settings(request.app.state.deps.config))


@router.put("/settings")
async def put_settings(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """局部更新：只提交改动的键即可，未提交的保持原值。

    有意收 `Dict` 而非 pydantic 模型——可配置键的白名单与校验规则集中在
    server.settings._VALIDATORS，避免在两处重复维护同一份字段清单。
    """
    deps = request.app.state.deps
    return ok(update_settings(deps.config, deps, payload))
