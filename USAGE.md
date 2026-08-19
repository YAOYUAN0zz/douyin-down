# USAGE — 面向 AI Agent 的操作说明

> 本文给**接手这个仓库并代替用户操作它**的 Agent 看：怎么装、怎么跑、怎么用、出错怎么办。
> 要**改这个项目的代码**，读 `AGENTS.md`（架构、设计模式、测试规范）与各子目录的 `AGENTS.md`。
> 面向人类的完整说明在 `README.zh-CN.md` / `README.md`。

## 1. 这是什么

抖音批量下载器，一个仓库两种形态，共用同一套下载内核：

| 形态 | 入口 | 适用 |
|---|---|---|
| **CLI** | `douyin-dl` | 批量、脚本化、定时任务 |
| **Web UI + REST API** | `douyin-dl --serve` → 浏览器 | 交互式操作、给非技术用户用 |

技术栈：Python 3.9+ 后端（uv 管理，FastAPI 服务模式）+ Vue 3 前端（pnpm 管理）。monorepo：`backend/` + `frontend/`。

## 2. 硬约束（先读这节，最容易踩）

1. **一切命令在仓库根目录执行**，不要 `cd backend` 后再跑下载命令。
   `config.yml`、`Downloaded/`、`dy_downloader.db`、`.cookies.json` 全是**相对 CWD** 解析的；换了 CWD 会读不到配置、把文件下载到别处。
   统一用 `uv run --project backend <命令>` —— `--project` 指定依赖环境，CWD 保持在根目录。
2. **Python 依赖只用 uv，前端只用 pnpm**。不要 `pip install`、不要 `npm install`。
3. **不要提交也不要外发这些文件**：`config.yml`、`.cookies.json`、`dy_downloader.db*`、`Downloaded/`、`.env.dev` —— 含用户的抖音登录凭据和下载数据。`.gitignore` 已排除，但**打包/复制目录时会连带带走**，务必先确认。
4. **Cookie 会失效**。抖音接口对未登录/失效态返回的错误五花八门；报错先怀疑 Cookie，见 §7。
5. **接口会变**。这是逆向抖音私有接口的项目，某天突然全部失败是常态，不一定是本地环境问题。

## 3. 首次配置（4 步）

```bash
# 1) 安装后端依赖（server extra = Web UI/REST 所需的 fastapi+uvicorn）
uv sync --project backend --extra server

# 2) 生成配置
cp config.example.yml config.yml        # Windows: Copy-Item config.example.yml config.yml

# 3) 获取 Cookie（推荐：打开浏览器，手动登录后自动写入）
uv run --project backend python -m tools.cookie_fetcher --config config.yml

# 4) 编辑 config.yml，至少改 link / mode / number 三项
```

**可选 extra**（按需追加，不要默认全装）：

| extra | 装什么 | 何时需要 |
|---|---|---|
| `server` | fastapi + uvicorn | Web UI / REST 模式（几乎总是要） |
| `browser` | playwright | 自动抓 Cookie、超过 20 条作品的浏览器兜底翻页 |
| `transcribe` | openai-whisper | 视频转写 |
| `dev` | pytest + ruff + hypothesis | 改代码 / 跑测试 |

装 `browser` 后还需下载浏览器内核：

```bash
uv sync --project backend --extra server --extra browser
uv run --project backend python -m playwright install chromium
```

Cookie 持久化在 `.cookies.json`（与 `config.yml` 同级）。`config.yml` 里的 `cookies:` 段**只在首次、尚无 `.cookies.json` 时**作为种子导入，之后以 `.cookies.json` 为准 —— 所以改 `config.yml` 里的 cookie 通常不生效，要改就改 `.cookies.json` 或重新跑 cookie_fetcher。

## 4. 运行

### Web UI（推荐给最终用户）

```bash
./start-dev.sh          # macOS / Linux / Git Bash
./start-dev.ps1         # Windows PowerShell
```

脚本做的事：读 `.env.dev`（不存在则从 `.env.dev.example` 复制）→ 探测端口，**被占用就 +1 递增并回写** → 起后端 → 起前端 Vite。终端会打印实际地址，**不要假定是 8000/5173**。

生产形态（前端构建为静态资源，由后端单进程托管）：

```bash
./start-prod.sh         # 默认监听 0.0.0.0:8000，可用 .env.prod 覆盖
```

不想用脚本时，服务模式的裸命令：

```bash
uv run --project backend douyin-dl --serve --serve-host 127.0.0.1 --serve-port 8000
```

### CLI

```bash
# 按 config.yml 批量跑
uv run --project backend douyin-dl -c config.yml

# 命令行覆盖：追加链接、改并发、改目录
uv run --project backend douyin-dl -c config.yml \
  -u "https://www.douyin.com/video/7604129988555574538" -t 8 -p ./Downloaded
```

| 参数 | 说明 |
|---|---|
| `-u, --url` | 追加下载链接，可重复传 |
| `-c, --config` | 配置文件路径，默认 `config.yml` |
| `-p, --path` | 下载根目录 |
| `-t, --thread` | 并发数 |
| `--serve` / `--serve-host` / `--serve-port` | REST + Web UI 服务模式 |
| `--hot-board [N]` | 导出热搜榜快照 |
| `--search <kw>` / `--search-max <N>` | 关键词搜索 |
| `-v, --verbose` / `--show-warnings` | 放开日志级别（**排查问题时先加这个**） |

## 5. 常用任务配方

改 `config.yml` 的 `link` + `mode` + `number` 三项组合即可，`number` 中 `0` = 不限量：

| 目标 | link 填 | mode | number |
|---|---|---|---|
| 单个视频 / 图文 | 作品链接 | `post` | — |
| 博主全部作品 | 主页 `/user/MS4w...` | `post` | `post: 0` |
| 博主点赞 | 主页链接 | `like` | `like: 0` |
| 合集 | 合集链接 | `mix` | `mix: 0` |
| 音乐同款 | 音乐链接 | `music` | `music: 0` |
| 自己的收藏 | 任意已登录账号链接 | `collect` | `collect: 0` |
| 直播录制 | `live.douyin.com/{room_id}` | — | 见 `live:` 段 |

**增量下载**（只抓新作品，跑定时任务必开）：`increase.post: true`，配合 `database: true`。

## 6. 关键配置项

| 键 | 作用 | 提醒 |
|---|---|---|
| `video_quality` | `original` / `highest`(默认) / `lowest` / `1080p` 等 | `original` 每条多一次探测请求（10s 超时），慢但可能拿到远大于转码档的原片 |
| `thread` | 并发数，默认 5 | 调高易触发风控，出现大量失败先调回 5 |
| `path` | 下载根目录，默认 `./Downloaded/` | 相对 CWD |
| `database` / `database_path` | SQLite 历史库，默认开 | 关掉则增量下载和「已下载」标记失效 |
| `filename_template` / `folder_template` | 命名模板 | **必须含 `{id}`**，否则重名互相覆盖 |
| `author_dir` | `nickname`(默认) / `sec_uid` / `nickname_uid` | 改了只影响后续下载，不迁移旧目录 |
| `download_pinned` | 是否含置顶作品，默认 `false` | — |
| `proxy` | 代理地址 | 空字符串 = 不走代理 |
| `comments.enabled` | 采集评论到 `*_comments.json` | 默认关 |
| `notifications` | 完成通知，支持 bark / telegram / webhook | 默认关 |

## 7. 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| 全部作品下载失败、报登录相关错误 | Cookie 失效。重跑 `uv run --project backend python -m tools.cookie_fetcher --config config.yml`，或在 Web UI 点「自动获取参数」 |
| 只抓到 20 条就停 | 抖音接口翻页限制。装 `browser` extra 并保持 `browser_fallback.enabled: true` 走浏览器兜底 |
| `os error 32` / 启动时提示残留 `douyin-dl` 进程（Windows） | 上次的后端没退干净，占着 `.venv\Scripts\douyin-dl.exe`。执行 `taskkill /F /IM douyin-dl.exe` 后重试 |
| 端口被占 / 启动失败 | `start-dev` 会自动 +1 避让并回写 `.env.dev`；看终端打印的实际端口，别用记忆中的端口 |
| uv 报虚拟环境不匹配的告警 | 外层激活了别的 venv。`unset VIRTUAL_ENV`（PowerShell: `$env:VIRTUAL_ENV = $null`），启动脚本已内置此处理 |
| 没生成转写文件 | `transcript.enabled` 未开，或 `OPENAI_API_KEY` 未设置 |
| 历史/统计类接口报 503 | `config.database` 被关了，历史类端点依赖数据库 |
| 想看详细报错 | CLI 加 `-v`；Web UI 看后端终端输出 |

**重新下载**：历史库会去重，想重下就从 `dy_downloader.db` 删对应记录，或临时 `database: false`。

## 8. REST API

服务模式下前缀 `/api/v1`，统一响应体 `{code, message, data}`，成功 `code=0`。完整端点清单、业务码表、SSE 进度推送格式见 **`dev_docs/api.md`** —— 改接口时该文档与 `frontend/src/api/types.ts` 必须同步更新。

常用：`GET /health`、`POST /download`、`POST /download/batch`、`POST /works/list`、`GET /jobs`、`GET /jobs/events`(SSE)、`GET /api/v1/auth/status`。

## 9. 改代码时

```bash
uv run --project backend pytest          # 后端测试
uv run --project backend ruff check .    # 后端 lint（line-length 100）
cd frontend && pnpm check                # 前端：prettier + eslint + vue-tsc
```

约束：Python 保持 3.9 兼容；核心路径全异步（`aiohttp`/`aiofiles`/`aiosqlite`），禁阻塞 I/O；日志走 `utils.logger.setup_logger(name)`，禁 `print`。详见 `AGENTS.md`。

## 10. 不要做的事

- 不要把本地工作目录直接打包发给别人（会带走 Cookie 和下载数据，见 §2.3）
- 不要为了「跑得快」把 `thread` 调到两位数 —— 触发风控后反而全失败
- 不要绕过 `uv` / `pnpm` 直接装依赖
- 不要在未确认的情况下断言「接口坏了」或「代码有 bug」：先 `-v` 看日志，再验 Cookie，最后才怀疑代码
- 本项目仅供技术研究与个人数据管理，不要用它做批量爬取分发等越界用途
