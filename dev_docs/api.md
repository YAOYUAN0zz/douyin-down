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
| 50300 | 503 | 数据库未启用（`config.database=false`），历史类端点不可用 |

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

`items[]` 字段见 `frontend/src/api/types.ts` 的 `WorkItem`（封面/描述/统计/话题/音乐/逐档画质 `qualities[]` 等）。每项附带 `downloaded: boolean`（历史库去重命中，数据库关闭时恒为 `false`），前端据此显示「已下载」角标。

### 任务

| Method | Path | 说明 / data |
|---|---|---|
| GET | `/jobs?status=&page=&page_size=` | `{jobs: JobDto[], total, page, page_size}`；服务端按创建时间倒序。`status` ∈ all/active/pending/running/success/partial/failed/cancelled（默认 all）；`page_size=0` 表示不分页 |
| GET | `/jobs/events?limit=` | **SSE**：持续推送 `data: {"jobs": [...]}` 帧，有活动任务每 1s、空闲每 10s；`limit>0` 推送 N 次后结束（调试用） |
| GET | `/jobs/{job_id}` | `JobDto`（含 `progress`：step/detail/items 计数/字节级 current/output_dir/author） |
| POST | `/jobs/{job_id}/cancel` | 取消 in-flight 任务 → 更新后的 JobDto；已结束 → 409/40900 |
| POST | `/jobs/{job_id}/retry` | 以原 URL+参数重建新任务 → 新 JobDto；未结束 → 409 |
| DELETE | `/jobs/{job_id}` | 删除已结束任务（内存+数据库）→ `{deleted: job_id}`；进行中 → 409 |
| POST | `/jobs/clear` | 清空全部已结束任务 → `{deleted: N}` |

任务状态机：`pending → running → success / partial / failed / cancelled`（partial=部分条目失败）。终态任务持久化到 SQLite（`config.database` 开启时，默认开启），服务重启后自动恢复；下载去重/历史与 CLI 对齐启用。

### 历史记录

| Method | Path | 说明 / data |
|---|---|---|
| GET | `/history?query=&author=&aweme_type=&author_sec_uid=&job_id=&sort=&page=&page_size=` | `{items: HistoryItem[], total, page, page_size}`。`query` 为标题子串（大小写不敏感），`author` 为作者名子串，`author_sec_uid`/`job_id` 精确匹配；`aweme_type` ∈ video/gallery/music/live_replay；`sort` ∈ `download_time`（默认，下载时间倒序）/`create_time`（发布时间倒序）；`page_size` 取值 1~100（默认 20） |
| GET | `/history/stats?limit=` | `{total, top_authors_7d[], top_authors_30d[]}`，作者项为 `{sec_uid, author_name, download_count}`；`limit` 取值 1~50（默认 10） |
| GET | `/history/{aweme_id}` | 单条详情，在列表字段基础上附 `metadata`（下载时捕获的完整作品 JSON，解析失败为 `null`）；不存在 → 404/40400 |

`HistoryItem`：`{aweme_id, aweme_type, title, author_id, author_name, author_sec_uid, create_time, download_time, file_path, cover_urls[], job_id}`。时间为 unix 秒，`file_path` 为落盘目录。数据来源是下载成功后写入的 `aweme` 表，只统计有落盘产物（`file_path` 非空）的记录；`config.database=false` 时三个端点均返回 503/50300。

### 下载参数（auth）

| Method | Path | 说明 |
|---|---|---|
| GET | `/auth/status` | `{cookie_count, required[], missing[], ready, has_session}` |
| POST | `/auth/fetch` | 启动服务器端浏览器登录抓取；已有会话 → 409/40900 |
| GET | `/auth/fetch/status` | `{status: idle\|running\|success\|failed\|cancelled, message, missing[], captured_count, started_at, finished_at}` |
| POST | `/auth/fetch/confirm` | 声明已完成登录，立即抓取；无会话 → 409 |
| POST | `/auth/fetch/cancel` | 取消会话；无会话 → 409 |

### 设置（settings）

| Method | Path | 请求 | data |
|---|---|---|---|
| GET | `/settings` | — | `{values, config_path, requires_restart_keys[], env_overrides}` |
| PUT | `/settings` | 局部补丁，只带改动的键 | 同上 + `{saved, restart_required[]}` |

- **白名单**：可改的键集中定义在 `backend/server/settings.py` 的 `_VALIDATORS`，同时也是校验规则的唯一来源。`cookies` / `link` / `database` 等运行时或敏感键**不可**经此端点修改 → 400/40000。
- **局部更新**：未提交的键保持原值；嵌套段（`comments` / `live` / `notifications`）做浅合并，可只带改动的子键。
- **原子性**：任一键校验失败则整个请求不落地，不会改一半。
- **落盘**：写回 `config.yml`（`ConfigLoader.save()`，保留用户手写的其他键）。`saved=false` 表示服务运行在无配置文件的内存态，改动仅本次运行有效。
- **环境变量接管**：`DOUYIN_PATH` / `DOUYIN_THREAD` / `DOUYIN_PROXY` 在 `ConfigLoader._load_config` 里**后于**配置文件合并，优先级更高。被设置时对应键写进 `config.yml` 也会在重启后被覆盖，因此 PUT 直接拒绝（400/40000），GET 通过 `env_overrides`（`{配置键: 环境变量名}`）告知前端禁用这些字段。
- **生效时机**：
  - 立即生效——画质、保存开关、命名模板、代理、评论/直播/通知等（下载时才读配置）；
  - 热应用——`path`、`rate_limit`、`retry_times`（同步改写已构造的 FileManager / RateLimiter / RetryHandler）；
  - **需重启**——`thread`（已烧进 `asyncio.Semaphore`，在途任务持有，不热改）。改动它时 `restart_required` 会带上该键，前端据此提示。

## 规划中的端点（见 `webui-redesign-report.md` §5）

M3 剩余：`/resolve`；M4 剩余：server 侧通知派发与 `/notifications/test`。（发现/直播录制已按用户决定砍掉，不做 Web 化。）
