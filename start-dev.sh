#!/usr/bin/env bash
# 一键启动开发环境：后端（uv + FastAPI --serve）+ 前端（Vite dev server）
# 端口策略：读 .env.dev 默认端口，被占则 +1 递增并回写实际端口。
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env.dev ] || cp .env.dev.example .env.dev
set -a
. ./.env.dev
set +a

port_free() { ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

pick_port() {
    local p="$1"
    while ! port_free "$p"; do p=$((p + 1)); done
    echo "$p"
}

BACKEND_PORT="$(pick_port "${BACKEND_PORT:-8000}")"
FRONTEND_PORT="$(pick_port "${FRONTEND_PORT:-5173}")"
VITE_API_PORT="$BACKEND_PORT"

# 回写实际端口，供前端与下次启动使用
sed -i.bak \
    -e "s/^BACKEND_PORT=.*/BACKEND_PORT=$BACKEND_PORT/" \
    -e "s/^FRONTEND_PORT=.*/FRONTEND_PORT=$FRONTEND_PORT/" \
    -e "s/^VITE_API_PORT=.*/VITE_API_PORT=$VITE_API_PORT/" .env.dev
rm -f .env.dev.bak

echo "backend  -> http://${BACKEND_HOST:-127.0.0.1}:$BACKEND_PORT"
echo "frontend -> http://127.0.0.1:$FRONTEND_PORT"

# 后端从仓库根目录运行，config.yml / Downloaded/ 等相对路径保持不变
uv run --project backend douyin-dl --serve --serve-host "${BACKEND_HOST:-127.0.0.1}" --serve-port "$BACKEND_PORT" &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT

cd frontend
[ -d node_modules ] || pnpm install
VITE_API_PORT="$VITE_API_PORT" pnpm dev --port "$FRONTEND_PORT" --strictPort
