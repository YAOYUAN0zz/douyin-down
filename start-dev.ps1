# Windows 本机开发启动脚本（与 start-dev.sh 等价）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 外层若激活过别的虚拟环境，uv 会因与 --project backend 不符而告警；环境统一由 --project 决定
$env:VIRTUAL_ENV = $null

# 上次的后端没退干净会占着 .venv\Scripts\douyin-dl.exe，令 uv run 的重装步骤报 os error 32
if (Get-Process douyin-dl -ErrorAction SilentlyContinue) {
    Write-Error "检测到残留的 douyin-dl 进程，会占用 .venv\Scripts\douyin-dl.exe 导致启动失败。请先执行：taskkill /F /IM douyin-dl.exe"
}

if (-not (Test-Path .env.dev)) { Copy-Item .env.dev.example .env.dev }
$envMap = @{}
Get-Content .env.dev | Where-Object { $_ -match "^\s*[^#].*=" } | ForEach-Object {
    $k, $v = $_ -split "=", 2
    $envMap[$k.Trim()] = $v.Trim()
}

# ---- 依赖自动补齐 ----
# uv sync / pnpm install 都是幂等的：已装齐时秒回，缺了才装，故每次启动都跑。
# --inexact：只补不删，避免把用户额外装的 playwright 当「多余包」卸掉。
$uvExtras = if ($envMap["UV_EXTRAS"]) { $envMap["UV_EXTRAS"] } else { "server" }
$extraArgs = @()
foreach ($extra in ($uvExtras -split ",")) {
    $name = $extra.Trim()
    if ($name) { $extraArgs += @("--extra", $name) }
}
Write-Host "checking backend deps (extras: $uvExtras) ..."
uv sync --project backend @extraArgs --inexact
if ($LASTEXITCODE -ne 0) { Write-Error "后端依赖安装失败，请检查网络或镜像源可用性" }

# browser extra 只装 playwright 这个 Python 包，浏览器内核要另外下；该命令自身幂等
if ($uvExtras -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ -eq "browser" }) {
    Write-Host "checking playwright browser ..."
    uv run --project backend python -m playwright install chromium
}

function Test-PortFree([int]$Port) {
    -not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}
function Select-Port([int]$Port) {
    while (-not (Test-PortFree $Port)) { $Port++ }
    $Port
}

$backendHost = if ($envMap["BACKEND_HOST"]) { $envMap["BACKEND_HOST"] } else { "127.0.0.1" }
$backendPort = if ($envMap["BACKEND_PORT"]) { [int]$envMap["BACKEND_PORT"] } else { 8000 }
$frontendPort = if ($envMap["FRONTEND_PORT"]) { [int]$envMap["FRONTEND_PORT"] } else { 5173 }
$backendPort = Select-Port $backendPort
$frontendPort = Select-Port $frontendPort

# 回写实际端口
(Get-Content .env.dev) |
    ForEach-Object {
        $_ -replace "^BACKEND_PORT=.*", "BACKEND_PORT=$backendPort" `
           -replace "^FRONTEND_PORT=.*", "FRONTEND_PORT=$frontendPort" `
           -replace "^VITE_API_PORT=.*", "VITE_API_PORT=$backendPort"
    } | Set-Content -Encoding utf8 .env.dev

Write-Host "backend  -> http://${backendHost}:$backendPort"
Write-Host "frontend -> http://127.0.0.1:$frontendPort"

# 后端从仓库根目录运行，config.yml / Downloaded/ 等相对路径保持不变
$backendJob = Start-Process -PassThru -NoNewWindow uv -WorkingDirectory $PSScriptRoot `
    -ArgumentList "run", "--project", "backend", "douyin-dl", "--serve", "--serve-host", $backendHost, "--serve-port", $backendPort
try {
    Set-Location frontend
    # 无条件跑：pnpm install 幂等，且能在 lockfile 更新后补齐已存在但过期的 node_modules
    pnpm install
    $env:VITE_API_PORT = "$backendPort"
    pnpm dev --port $frontendPort --strictPort
} finally {
    # uv 只是外层壳，真正的服务是它派生的 douyin-dl.exe / python.exe：
    # 只停外层会留孤儿进程，占住端口与 exe，故按进程树清理
    if ($backendJob -and -not $backendJob.HasExited) {
        taskkill /F /T /PID $backendJob.Id 2>$null | Out-Null
    }
}
