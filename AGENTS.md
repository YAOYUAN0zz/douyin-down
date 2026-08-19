<!-- Generated: 2026-03-27 | Updated: 2026-05-08 -->

# douyin-downloader

> **Operating this project (install / run / use / troubleshoot) → read [`USAGE.md`](USAGE.md).**
> This file covers *developing* it: architecture, patterns, and test requirements.

## Purpose
A Python-based Douyin (TikTok China) batch downloader that fetches videos, galleries, music, and user content without watermarks. Supports multiple download modes (user posts, likes, mixes, music), concurrent downloads with rate limiting, and cookie-based authentication. YAML-configured, usable either as a CLI (`douyin-dl`) or as a REST API + Vue 3 web console (`douyin-dl --serve`).

## Repository Layout (monorepo)

| Path | Description |
|------|-------------|
| `backend/` | Python backend (managed by **uv**; run `uv sync --extra dev --extra server` inside) |
| `backend/pyproject.toml` | Build config, dependencies, CLI entry point (`douyin-dl`), tool settings |
| `frontend/` | Web UI (Vite + Vue 3 + TypeScript, managed by **pnpm**; build output `frontend/dist` is served by the backend) |
| `config.example.yml` | Example YAML config for users to copy and customize (runtime CWD = repo root) |
| `start-dev.sh` / `start-dev.ps1` | One-command dev startup (backend + frontend, port auto-bump) |
| `start-prod.sh` | Build frontend then serve everything from the backend |
| `Dockerfile` | Container build for the downloader |
| `dev_docs/` | Design docs (`webui-redesign-report.md`, `api.md`) |

## Backend Subdirectories (`backend/`)

| Directory | Purpose |
|-----------|---------|
| `auth/` | Cookie and MS token management (see `auth/AGENTS.md`) |
| `cli/` | CLI argument parsing, main async loop, progress display (see `cli/AGENTS.md`) |
| `config/` | YAML config loading, env var overrides, defaults (see `config/AGENTS.md`) |
| `control/` | Concurrency control — rate limiter, retry handler, queue manager (see `control/AGENTS.md`) |
| `core/` | Business logic — API client, URL parser, downloaders, strategy pattern (see `core/AGENTS.md`) |
| `server/` | FastAPI service — `api/` routers → services (`jobs.py`, `works.py`, `auth_flow.py`) → storage |
| `storage/` | SQLite database, file management, metadata handling (see `storage/AGENTS.md`) |
| `tests/` | Pytest test suite (see `tests/AGENTS.md`) |
| `tools/` | Standalone utilities like browser-based cookie fetching (see `tools/AGENTS.md`) |
| `utils/` | Shared helpers — logging, validation, anti-bot signatures (see `utils/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- Python 3.8+ compatibility required — avoid walrus operator, `match` statements, and `type` aliases
- All I/O is async (`aiohttp`, `aiofiles`, `aiosqlite`) — never use blocking I/O in core paths
- Entry point is `cli.main:main()` which calls `asyncio.run(main_async(args))`
- Config is YAML-based with env var overrides (`DOUYIN_*` prefix)
- The `mix`/`allmix` config alias system requires special handling (see `config/config_loader.py`)

### Testing Requirements
- Run (from `backend/`): `uv run pytest`
- Async tests use `pytest-asyncio` with `asyncio_mode = "auto"`
- Linting (from `backend/`): `uv run ruff check .` (line-length 100)
- Frontend (from `frontend/`): `pnpm build` must pass (vue-tsc strict)

### Common Patterns
- Factory pattern for downloaders (`DownloaderFactory.create()`)
- Strategy pattern for user download modes (`core/user_modes/`)
- Registry pattern for mode discovery (`UserModeRegistry`)
- All downloaders inherit from `BaseDownloader` with shared `_download_mode_items()`
- Logging via `utils.logger.setup_logger(name)` — one logger per module

## Dependencies

### External
- `aiohttp` — async HTTP client for API calls and downloads
- `aiofiles` — async file I/O
- `aiosqlite` — async SQLite for download history
- `rich` — terminal UI (progress bars, tables, styled output)
- `pyyaml` — YAML config parsing
- `python-dateutil` — date/time parsing for time-range filters
- `gmssl` — Chinese SM3/SM4 crypto for anti-bot signatures

### Optional
- `playwright` — browser automation for cookie fetching

<!-- MANUAL: -->
