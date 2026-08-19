#!/usr/bin/env bash
# 一键启动开发环境：后端（uv + FastAPI --serve）+ 前端（Vite dev server）
# 端口策略：读 .env.dev 默认端口，被占则 +1 递增并回写实际端口。
set -euo pipefail
cd "$(dirname "$0")"

# 外层 shell 若激活过别的虚拟环境，uv 会因与 --project backend 不符而告警；
# 这里统一由 --project 决定环境，直接清掉该变量
unset VIRTUAL_ENV

# Windows 上 uv run 启动前要重装项目，若上次的后端没退干净会占着
# .venv/Scripts/douyin-dl.exe，导致 "os error 32"。先给出可执行的提示而非让 uv 报晦涩错误
if command -v tasklist >/dev/null 2>&1; then
    if tasklist //FI "IMAGENAME eq douyin-dl.exe" //NH 2>/dev/null | grep -qi douyin-dl; then
        echo "检测到残留的 douyin-dl 进程，会占用 .venv/Scripts/douyin-dl.exe 导致启动失败。" >&2
        echo "请先执行：taskkill /F /IM douyin-dl.exe" >&2
        exit 1
    fi
fi

[ -f .env.dev ] || cp .env.dev.example .env.dev
set -a
. ./.env.dev
set +a

# OSTYPE 在以 sh 调用时可能为空，回退到 uname
case "${OSTYPE:-$(uname -s 2>/dev/null || echo unknown)}" in
    msys* | cygwin* | win32 | MSYS* | MINGW* | CYGWIN*) IS_WINDOWS=1 ;;
    *) IS_WINDOWS=0 ;;
esac

# 端口占用判定必须覆盖所有监听地址：vite 默认绑在 ::1（IPv6），
# 只连 127.0.0.1 会误判为空闲，随后 --strictPort 启动失败
port_free() {
    if [ "$IS_WINDOWS" = 1 ]; then
        ! netstat -ano 2>/dev/null |
            awk -v port=":$1" '$1 == "TCP" && $2 ~ port"$" && $4 == "LISTENING" { found = 1 } END { exit !found }'
    else
        ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null &&
            ! (exec 3<>"/dev/tcp/[::1]/$1") 2>/dev/null
    fi
}

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

# uv run / pnpm 都只是外层壳，真正的服务是它们派生的 douyin-dl.exe、python.exe、
# vite。只 kill 外层会留下孤儿进程占住端口（下次启动端口漂移甚至失败），故按进程树清理。
# 端口在启动前已确认空闲，此刻监听者必是本脚本拉起的进程。
kill_port_tree() {
    local win_pid
    win_pid="$(netstat -ano 2>/dev/null |
        awk -v port=":$1" '$1 == "TCP" && $2 ~ port"$" && $4 == "LISTENING" {print $5; exit}')"
    [ -n "$win_pid" ] && taskkill //F //T //PID "$win_pid" >/dev/null 2>&1
    return 0
}

cleanup() {
    if [ "$IS_WINDOWS" = 1 ]; then
        # MSYS bash 的 $! 是 MSYS pid，taskkill 只认 Windows pid，故按监听端口反查
        kill_port_tree "$BACKEND_PORT"
        kill_port_tree "$FRONTEND_PORT"
    else
        pkill -P "${BACKEND_PID:-0}" 2>/dev/null || true
    fi
    kill "${BACKEND_PID:-0}" 2>/dev/null || true
    return 0
}
trap cleanup EXIT INT TERM

cd frontend
[ -d node_modules ] || pnpm install
# 前端同样放后台：若留在前台，bash 会把信号处理推迟到它结束，
# Ctrl+C 时 trap 形同虚设，进程照样成为孤儿
VITE_API_PORT="$VITE_API_PORT" pnpm dev --port "$FRONTEND_PORT" --strictPort &
FRONTEND_PID=$!

# wait 可被信号立即打断，从而让 cleanup 及时执行；任一端退出即整体收摊
wait -n 2>/dev/null || wait "$FRONTEND_PID" 2>/dev/null || true
