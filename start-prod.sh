#!/usr/bin/env bash
# 生产启动：构建前端产物后由后端 StaticFiles 统一服务
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env.prod ] || cp .env.prod.example .env.prod
set -a
. ./.env.prod
set +a

(cd frontend && pnpm install --frozen-lockfile && pnpm build)
unset VIRTUAL_ENV
exec uv run --project backend douyin-dl --serve --serve-host "${BACKEND_HOST:-0.0.0.0}" --serve-port "${BACKEND_PORT:-8000}"
