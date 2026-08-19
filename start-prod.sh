#!/usr/bin/env bash
# 生产启动：构建前端产物后由后端 StaticFiles 统一服务
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env.prod ] || cp .env.prod.example .env.prod
set -a
. ./.env.prod
set +a

unset VIRTUAL_ENV

# 依赖自动补齐。生产用 --frozen 系列：只按 lockfile 安装，绝不隐式改锁，
# 保证线上装到的与提交时解析的完全一致。
UV_EXTRAS="${UV_EXTRAS:-server}"
EXTRA_ARGS=""
for extra in $(echo "$UV_EXTRAS" | tr ',' ' '); do
    EXTRA_ARGS="$EXTRA_ARGS --extra $extra"
done
# shellcheck disable=SC2086
uv sync --project backend $EXTRA_ARGS --frozen --no-dev --inexact

(cd frontend && pnpm install --frozen-lockfile && pnpm build)
exec uv run --project backend --no-sync douyin-dl --serve --serve-host "${BACKEND_HOST:-0.0.0.0}" --serve-port "${BACKEND_PORT:-8000}"
