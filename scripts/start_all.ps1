# Wave 2 四服务一键启动 / 停止（冒烟点火脚本）
# A 设备监测(8101) / B 故障预警(8102) / C 维修工单(8103) / D 身份通知(8104)
# 首次启动为各服务生成独立 .env（数据库互不共用、内部令牌统一、
# MEMBER_*_BASE 按端口互指，变量名以各模块 src/config.py 实际读取为准）。
# 用法：
#   .\scripts\start_all.ps1          # 启动四服务并等待全部 UP（60s 超时）
#   .\scripts\start_all.ps1 -Stop    # 停止四服务并关闭其窗口
param(
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$internalToken = "dev-internal-token-change-me"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $env:TEMP "ims_start_all_pids.txt"

$baseA = "http://127.0.0.1:8101"
$baseB = "http://127.0.0.1:8102"
$baseC = "http://127.0.0.1:8103"
$baseD = "http://127.0.0.1:8104"

# 四服务：目录 / 端口（工作目录 = 仓库根 + Dir）
$services = @(
    @{ Code = "A"; Title = "设备监测"; Dir = "apps\equipment-monitoring"; Port = 8101 },
    @{ Code = "B"; Title = "故障预警"; Dir = "apps\fault-warning";        Port = 8102 },
    @{ Code = "C"; Title = "维修工单"; Dir = "apps\maintenance";          Port = 8103 },
    @{ Code = "D"; Title = "身份通知"; Dir = "apps\integration-quality";  Port = 8104 }
)

function Get-EnvContent {
    param([string]$Code)
    switch ($Code) {
        "A" {
            "MEMBER_A_PORT=8101`n" +
            "MEMBER_A_DATABASE_URL=sqlite:///./member_a.db`n" +
            "INTERNAL_API_TOKEN=$internalToken`n" +
            "MEMBER_B_BASE=$baseB`nMEMBER_C_BASE=$baseC`nMEMBER_D_BASE=$baseD`n"
        }
        "B" {
            "MEMBER_B_PORT=8102`n" +
            "MEMBER_B_DATABASE_URL=sqlite:///./member_b.db`n" +
            "INTERNAL_API_TOKEN=$internalToken`n" +
            "MEMBER_A_BASE=$baseA`nMEMBER_C_BASE=$baseC`nMEMBER_D_BASE=$baseD`n"
        }
        "C" {
            "MEMBER_C_PORT=8103`n" +
            "DATABASE_URL=sqlite:///./member_c.db`n" +
            "INTERNAL_API_TOKEN=$internalToken`n" +
            "MEMBER_A_BASE=$baseA`nMEMBER_B_BASE=$baseB`nMEMBER_D_BASE=$baseD`n"
        }
        "D" {
            "MEMBER_D_PORT=8104`n" +
            "MEMBER_D_DATABASE_URL=sqlite:///./member_d.db`n" +
            "INTERNAL_API_TOKEN=$internalToken`n" +
            "MEMBER_A_BASE=$baseA`nMEMBER_B_BASE=$baseB`nMEMBER_C_BASE=$baseC`n"
        }
    }
}

# ---------- -Stop：停止四服务 ----------
if ($Stop) {
    Write-Host "== 停止四服务 ==" -ForegroundColor Yellow
    foreach ($s in $services) {
        $procIds = @()
        try {
            $procIds = @(Get-NetTCPConnection -LocalPort $s.Port -State Listen `
                -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -Unique)
        } catch { }
        if ($procIds.Count -gt 0) {
            foreach ($procId in $procIds) {
                try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch { }
                Write-Host ("[STOP] {0}-{1} 端口 {2} 进程 PID {3} 已终止" -f `
                    $s.Code, $s.Title, $s.Port, $procId)
            }
        } else {
            Write-Host ("[STOP] {0}-{1} 端口 {2} 无监听进程" -f `
                $s.Code, $s.Title, $s.Port)
        }
    }
    if (Test-Path $pidFile) {
        foreach ($procId in (Get-Content $pidFile)) {
            try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch { }
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        Write-Host "[STOP] 已关闭启动窗口并清理 PID 记录（$pidFile）"
    }
    exit 0
}

# ---------- 1. 生成各服务 .env（若不存在） ----------
Write-Host "== 生成各服务 .env（若不存在，独立数据库互不共用） ==" -ForegroundColor Cyan
foreach ($s in $services) {
    $envPath = Join-Path (Join-Path $repoRoot $s.Dir) ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        Set-Content -LiteralPath $envPath -Value (Get-EnvContent -Code $s.Code) -Encoding ASCII
        Write-Host ("[ENV ] 新建 {0}" -f $envPath)
    } else {
        Write-Host ("[ENV ] 已存在，沿用 {0}" -f $envPath)
    }
}

# ---------- 2. 每服务一个后台窗口启动 uvicorn ----------
Write-Host "== 启动四个服务（各占一个最小化窗口，点开可看日志） ==" -ForegroundColor Cyan
$startedPids = @()
foreach ($s in $services) {
    $workDir = Join-Path $repoRoot $s.Dir
    $inner = "Set-Location -LiteralPath '{0}'; " -f $workDir
    $inner += "Write-Host '== {0}-{1} (端口 {2}) ==' -ForegroundColor Green; " -f `
        $s.Code, $s.Title, $s.Port
    $inner += "python -m uvicorn src.main:app --host 127.0.0.1 --port {0}" -f $s.Port
    $encoded = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($inner))
    $proc = Start-Process powershell `
        -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded) `
        -WindowStyle Minimized -PassThru
    $startedPids += $proc.Id
    Write-Host ("[RUN ] {0}-{1} 窗口 PID {2} 端口 {3}" -f `
        $s.Code, $s.Title, $proc.Id, $s.Port)
}
$startedPids | Set-Content $pidFile

# ---------- 3. 轮询 /health 直到全部 UP（60s 超时） ----------
Write-Host "== 等待 /health 全部 UP（最长 60s） ==" -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(60)
$ready = @{}
do {
    foreach ($s in $services) {
        if ($ready[$s.Port]) { continue }
        try {
            $resp = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/health" -f $s.Port) `
                -TimeoutSec 2
            if ($resp.status -eq "UP") {
                $ready[$s.Port] = $true
                Write-Host ("[OK  ] {0}-{1} (端口 {2}) UP" -f `
                    $s.Code, $s.Title, $s.Port) -ForegroundColor Green
            }
        } catch { }
    }
    if ($ready.Count -eq $services.Count) { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

if ($ready.Count -lt $services.Count) {
    $notReady = @($services | Where-Object { -not $ready[$_.Port] })
    Write-Host ""
    Write-Host "启动失败（60s 超时），以下服务未就绪：" -ForegroundColor Red
    foreach ($s in $notReady) {
        Write-Host ("  - {0}-{1} 端口 {2} http://127.0.0.1:{2}/health" -f `
            $s.Code, $s.Title, $s.Port) -ForegroundColor Red
    }
    Write-Host "请查看对应最小化 PowerShell 窗口中的完整报错。"
    exit 1
}

Write-Host ""
Write-Host "四服务全部 UP：" -ForegroundColor Green
foreach ($s in $services) {
    $h = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/health" -f $s.Port)
    Write-Host ("  {0} {1} -> {2}" -f $s.Code, $s.Title, ($h | ConvertTo-Json -Compress))
}
Write-Host ""
Write-Host ("停止命令：powershell -ExecutionPolicy Bypass -File `"{0}`" -Stop" -f `
    (Join-Path $PSScriptRoot "start_all.ps1"))
