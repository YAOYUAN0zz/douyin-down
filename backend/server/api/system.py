"""系统类端点：健康检查。"""

from typing import Any, Dict

from fastapi import APIRouter

from server.schemas import ok

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> Dict[str, Any]:
    return ok({"status": "ok"})
