# Windows 本机开发启动脚本（与 start-dev.sh 等价）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .env.dev)) { Copy-Item .env.dev.example .env.dev }
$envMap = @{}
Get-Content .env.dev | Where-Object { $_ -match "^\s*[^#].*=" } | ForEach-Object {
    $k, $v = $_ -split "=", 2
    $envMap[$k.Trim()] = $v.Trim()
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
    if (-not (Test-Path node_modules)) { pnpm install }
    $env:VITE_API_PORT = "$backendPort"
    pnpm dev --port $frontendPort --strictPort
} finally {
    if ($backendJob -and -not $backendJob.HasExited) { Stop-Process -Id $backendJob.Id -Force }
}
