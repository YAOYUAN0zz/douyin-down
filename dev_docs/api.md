# API 对接文档

> 前后端共用的接口契约。后端定义：`backend/server/api/`（路由）+ `backend/server/schemas.py`（请求模型与码表）；前端消费：`frontend/src/api/`。改动端点时**必须**同步更新本文档与前端类型。

## 统一响应模型

所有端点返回同一包装（禁混用）：

```json
{ "code": 0, "message": "ok", "data": { } }
```

- 成功：`code=0`，`message="ok"`，业务负载在 `data`
- 失败：`data=null`，`code` 为业务码，`message` 为可展示的中文错误信息
- HTTP 状态码保持传输层语义（400/401/404/409/422/5xx），与业务码语义一致

## 业务码表（`backend/server/schemas.py`）

| code | HTTP | 含义 |
|---|---|---|
| 0 | 200 | 成功 |
| 40000 | 400 | 通用参数错误（缺 url 等） |
| 40001 | 400 | 画质参数不在白名单 |
| 40002 | 400 | 批量提交超上限（100） |
| 40100 | 401 | 登录态失效/未登录（前端收到后弹全局「重新登录」横幅） |
| 40400 | 404 | 资源不存在（job 等） |
| 40900 | 409 | 状态冲突（auth 会话已存在/不存在） |
| 42200 | 422 | 请求体校验失败 |
| 50000 | 500 | 未分类服务端错误 |
| 50200 | 502 | 抖音上游接口异常（上游其他状态 N 映射为 N×100） |

## 端点清单（前缀 `/api/v1`）

### 系统

| Method | Path | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 → `data: {status: "ok"}` |

### 下载

| Method | Path | 请求 | data |
|---|---|---|---|
| POST | `/download` | `{url, video_quality?}` | `{job_id, status, url}` |
| POST | `/download/batch` | `{urls[], video_quality?}`（≤100） | `{jobs: [{job_id, status, url}]}` |

`video_quality` 白名单：`original / highest / lowest / 1440p / 1080p / 720p / 540p / 480p / 360p`，空表示跟随全局配置。

### 作品列表

| Method | Path | 请求 | data |
|---|---|---|---|
| POST | `/works/list` | `{url, cursor=0, count=20}`（count≤50） | `{source_type, items[], has_more, cursor}` |

`items[]` 字段见 `frontend/src/api/types.ts` 的 `WorkItem`（封面/描述/统计/话题/音乐/逐档画质 `qualities[]` 等）。

### 任务

| Method | Path | data |
|---|---|---|
| GET | `/jobs` | `{jobs: JobDto[]}`（未分页；分页/筛选属 M2） |
| GET | `/jobs/{job_id}` | `JobDto`（含 `progress`：step/detail/items 计数/字节级 current/output_dir/author） |

### 下载参数（auth）

| Method | Path | 说明 |
|---|---|---|
| GET | `/auth/status` | `{cookie_count, required[], missing[], ready, has_session}` |
| POST | `/auth/fetch` | 启动服务器端浏览器登录抓取；已有会话 → 409/40900 |
| GET | `/auth/fetch/status` | `{status: idle\|running\|success\|failed\|cancelled, message, missing[], captured_count, started_at, finished_at}` |
| POST | `/auth/fetch/confirm` | 声明已完成登录，立即抓取；无会话 → 409 |
| POST | `/auth/fetch/cancel` | 取消会话；无会话 → 409 |

## 规划中的端点（见 `webui-redesign-report.md` §5）

M2：jobs 取消/重试/删除/清空、分页筛选、SSE `/jobs/events`；M3：`GET/PUT /settings`、`/resolve`；M4：`/history*`、通知测试。（发现/直播录制已按用户决定砍掉，不做 Web 化。）
