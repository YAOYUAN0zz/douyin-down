# Web UI 重设计报告（douyin-downloader）

> 版本：v2（2026-08-18）　分支：`feat/web-ui-auto-fetch-params`
> 目的：基于对现有 Web UI、后端 API 与核心能力的完整调研，提出一套「方便用户使用、功能覆盖详细」的新 UI 设计方案，作为后续改造的依据。
>
> **v2 修订（用户已拍板）**：① 项目转为前后端 monorepo 结构，新增 §6 目标文件夹架构；② 全部端点（存量 + 新增）统一到同一套响应模型与错误码规范（§5）。
> **v3 修订**：本项目为从 GitHub clone 的第三方项目二次开发，**不存在**需要同步的桌面端仓库，已移除全部「与桌面端对齐」相关内容（项目 CLAUDE.md / AGENTS.md 中的对应记录亦已清除）。
> **v4 修订（实施记录）**：M0 与 M1 已落地。落地时对 §6 的一处调整：Python 包**平铺在 `backend/` 下且包名不变**（`backend/core/` 而非 `backend/douyin_downloader/core/`），避免全仓 import 与测试 mock-patch 字符串的大规模重写；其余按方案执行。API 规格见 `dev_docs/api.md`。

---

## 1. 背景与目标

当前 Web UI 是 `--serve` 模式下的单文件页面（`server/webui/index.html`，589 行，纯原生 HTML/CSS/JS），只覆盖了后端能力的一小部分：单链接下载、作品列表预览+批量下载、cookie 自动获取、任务进度表。而后端（CLI 同款核心）实际具备主页多模式批量、增量下载、时间过滤、直播录制、评论采集、热搜/搜索、转写、通知推送、SQLite 历史与去重等大量能力，均未在 UI 暴露。

**重设计目标**：

1. **能力对齐**：把后端已有能力尽可能通过 UI 暴露，让 Web 端接近 CLI 全功能。
2. **易用优先**：降低操作成本——粘贴即下、常用选项一眼可见、错误可读可行动。
3. **可持续演进**：摆脱单文件限制，建立可维护的前端结构与设计令牌体系。
4. **状态可信**：任务/历史持久化，页面刷新与服务重启不丢状态。

---

## 2. 现状调研摘要

### 2.1 技术栈与结构

- 前端：**唯一文件** `server/webui/index.html`（25.7 KB / 589 行），内联 style + 内联 ES5 script，无框架、无构建、无第三方依赖。
- 后端：FastAPI（可选依赖），`server/app.py`（296 行）承载全部 12 个路由；`GET /` 用 `FileResponse` 直接返回单 HTML，**未挂载 StaticFiles**，因此当前无法引入第二个静态资源文件（`server/app.py:245-251`）。
- 任务系统：`server/jobs.py` 纯内存 `JobManager`（上限 500、TTL 86400s），**服务重启全丢**；数据库在 server 路径被显式关闭（`server/app.py:176` 传 `None`）。

### 2.2 现有页面功能（单页 4 张卡片，920px 定宽）

| 卡片 | 功能 |
|---|---|
| 下载参数状态 | cookie 必需项 ✓/✗ 徽章、登录会话检测；「自动获取参数」启动服务端 Playwright 浏览器登录，2s 轮询流程状态 |
| 提交下载 | 单 URL 输入 + 画质下拉（10 档）+ 开始下载 |
| 作品列表（按需下载） | URL → 卡片流网格（封面/描述/统计/话题/音乐/逐档画质与文件大小）、复选+全选、画质选择、批量下载、cursor 加载更多 |
| 任务列表 | 四列表格：链接（画质 tag）/状态/进度/创建时间；running 显示条目计数 + 字节级进度条；2s 全量轮询 |

### 2.3 后端 API 现状（12 个端点）

`/`、`/api/v1/health`、`POST /download`、`POST /download/batch`（≤100 条）、`POST /works/list`（count≤50，401 带中文登录引导）、`GET /jobs/{id}`、`GET /jobs`（无分页无排序）、`GET /auth/status`、`POST /auth/fetch`、`GET /auth/fetch/status`、`POST /auth/fetch/confirm`、`POST /auth/fetch/cancel`。

### 2.4 现有 UI 主要痛点（代码可证）

**功能缺失**
- 任务不可取消/重试/删除/清空（后端也无对应端点）；无任务详情、无输出目录展示（后端 progress 已含 `output_dir`，前端未用，`server/jobs.py:49-57`）。
- 无设置页：`config_loader.py:159-180` 已有 `_UI_PERSISTED_KEYS` 白名单与 `save()`，但本仓库无 settings 端点，配置写回能力闲置。
- 无历史记录：`storage/database.py`（745 行）的 `get_aweme_history`（分页+搜索）、`get_top_authors`、job 持久化（`upsert_job/load_terminal_jobs`）全部闲置。
- 主页下载无法选模式（post/like/mix/music/collect/collectmix）、无数量上限/增量/时间过滤入口；无直播录制入口；无热搜/搜索；无附带产物开关（封面/音乐/头像/JSON）。

**交互与工程质量**
- 轮询永不停止（`setInterval` 2s，无 visibilitychange 暂停、无退避、无 SSE/WS）；轮询失败**完全静默**，服务挂了页面看似正常。
- 每 2s 整表/整网格 `innerHTML` 重建并重挂事件——卡片多时闪烁、丢滚动、封面重复请求。
- 错误只有 4 个固定消息位互相覆盖；job 失败展示原始 `LoginRequiredError: ...` 字符串，无「重新登录」联动。
- 状态机只有 4 态，无 partial（部分失败按 FAILED 记）；跳过数在 running 时不可见。
- 920px 定宽、无 `@media`、无暗色模式、无骨架屏、无键盘可达性（卡片选择是 div click，无 tabindex/role/aria-live）。
- 两处画质下拉选项完全复制粘贴（`index.html:143-154` 与 `173-184`），改一漏一。

### 2.5 后端已有但 UI 未暴露的能力（机会清单）

| 能力 | 所在模块 | UI 现状 |
|---|---|---|
| 主页六模式（post/like/mix/music/collect/collectmix） | `core/user_mode_registry.py` | 不可选 |
| 数量上限 `number.*`、增量 `increase.*` | config | 无 |
| 时间过滤 `start_time/end_time` | config | 无日期选择 |
| 附带产物 video/music/cover/avatar/json | config | 无开关 |
| 命名模板 filename/folder_template、author_dir、folderstyle、group_by_mode | config + `utils/naming.py` | 无 |
| 直播录制 live / live_replay | `core/downloader_factory.py:59-62` | 无入口、无停止 |
| 热搜榜 / 关键词搜索 | `core/discovery.py` | 无 API 无 UI |
| 评论采集 comments.* | `core/comments_collector.py` | 无 |
| 转写 transcript.* | `core/transcript_manager.py` | 无 |
| 通知推送 bark/telegram/webhook | `utils/notifier.py` | server 路径完全不派发 |
| SQLite 历史/去重/job 持久化 | `storage/database.py` | server 关闭 DB |
| 代理、并发、限速、重试、浏览器兜底 | config | 无 |

---

## 3. 设计原则

1. **粘贴即下**：首屏最重要动作是「粘贴链接 → 下载」，高级选项渐进展开，默认值来自配置。
2. **少下拉、多可见**：选项 ≤7 且需对比时用分段控件/单选/复选/开关，不用下拉（画质档 10 项保留下拉+搜索例外）。
3. **三态必备**：每个数据区域都有 loading（骨架屏）/ empty（空状态+引导动作）/ error（可读文案+重试按钮）。
4. **错误可行动**：401 登录失效 → 全局横幅 + 一键「重新登录」直达 auth 流程；失败任务 → 一键重试。
5. **状态可信**：任务与历史入库持久化；连接断开有全局离线提示，恢复后自动重连。
6. **设计令牌**：颜色/间距/圆角/字号全部走 CSS 变量，浅色为基线，`prefers-color-scheme` + 手动开关支持暗色。
7. **响应式**：桌面三栏内容区，≤768px 折叠为单列；表格在窄屏降级为卡片列表。

---

## 4. 信息架构

采用**左侧导航 + 内容区**的经典布局（窄屏折叠为顶部汉堡菜单）：

```
┌────────────┬──────────────────────────────────────────┐
│ Logo       │  全局状态条（登录状态 / 离线提示 / 活动任务数）│
│ ─────────  ├──────────────────────────────────────────┤
│ ⬇ 下载      │                                          │
│ 🗂 作品浏览  │              内容区                        │
│ 📋 任务中心  │                                          │
│ 🕘 历史记录  │                                          │
│ 🔍 发现     │                                          │
│ 📡 直播录制  │                                          │
│ ⚙ 设置     │                                          │
└────────────┴──────────────────────────────────────────┘
```

六个主页面 + 全局元素，逐一说明如下。

### 4.1 全局元素

- **顶部状态条**：
  - 登录状态胶囊：`已登录（N cookies）` / `未登录 → [自动获取参数]`。点击展开 cookie 必需项明细（现有徽章逻辑迁移至此）。
  - 活动任务徽标：`▶ 3 进行中`，点击跳任务中心。
  - 离线横幅：轮询/SSE 断连超过 5s 显示「与服务器连接中断，正在重连…」，恢复自动消失。
- **登录失效全局拦截**：任何 API 返回 401 → 顶部红色横幅「登录已失效」+ `[重新登录]` 按钮（触发 auth/fetch 流程弹窗）。
- **通知中心（toast 栈）**：右下角可堆叠 toast，错误类不自动消失、可复制详情；替代现有互相覆盖的 4 个消息位。
- **Auth 流程弹窗**：把现有「自动获取/我已完成登录/取消/状态轮询」收进一个模态对话框，任何页面可唤起；流程 running 时状态条持续显示。

### 4.2 页面一：下载（首页）

首屏核心工作台，两个区块：

**A. 快速下载区**
- 大号多行文本框：支持**一次粘贴多条链接**（换行/空格分隔，前端解析计数「识别到 N 条链接」），短链自动接受。
- 画质：下拉（10 档，默认「跟随配置」）——唯一保留的下拉，选项定义单一来源（常量模块），杜绝现在的两处复制。
- `[开始下载]` 主按钮 + 回车提交。
- **高级选项（默认折叠的 disclosure）**：
  - 附带产物：☑视频 ☑音乐 ☐封面 ☐头像 ☐JSON（复选组，默认取配置值）
  - 时间范围：起止日期选择器（对应 `start_time/end_time`）
  - 数量上限：数字输入（0=不限）
  - 增量下载：开关（仅链接为主页/合集时可用，否则禁用+说明）
- 链接类型即时识别：粘贴后异步探测并在链接旁打 tag（视频/图文/合集/音乐/主页/直播），主页链接旁出现「浏览作品列表 →」快捷跳转。

**B. 主页批量下载区**（当输入含主页链接时展开，或独立入口）
- 模式选择：**复选按钮组**（发布 post / 喜欢 like / 合集 mix / 音乐 music），收藏（collect/collectmix）单列一组并注明「仅当前登录账号，且不能与其他模式混用」——由控件互斥逻辑直接约束，而不是让用户读文档。
- 每模式数量上限 + 增量开关，随所选模式显示。

**C. 最近任务摘要**：区块底部显示最近 5 条任务（复用任务中心的行组件），带「查看全部 →」。

### 4.3 页面二：作品浏览（现「作品列表」升级）

保留并强化现有卡片流：

- URL 输入 + 获取列表；**主页链接增加模式分段控件**（发布/喜欢/合集/音乐），切换即重新拉取。
- 卡片流网格（现有信息密度已好，保留封面/统计/画质档/文件大小）新增：
  - 卡片右上角「已下载」角标（依赖历史库去重查询，见 §5）。
  - 悬停操作：单个下载（快捷）/ 复制链接 / 查看画质详情。
  - 付费作品标识（`utils/paid_content.py` 结果已可得）。
- 工具栏：全选/反选/仅选未下载、已选计数、画质选择、`[下载选中]`、筛选（类型：视频/图集；排序：时间/点赞）。
- 滚动加载（IntersectionObserver 替代「加载更多」按钮，保留按钮兜底）；**增量渲染**——新页只 append 节点，不整网格重建。
- 三态：骨架卡片 loading、空状态（「未获取到作品，检查链接或登录状态」+ 重试）、错误态带原因与重试。

### 4.4 页面三：任务中心

- 任务列表升级为**行卡片**（窄屏友好），字段：链接（可点开原页）、类型 tag、画质 tag、状态、进度（条目计数 + 当前文件字节进度条 + 当前步骤文案）、创建/完成时间（相对时间+悬停绝对时间）、**输出目录**（已有数据，补显示 + 复制路径按钮）。
- 状态机扩展：`pending / running / success / partial / failed / cancelled`——部分失败不再一律记 FAILED；跳过数常显。
- 行操作：`[取消]`（running）、`[重试]`（failed/partial，沿用原参数重建 job）、`[删除]`；顶部 `[清空已完成]`。
- 筛选分段控件：全部 / 进行中 / 成功 / 失败；后端支持 `?status=&page=` 分页。
- 任务详情抽屉：点击行展开——完整参数、逐条目结果（成功/失败/跳过明细与错误信息）、日志片段。
- **实时性**：优先 SSE（`GET /api/v1/jobs/events`），降级为智能轮询（有 running 任务 2s，空闲 10s，页面隐藏时暂停——`visibilitychange`）。
- **持久化**：打开 server 侧数据库，复用 `upsert_job/load_terminal_jobs`，重启后历史任务仍可见。

### 4.5 页面四：历史记录

全新页面，直接消费 `storage/database.py` 现成能力：

- 已下载作品列表：分页 + 关键词搜索（`get_aweme_history`）、按作者/类型/时间筛选。
- 行内动作：打开输出目录路径（复制）、重新下载、查看元数据 JSON。
- 侧栏统计卡：总下载数、近 7/30 天活跃作者 Top（`get_top_authors`）、按作者计数。

### 4.6 页面五：发现（热搜 + 搜索）

- 热搜榜 Tab：一键拉取 `--hot-board` 数据，表格（排名/词条/热度），词条可一键转搜索。
- 搜索 Tab：关键词 + 数量上限 → 结果以作品卡片流展示（复用作品浏览的卡片组件），可勾选批量下载。
- 需新增两个后端端点（见 §5）。

### 4.7 页面六：直播录制

- 输入 `live.douyin.com/{room_id}` 或主播主页链接 → 显示直播间状态（在播/未开播）。
- `[开始录制]` → 创建 live job，任务中心显示录制时长/已录字节，**带 `[停止录制]`**。
- 录制参数（最长时长、空闲超时）就地可调，默认取配置。
- 明确标注 HLS 源仅保存 playlist、需 ffmpeg 后处理（后端现状如实提示）。

### 4.8 页面七：设置

后端 `_UI_PERSISTED_KEYS` + `save()` 已就绪，只差端点。按分组渲染，**保存后热生效**（重建 config 快照）：

| 分组 | 控件 |
|---|---|
| 下载 | 保存路径（文本+说明）、默认画质（下拉）、并发 thread（数字/滑块）、限速 rate_limit、重试次数、代理 |
| 产物 | video/music/cover/avatar/json 复选组、download_pinned、homepage_screenshot 开关 |
| 命名 | filename_template / folder_template（输入框 + 可插入变量 chips + 实时预览）、author_dir 单选（nickname/sec_uid/nickname_uid）、folderstyle 开关 |
| 评论 | enabled 开关、include_replies、max_comments、page_size |
| 转写 | enabled、model、api_url、api_key（密码框，回显打码）、输出格式复选 |
| 通知 | enabled + on_success/on_failure 开关、providers 列表编辑（bark/telegram/webhook 三种模板表单）、`[发送测试通知]` |
| 直播 | max_duration_seconds、idle_timeout_seconds |
| 账号 | cookie 状态明细、`[自动获取参数]`、`[清除登录]` |

敏感字段（api_key、cookie 值）在 GET 响应中打码，只在用户显式修改时写回。

---

## 5. 后端配套改造（API 增补清单）

> **统一要求（硬约束）**：本仓库的**全部端点**——包括现有 12 个存量端点与下表所有新增端点——统一到同一套响应模型：`{code, message, data}`、成功 `code=0`、错误码集中定义并文档化，前后端共用码表。存量端点改造属破坏性变更，但本 UI 是唯一消费方，直接切换即可。API 规格随实现沉淀到 `dev_docs/api.md`。

| 优先级 | 端点 | 说明 |
|---|---|---|
| P0 | `GET /` 改为 StaticFiles 挂载 `server/webui/` | 解锁多文件前端（`server/app.py:245-251`） |
| P0 | `POST /api/v1/jobs/{id}/cancel`、`/retry`、`DELETE /api/v1/jobs/{id}`、`POST /api/v1/jobs/clear` | 任务操作 |
| P0 | `GET /api/v1/jobs?status=&page=&page_size=` | 分页/筛选/服务端排序 |
| P0 | server 打开数据库（改 `server/app.py:176`）+ job 持久化接线 | 历史/去重/重启不丢 |
| P0 | `GET/PUT /api/v1/settings` | 消费现成 `_UI_PERSISTED_KEYS` 白名单与 `save()`（`config/config_loader.py:159-251`） |
| P1 | `GET /api/v1/jobs/events`（SSE） | 实时进度推送，替代盲轮询 |
| P1 | `POST /api/v1/download` 请求体扩展 | `mode[]`、`number`、`increase`、`start_time/end_time`、产物开关（per-job override） |
| P1 | `GET /api/v1/history?query=&page=`、`GET /api/v1/history/stats` | 历史页 |
| P1 | `POST /api/v1/resolve` | 链接类型探测（返回 source_type，用于输入框即时 tag） |
| P2 | `GET /api/v1/discovery/hot-board`、`POST /api/v1/discovery/search` | 发现页（包装 `core/discovery.py`） |
| P2 | `POST /api/v1/live/record`、`POST /api/v1/live/{job_id}/stop`、`GET /api/v1/live/status?room=` | 直播录制 |
| P2 | server 路径接入 `_dispatch_notifications` | 任务完成推送与 CLI 对齐 |
| P2 | `POST /api/v1/notifications/test` | 设置页测试按钮 |

现有端点直接抛 HTTPException，改造时统一包一层；全项目只选这一种返回模型，禁混用。

## 6. 目标文件夹架构（前后端 monorepo）

项目从「根目录 Python 包 + 内嵌单文件 UI」转为标准前后端 monorepo（单产品强耦合前后端）。目标结构：

```
douyin-downloader/
├── backend/                        # Python 后端（uv 管理）
│   ├── douyin_downloader/          # 现根目录各包整体迁入
│   │   ├── auth/
│   │   ├── cli/
│   │   ├── config/
│   │   ├── control/
│   │   ├── core/
│   │   ├── storage/
│   │   ├── tools/
│   │   ├── utils/
│   │   └── server/                 # FastAPI，按分层重组：
│   │       ├── api/                #   路由层（routers，按域拆分：download/jobs/works/auth/settings/history/discovery/live）
│   │       ├── services/           #   Service 层（JobManager、auth_flow、works 预览等迁入）
│   │       ├── schemas/            #   Pydantic 请求/响应模型（统一响应包装与错误码定义处）
│   │       └── app.py              #   应用工厂：只做装配（中间件、StaticFiles、路由注册）
│   ├── tests/                      # 现 tests/ 迁入
│   ├── pyproject.toml              # 现根 pyproject 迁入并更新包路径
│   └── uv.lock
├── frontend/                       # Vite + Vue 3（pnpm 管理）
│   ├── src/
│   │   ├── api/                    # API client（与 schemas 对齐的 TS 类型 + 请求封装）
│   │   ├── components/             # 通用组件（toast、状态条、作品卡片、任务行…）
│   │   ├── pages/                  # 七个页面（download/works/jobs/history/discovery/live/settings）
│   │   ├── stores/                 # Pinia（auth、jobs、settings）
│   │   ├── styles/tokens.css       # 设计令牌（浅色基线 + 暗色覆盖）
│   │   └── utils/
│   ├── test/                       # vitest
│   ├── package.json / pnpm-lock.yaml
│   ├── vite.config.ts              # 构建输出 → frontend/dist（后端 StaticFiles 指向此处）
│   └── tsconfig.json               # strict，禁 any
├── dev_docs/
│   ├── webui-redesign-report.md    # 本文
│   └── api.md                      # API 对接文档（随端点实现同步更新）
├── docs/ img/                      # 现有资料保持
├── start-dev.sh / start-prod.sh    # 一键启动（端口固定+自动避让，前端经 VITE_API_PORT 读后端地址）
├── .env.dev / .env.prod（+ .example）
├── .editorconfig / .gitattributes  # UTF-8 + LF
├── Dockerfile                      # 多阶段：node 构建 frontend → python 运行时仅带 dist
└── README.md
```

迁移要点：

1. 现有各包（`auth/ cli/ config/ control/ core/ storage/ tools/ utils/` 及 tests）目录名不变，整体下移到 `backend/douyin_downloader/`，import 路径统一更新。
2. `server/` 从「三个大文件」重组为 路由 → Service →（storage 作 Repository）分层，每层只依赖下一层；`schemas/` 集中定义统一响应包装与错误码。
3. `run.py`、`requirements.txt`（pip 遗留）随迁移清理：入口统一 `uv run douyin-downloader`（pyproject scripts），依赖统一 uv 管理。
4. 旧 `server/webui/index.html` 在前端壳跑通后删除。
5. 根目录只留编排（启动脚本、env、Docker、文档），不留源码。

## 7. 前端技术选型建议

| 方案 | 评估 |
|---|---|
| **A. Vite + Vue 3 + Naive UI/Element Plus（推荐）** | 组件库覆盖表单/表格/抽屉/toast/暗色主题，开发效率最高；构建产物静态输出到 `server/webui/dist/` 由 StaticFiles 服务，运行时仍零 Node 依赖。代价：仓库引入 pnpm 前端子工程（`server/webui/` 转为 Vite 项目，构建产物入库或 CI 构建）。 |
| B. Preact/htm 或 petite-vue，无构建 | 保持零构建，但组件库缺位，表单/抽屉/暗色都要手搓，与「功能详细」目标冲突。 |
| C. 继续单文件原生 JS | 仅适合小修小补；本报告的信息架构（7 页面、SSE、设置表单）在单文件里不可维护，不建议。 |

推荐 A。若采纳，按全局约定使用 pnpm、TS strict、eslint+prettier；设计令牌集中于 `tokens.css`，暗色经 `prefers-color-scheme` + `data-theme` 双通道。

## 8. 实施路线图

| 阶段 | 内容 | 交付 |
|---|---|---|
| M0 结构迁移 | 目录迁移至 §6 monorepo 结构（backend/ 下移、server 分层拆分）；uv/pnpm、启动脚本、env、`.gitattributes`/`.editorconfig`、门禁基线 | 新结构下测试全绿 |
| M1 基础设施 | StaticFiles 挂载 dist、前端工程脚手架（Vite+Vue3+组件库）、设计令牌+暗色、布局壳（侧导航/状态条/toast）、统一响应模型（§5） | 新壳跑通，旧功能迁移：下载、作品浏览、任务列表、auth 弹窗 |
| M2 任务与持久化 | server 开 DB、job 持久化、任务操作端点（取消/重试/删除/清空）、分页筛选、SSE、任务详情抽屉、partial 状态 | 任务中心完整版 |
| M3 设置与下载增强 | settings 端点+设置页全分组、下载页高级选项（模式/数量/增量/时间/产物）、链接探测 tag | 设置页 + 下载工作台完整版 |
| M4 历史与发现 | history 端点+历史页、卡片「已下载」角标、hot-board/search 端点+发现页 | 历史 + 发现 |
| M5 直播与通知 | live 录制端点+页面、server 通知派发+测试按钮 | 全量能力对齐 |

每阶段独立可合并；M1 完成后旧 `index.html` 即可删除（及时删死代码）。

## 9. 风险与开放问题

1. **上游同步**：本项目基于 GitHub 上游 clone 二次开发；目录整体迁移后与上游的 diff/merge 成本显著升高，如仍需跟进上游更新，需接受手动搬运补丁的代价（或明确放弃跟随上游）。
2. **前端子工程与构建产物入库策略**：dist 入库（部署零依赖）vs CI 构建（仓库干净）——建议 dist 入库 + CI 校验一致性，Docker 多阶段构建不污染运行时镜像。需用户拍板。
3. **SSE 在 uvicorn 单 worker 下的连接占用**：连接数少（本地工具），风险低；仍保留轮询降级。
4. **数据库单例冲突**：`server/app.py:176` 注释提到的冲突原因需先查清（推测与 CLI 同进程单例有关），M2 前置任务。
5. **发现/搜索接口稳定性**：依赖抖音非公开接口，UI 需做好错误态与「功能可能受风控影响」的提示。

---

## 附录 A：配置项全量清单（设置页映射依据）

见 `config/default_config.py`。UI 可写回白名单（`config_loader.py:159-180`）：path、thread、rate_limit、video、cover、music、avatar、json、download_pinned、homepage_screenshot、proxy、retry_times、folderstyle、filename_template、folder_template、video_quality、comments、live、transcript、notifications。白名单之外的 `mode/number/increase/start_time/end_time` 建议作为 **per-job 参数**随请求下发（§5 P1），不写回配置文件。

环境变量覆盖：`DOUYIN_COOKIE`、`DOUYIN_PATH`、`DOUYIN_THREAD`、`DOUYIN_PROXY`（设置页对被 env 覆盖的项显示「由环境变量接管」并禁用编辑）。
