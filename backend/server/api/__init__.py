"""路由层：按域拆分的 APIRouter，统一挂载在 /api/v1 前缀下。

各路由只做参数校验与响应包装，业务委托给 Service 层
（server.jobs / server.works / server.auth_flow / server.deps）。
"""

from fastapi import APIRouter

from server.api import auth, download, jobs, system, works

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(download.router)
api_router.include_router(works.router)
api_router.include_router(jobs.router)
api_router.include_router(auth.router)
