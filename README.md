# 抖音下载器

> 由 [拾壹0x7f](https://github.com/shiyi-0x7f) 维护的抖音内容下载与管理工具，提供 CLI、REST API 与 Vue 3 Web UI。

用于下载有权访问和保存的视频、图文、合集、音乐及作者主页作品；支持任务进度、下载历史、SQLite 去重、批量与增量下载，以及浏览器辅助获取下载参数。

> [!WARNING]
> 请仅下载有权访问、保存或处理的内容，并遵守平台规则、适用法律及他人的隐私和版权。平台接口、登录态和风控策略可能随时变化，部分功能可能因此失效。

## 核心能力

- **多类型链接**：视频、图文、合集、音乐、短链与作者主页。
- **多种使用方式**：CLI、FastAPI REST API，以及同页浏览作品和提交下载的 Web UI。
- **任务管理**：实时进度、取消/重试、SQLite 历史记录与已下载去重。
- **批量下载**：主页发布作品、点赞、合集、音乐、收藏夹、增量下载与时间过滤。
- **下载控制**：无水印源优先、画质选择、并发/限速/重试、文件完整性校验。
- **扩展能力**：热搜/关键词搜索、通知推送与浏览器辅助分页；评论采集和直播录制目前仅保留 CLI 配置入口。

完整使用、配置与排障说明见 [USAGE.md](./USAGE.md)，接口说明见 [API 文档](./dev_docs/api.md)。

## 快速开始

### 环境要求

- Python **3.9+** 与 [uv](https://docs.astral.sh/uv/)
- 使用 Web UI 时，还需要 Node.js **20+** 与 [pnpm](https://pnpm.io/)
- Windows、macOS 或 Linux

以下命令均应在**仓库根目录**运行。`config.yml`、`.cookies.json`、`Downloaded/` 与数据库等运行文件依赖当前工作目录。

### 1. 创建配置

macOS / Linux：

```bash
cp config.example.yml config.yml
```

Windows PowerShell：

```powershell
Copy-Item config.example.yml config.yml
```

### 2. 获取下载参数

推荐通过浏览器登录自动获取 Cookie 与下载参数：

```bash
uv run --project backend python -m tools.cookie_fetcher --config config.yml
```

完成浏览器登录后回到终端继续即可。Cookie 会过期；遇到登录态或风控错误时，请重新获取。

### 3. 选择启动方式

#### Web UI（推荐）

开发模式会同时启动后端与 Vite 前端，并自动补齐依赖：

```bash
./start-dev.sh
```

Windows PowerShell：

```powershell
.\start-dev.ps1
```

生产模式会构建前端后由后端统一提供页面：

```bash
./start-prod.sh
```

> `start-dev.*` 默认安装 `server,browser` 依赖及 Chromium，以支持 Web UI 与浏览器登录流程；首次执行需要下载浏览器内核。

#### CLI

使用配置文件执行：

```bash
uv run --project backend douyin-dl -c config.yml
```

临时追加链接、并发数和下载路径：

```bash
uv run --project backend douyin-dl -c config.yml \
  -u "https://www.douyin.com/video/7604129988555574538" \
  -t 5 \
  -p ./Downloaded
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `-u, --url` | 追加下载链接，可重复传入 |
| `-c, --config` | 配置文件路径，默认 `config.yml` |
| `-p, --path` | 下载目录 |
| `-t, --thread` | 并发数 |
| `-v, --verbose` | 输出更详细的日志 |
| `--serve` | 启动 REST API 与已构建的 Web UI |
| `--hot-board [N]` | 导出抖音热搜结果 |
| `--search KEYWORD` | 按关键词搜索并导出结果 |

运行 `uv run --project backend douyin-dl --help` 查看完整参数列表。

## Web UI

Web UI 提供以下主要流程：

1. 在下载页粘贴单个视频、图文、合集、音乐或作者主页链接；
2. 使用“浏览作品”查看可取得的作品卡片、画质、元数据与下载状态；
3. 勾选需要的作品后提交下载，或直接创建下载任务；
4. 在任务中心查看进度、重试或取消任务；
5. 在历史记录中搜索、查看已下载作品及元数据。

作者主页的作品列表依赖抖音接口返回有效分页数据。若出现验证码、403、Cookie 失效或接口风控，页面会提示错误或结果可能不完整；这不表示所有作品都已成功取得。

## 常见限制

- 登录 Cookie 与下载参数会失效，需要重新获取。
- 收藏夹相关模式仅支持当前 Cookie 对应的账号，且不能与其他主页模式混用。
- 浏览器辅助功能可能需要人工完成登录或验证码，不能保证绕过平台限制。
- 评论采集与直播录制已暂从 Web UI 设置页下线；如有需要，仍可通过 CLI 配置使用，且受平台变化影响较大。

## 数据与凭据安全

以下文件可能包含登录凭据、个人下载数据或数据库记录，已被 Git 忽略，**不要提交、打包或外发**：

- `config.yml`
- `.cookies.json`
- `.env.dev` / `.env.prod`
- `dy_downloader.db*`
- `Downloaded/`

## 开发与验证

后端：

```bash
uv --directory backend run ruff check .
uv --directory backend run pytest
```

前端：

```bash
cd frontend
pnpm check
pnpm build
```

项目结构、开发约定与测试要求见 [AGENTS.md](./AGENTS.md)。

## 维护与致谢

**拾壹0x7f** 负责本仓库的持续维护与二次开发，包括 Vue 3 Web 控制台、前后端 monorepo 重构、任务与历史记录能力。

本项目基于 [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader) 的原始实现进行二次开发，感谢原项目的开源贡献。

### 联系与关注

<p>
  <a href="https://github.com/shiyi-0x7f"><img src="https://img.shields.io/badge/GitHub-shiyi--0x7f-181717?style=flat-square&logo=github&logoColor=white" alt="GitHub" /></a>
  <a href="https://x.com/shiyi0x7f"><img src="https://img.shields.io/badge/X-@shiyi0x7f-000000?style=flat-square&logo=x&logoColor=white" alt="X" /></a>
  <a href="https://space.bilibili.com/19276680"><img src="https://img.shields.io/badge/Bilibili-19276680-00A1D6?style=flat-square&logo=bilibili&logoColor=white" alt="Bilibili" /></a>
  <img src="https://img.shields.io/badge/WeChat-%E6%89%AB%E7%A0%81%E5%85%B3%E6%B3%A8-07C160?style=flat-square&logo=wechat&logoColor=white" alt="微信公众号" />
</p>

<img src="./img/wechat-mp-qr.jpg" alt="拾壹0x7f 微信公众号二维码" width="180" />

## 许可证

本项目采用 [MIT License](./LICENSE)。
