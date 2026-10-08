# Wave 2 四服务一键启动 / 停止（Windows 本机演示入口）
# A 设备监测(8101) / B 故障预警(8102) / C 维修工单(8103) / D 身份通知(8104)
# 统一入口(8888) 静态托管 web/ 并把 /a /b /c /d 反代到四服务（与 deploy/nginx.conf 同口径）。
#
# 首次运行自举：检查 python(>=3.10) → 创建仓库根共享 .venv → 安装各服务依赖 →
# 生成各服务 .env（数据库互不共用、内部令牌统一）→ 启动四服务 + 8888 统一入口。
# 与服务器版 scripts/start_all.sh 行为对齐（同样的 venv、依赖、env 口径）。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1            # 启动
#   powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1 -Stop      # 停止
#   powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1 -SkipInstall  # 跳过依赖安装
#   powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1 -NoWeb     # 不启动统一入口
#   powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1 -WebPort 8889  # 统一入口换端口
param(
    [switch]$Stop,
    [switch]$SkipInstall,
    [switch]$NoWeb,
    [int]$WebPort = 8888
)

# PowerShell 7.3+ 默认把原生命令非零退出码当成终止性错误；本脚本自己检查
# $LASTEXITCODE，故显式关掉该行为，保证 5.1 与 7.x 下语义一致。
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$ErrorActionPreference = "Stop"
$internalToken = "dev-internal-token-change-me"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $env:TEMP "ims_start_all_pids.txt"
$webPortFile = Join-Path $env:TEMP "ims_start_all_webport.txt"
$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

# 统一入口端口（可用 -WebPort 覆盖，例如 8888 被 Jupyter 占用时改 8889）
if ($WebPort -lt 1 -or $WebPort -gt 65535) {
    Write-Host ("[ERR ] -WebPort 取值非法：{0}（应为 1-65535）" -f $WebPort) -ForegroundColor Red
    exit 1
}
if ($WebPort -in @(8101, 8102, 8103, 8104)) {
    Write-Host ("[ERR ] -WebPort {0} 与四服务端口冲突，请换一个（如 8889）" -f $WebPort) -ForegroundColor Red
    exit 1
}
$webPort = $WebPort

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

# 各服务 .env：变量名以各模块 src/config.py 实际读取为准。
# 注意 B 与 A/C/D 命名不同：B 读 DATABASE_URL 与 *_SERVICE_URL（见 apps/fault-warning/src/config.py），
# 早期版本误写 MEMBER_B_DATABASE_URL / MEMBER_A_BASE，因 pydantic extra="ignore" +
# 默认值恰好等价而"碰巧能跑"。此处按实际键名生成。
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
            "DATABASE_URL=sqlite:///./member_b.db`n" +
            "INTERNAL_API_TOKEN=$internalToken`n" +
            "EQUIPMENT_SERVICE_URL=$baseA`n" +
            "MAINTENANCE_SERVICE_URL=$baseC`n" +
            "INTEGRATION_SERVICE_URL=$baseD`n" +
            "ALLOW_CLIENT_MOCK=false`n"
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

# 该服务 config.py 必须能读到的键（缺失即视为坏文件，重写并备份）
function Get-EnvRequiredKeys {
    param([string]$Code)
    switch ($Code) {
        "A" { @("MEMBER_A_PORT", "MEMBER_A_DATABASE_URL", "INTERNAL_API_TOKEN",
                 "MEMBER_B_BASE", "MEMBER_C_BASE", "MEMBER_D_BASE") }
        "B" { @("MEMBER_B_PORT", "DATABASE_URL", "INTERNAL_API_TOKEN",
                 "EQUIPMENT_SERVICE_URL", "MAINTENANCE_SERVICE_URL",
                 "INTEGRATION_SERVICE_URL") }
        "C" { @("MEMBER_C_PORT", "DATABASE_URL", "INTERNAL_API_TOKEN",
                 "MEMBER_A_BASE", "MEMBER_B_BASE", "MEMBER_D_BASE") }
        "D" { @("MEMBER_D_PORT", "MEMBER_D_DATABASE_URL", "INTERNAL_API_TOKEN",
                 "MEMBER_A_BASE", "MEMBER_B_BASE", "MEMBER_C_BASE") }
    }
}

# 返回 .env 中缺失的键名列表（空列表 = 键名齐全）
function Get-EnvMissingKeys {
    param([string]$Path, [string]$Code)
    $missing = @()
    foreach ($key in (Get-EnvRequiredKeys -Code $Code)) {
        $found = $false
        foreach ($line in (Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue)) {
            if ($line -match ("^\s*" + [regex]::Escape($key) + "\s*=")) { $found = $true; break }
        }
        if (-not $found) { $missing += $key }
    }
    return $missing
}

# 按端口终止监听进程（-Stop 用）。
# -CommandLinePattern 非空时，只终止命令行匹配该正则的进程：避免 -Stop 误杀
# 不是本脚本启动的同端口服务（例如你机器上 8888 原本跑着 Jupyter）。
function Stop-ListeningPort {
    param([int]$Port, [string]$Label, [string]$CommandLinePattern = "")
    $procIds = @()
    try {
        $procIds = @(Get-NetTCPConnection -LocalPort $Port -State Listen `
            -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch { }
    if ($procIds.Count -eq 0) {
        Write-Host ("[STOP] {0} 端口 {1} 无监听进程" -f $Label, $Port)
        return
    }
    foreach ($procId in $procIds) {
        if ($CommandLinePattern -and -not (Test-ProcessCommandLine -ProcId $procId -Pattern $CommandLinePattern)) {
            Write-Host ("[SKIP] {0} 端口 {1} 的 PID {2} 不是本脚本启动的（不误杀）" `
                -f $Label, $Port, $procId) -ForegroundColor Yellow
            continue
        }
        try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch { }
        Write-Host ("[STOP] {0} 端口 {1} 进程 PID {2} 已终止" -f $Label, $Port, $procId)
    }
}

# 检查某进程的命令行是否匹配正则（拿不到命令行时保守返回 $false）
function Test-ProcessCommandLine {
    param([int]$ProcId, [string]$Pattern)
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $ProcId) `
            -ErrorAction Stop).CommandLine
    } catch { return $false }
    if (-not $cmd) { return $false }
    return ($cmd -match $Pattern)
}

# ---------- -Stop：停止四服务 + 统一入口 ----------
if ($Stop) {
    # 未显式给 -WebPort 时，读回上次启动记下的端口（避免默认 8888 找错对象）
    if (-not $PSBoundParameters.ContainsKey("WebPort") -and (Test-Path $webPortFile)) {
        try {
            $savedPort = [int](Get-Content $webPortFile -ErrorAction Stop | Select-Object -First 1)
            if ($savedPort -ge 1 -and $savedPort -le 65535) { $webPort = $savedPort }
        } catch { }
    }
    Write-Host ("== 停止四服务与统一入口（入口端口 {0}） ==" -f $webPort) -ForegroundColor Yellow
    foreach ($s in $services) {
        Stop-ListeningPort -Port $s.Port -Label ("{0}-{1}" -f $s.Code, $s.Title) `
            -CommandLinePattern "uvicorn"
    }
    if (-not $NoWeb) {
        Stop-ListeningPort -Port $webPort -Label "统一入口" -CommandLinePattern "dev_server\.py"
    }
    if (Test-Path $pidFile) {
        foreach ($procId in (Get-Content $pidFile)) {
            try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch { }
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        Write-Host "[STOP] 已关闭启动窗口并清理 PID 记录（$pidFile）"
    }
    Remove-Item $webPortFile -Force -ErrorAction SilentlyContinue
    exit 0
}

# ---------- 1. 自举：定位可用的 Python（>=3.10） ----------
function Get-PythonCommand {
    $candidates = @(
        @{ Exe = "py";       Args = @("-3") },
        @{ Exe = "python";   Args = @() },
        @{ Exe = "python3";  Args = @() }
    )
    $found = @()
    foreach ($cand in $candidates) {
        if (-not (Get-Command $cand.Exe -ErrorAction SilentlyContinue)) { continue }
        $version = $null
        try {
            $raw = & $cand.Exe @($cand.Args + @("-c", "import sys; print('%d.%d' % sys.version_info[:2])")) 2>$null
            if ($LASTEXITCODE -eq 0 -and $raw) { $version = "$raw".Trim() }
        } catch { $version = $null }
        if ($version) {
            $found += ,@{ Exe = $cand.Exe; Args = $cand.Args; Version = $version }
        }
    }
    if ($found.Count -eq 0) {
        Write-Host "[ERR ] 未找到可用的 Python。请安装 Python 3.10+（勾选 Add python.exe to PATH）：" -ForegroundColor Red
        Write-Host "       https://www.python.org/downloads/windows/" -ForegroundColor Red
        exit 1
    }
    foreach ($f in $found) {
        $parts = $f.Version.Split(".")
        if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10)) {
            Write-Host ("[PY  ] 使用 {0} {1}（Python {2}）" -f $f.Exe, ($f.Args -join " "), $f.Version)
            return $f
        }
    }
    $versions = ($found | ForEach-Object { "$($_.Exe) $($_.Version)" }) -join "、"
    Write-Host ("[ERR ] Python 版本过低（需 >= 3.10，当前：{0}）。请安装 3.10+ 后重试。" -f $versions) -ForegroundColor Red
    exit 1
}

# ---------- 2. 自举：共享 venv（幂等；兼容从 Linux 拷来的 .venv） ----------
function Ensure-Venv {
    param([hashtable]$Python)
    if (Test-Path $venvPython) {
        Write-Host "[VENV] 已存在，沿用 $venvDir"
        return
    }
    if (Test-Path $venvDir) {
        # 典型场景：整个仓库（含 Linux/macOS 建的 .venv）拷到 Windows，只有 bin/ 没有 Scripts/。
        # 不删除：改名留底（在原平台重跑 start_all.sh 会重新生成），避免误删他人环境。
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $backupDir = "$venvDir.linux-$stamp"
        Write-Host "[VENV] 现有 .venv 不适用于 Windows（缺少 Scripts\python.exe），" -ForegroundColor Yellow
        Write-Host ("[VENV] 将改名为 {0} 后重建（不删除，可在原平台恢复）" -f $backupDir) -ForegroundColor Yellow
        try {
            Move-Item -LiteralPath $venvDir -Destination $backupDir -ErrorAction Stop
        } catch {
            Write-Host ("[ERR ] 无法移动 {0}：{1}" -f $venvDir, $_.Exception.Message) -ForegroundColor Red
            Write-Host "       请手动重命名或删除该目录后重试。" -ForegroundColor Red
            exit 1
        }
    }
    Write-Host "== 创建共享虚拟环境（仓库根 .venv，幂等） ==" -ForegroundColor Cyan
    & $Python.Exe @($Python.Args + @("-m", "venv", $venvDir))
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Write-Host "[ERR ] venv 创建失败。请确认 Python 安装完整（含 venv 模块）后重试。" -ForegroundColor Red
        exit 1
    }
}

# ---------- 3. 自举：安装四服务依赖（幂等，以各 app 目录 requirements.txt 为准） ----------
function Install-Deps {
    Write-Host "== 安装四服务依赖（首次较慢，幂等可重复执行） ==" -ForegroundColor Cyan
    foreach ($s in $services) {
        $appDir = Join-Path $repoRoot $s.Dir
        $req = Join-Path $appDir "requirements.txt"
        if (-not (Test-Path $req)) {
            Write-Host ("[DEPS] {0}-{1} 无 requirements.txt，跳过" -f $s.Code, $s.Title) -ForegroundColor Yellow
            continue
        }
        Push-Location $appDir
        try {
            & $venvPython -m pip install -q --disable-pip-version-check -r requirements.txt
            $code = $LASTEXITCODE
        } finally {
            Pop-Location
        }
        if ($code -ne 0) {
            Write-Host ("[ERR ] {0}-{1} 依赖安装失败（{2}\requirements.txt）。" -f $s.Code, $s.Title, $s.Dir) -ForegroundColor Red
            Write-Host "       国内网络可换镜像源重试：" -ForegroundColor Red
            Write-Host ("       {0} -m pip install -r {1}\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple" -f $venvPython, $s.Dir) -ForegroundColor Red
            exit 1
        }
        Write-Host ("[DEPS] {0}-{1} 依赖就绪（{2}\requirements.txt）" -f $s.Code, $s.Title, $s.Dir)
    }
}

Write-Host "== 检查 Python 与依赖 ==" -ForegroundColor Cyan
$python = Get-PythonCommand
Ensure-Venv -Python $python
if ($SkipInstall) {
    Write-Host "[DEPS] 已指定 -SkipInstall，跳过依赖安装" -ForegroundColor Yellow
} else {
    Install-Deps
}

# ---------- 4. 生成各服务 .env（若不存在；键名不全则备份重写） ----------
# 背景：B 读 DATABASE_URL / *_SERVICE_URL，与 A/C/D 的 MEMBER_*_BASE 命名不同。
# 早期脚本给 B 写错了键名，pydantic extra="ignore" + 默认值让问题「碰巧不报错」，
# 却在 Windows 上把回连地址变成 localhost（→ IPv6 ::1，服务只监听 127.0.0.1），
# 触发「登录已过期」死循环。此处让历史坏文件自动愈合。
Write-Host "== 生成各服务 .env（若不存在，独立数据库互不共用） ==" -ForegroundColor Cyan
foreach ($s in $services) {
    $envPath = Join-Path (Join-Path $repoRoot $s.Dir) ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        Set-Content -LiteralPath $envPath -Value (Get-EnvContent -Code $s.Code) -Encoding ASCII
        Write-Host ("[ENV ] 新建 {0}" -f $envPath)
        continue
    }
    $missing = @(Get-EnvMissingKeys -Path $envPath -Code $s.Code)
    if ($missing.Count -gt 0) {
        $backup = "{0}.bak-{1}" -f $envPath, (Get-Date -Format "yyyyMMdd-HHmmss")
        Copy-Item -LiteralPath $envPath -Destination $backup -Force
        Set-Content -LiteralPath $envPath -Value (Get-EnvContent -Code $s.Code) -Encoding ASCII
        Write-Host ("[ENV ] 键名不匹配，已重写 {0}（缺失：{1}；原文件备份至 {2}）" `
            -f $envPath, ($missing -join ", "), $backup) -ForegroundColor Yellow
    } else {
        Write-Host ("[ENV ] 已存在且键名齐全，沿用 {0}" -f $envPath)
    }
}

# ---------- 5. 每服务一个后台窗口启动 uvicorn（用 venv 解释器） ----------
Write-Host "== 启动四个服务（各占一个最小化窗口，点开可看日志） ==" -ForegroundColor Cyan
$startedPids = @()
foreach ($s in $services) {
    $workDir = Join-Path $repoRoot $s.Dir
    $inner = "Set-Location -LiteralPath '{0}'; " -f $workDir
    $inner += "Write-Host '== {0}-{1} (端口 {2}) ==' -ForegroundColor Green; " -f `
        $s.Code, $s.Title, $s.Port
    $inner += "& '{0}' -m uvicorn src.main:app --host 127.0.0.1 --port {1}" -f `
        $venvPython, $s.Port
    $encoded = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($inner))
    $proc = Start-Process powershell `
        -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded) `
        -WindowStyle Minimized -PassThru
    $startedPids += $proc.Id
    Write-Host ("[RUN ] {0}-{1} 窗口 PID {2} 端口 {3}" -f `
        $s.Code, $s.Title, $proc.Id, $s.Port)
}

# ---------- 6. 轮询 /health 直到全部 UP（60s 超时） ----------
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
    $startedPids | Set-Content $pidFile
    exit 1
}

# ---------- 7. 启动统一入口（静态 web/ + 反代 /a /b /c /d） ----------
$webReady = $false
if (-not $NoWeb) {
    Write-Host ("== 启动统一入口 {0}（静态看板 + /a /b /c /d 反代） ==" -f $webPort) -ForegroundColor Cyan
    $devServer = Join-Path $repoRoot "scripts\dev_server.py"
    if (-not (Test-Path $devServer)) {
        Write-Host ("[WARN] 未找到 {0}，跳过统一入口。" -f $devServer) -ForegroundColor Yellow
    } else {
        # 端口占用预检：若已被非 dev_server 进程占用（如 Jupyter），给出明确指引
        $occupied = @()
        try {
            $occupied = @(Get-NetTCPConnection -LocalPort $webPort -State Listen `
                -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -Unique)
        } catch { }
        $foreign = @($occupied | Where-Object {
            -not (Test-ProcessCommandLine -ProcId $_ -Pattern "dev_server\.py") })
        if ($foreign.Count -gt 0) {
            Write-Host ("[ERR ] 端口 {0} 已被其它程序占用（PID {1}），本脚本不会强杀它。" -f `
                $webPort, ($foreign -join ", ")) -ForegroundColor Red
            Write-Host ("        请换一个端口启动，例如：-WebPort 8889") -ForegroundColor Yellow
            $startedPids | Set-Content $pidFile
            exit 1
        }
        $webInner = "Set-Location -LiteralPath '{0}'; " -f $repoRoot
        $webInner += "Write-Host '== 统一入口 (端口 {0}) ==' -ForegroundColor Green; " -f $webPort
        $webInner += "& '{0}' '{1}' --port {2}" -f $venvPython, $devServer, $webPort
        $webEncoded = [Convert]::ToBase64String(
            [Text.Encoding]::Unicode.GetBytes($webInner))
        $webProc = Start-Process powershell `
            -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $webEncoded) `
            -WindowStyle Minimized -PassThru
        $startedPids += $webProc.Id
        Write-Host ("[RUN ] 统一入口 窗口 PID {0} 端口 {1}" -f $webProc.Id, $webPort)
        # 等统一入口就绪（经它访问 A 的 /health，验证静态与反代两条路都对）
        $webDeadline = (Get-Date).AddSeconds(20)
        while ((Get-Date) -lt $webDeadline) {
            try {
                $probe = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/a/health" -f $webPort) -TimeoutSec 2
                if ($probe.status -eq "UP") { $webReady = $true; break }
            } catch { }
            Start-Sleep -Milliseconds 500
        }
        if ($webReady) {
            Write-Host ("[OK  ] 统一入口 (端口 {0}) UP，/a/health 经反代可达" -f $webPort) -ForegroundColor Green
        } else {
            Write-Host ("[WARN] 统一入口 {0} 未在 20s 内就绪，请点开其窗口查看报错。" -f $webPort) -ForegroundColor Yellow
        }
    }
}
$startedPids | Set-Content $pidFile
# 记下本次入口端口，供不带参数的 -Stop 精确停止（不误伤同端口的其它程序）
$webPort | Set-Content $webPortFile

# ---------- 8. 汇总 ----------
Write-Host ""
Write-Host "四服务全部 UP：" -ForegroundColor Green
foreach ($s in $services) {
    $h = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/health" -f $s.Port)
    Write-Host ("  {0} {1} -> {2}" -f $s.Code, $s.Title, ($h | ConvertTo-Json -Compress))
}
Write-Host ""
if ($webReady) {
    Write-Host ("打开看板：http://127.0.0.1:{0}/" -f $webPort) -ForegroundColor Green
    Write-Host "（统一入口与服务器 nginx 同口径：/a /b /c /d 已反代，页面默认地址无需修改）"
} elseif (-not $NoWeb) {
    Write-Host ("统一入口未就绪；可手动在浏览器打开 web\index.html，" -f $webPort) -ForegroundColor Yellow
    Write-Host ("但需把四个服务地址框改成 http://127.0.0.1:810x 直连。" ) -ForegroundColor Yellow
} else {
    Write-Host "已用 -NoWeb 跳过统一入口。四服务直连地址：http://127.0.0.1:8101~8104"
}
Write-Host ""
Write-Host ("停止命令：powershell -ExecutionPolicy Bypass -File `"{0}`" -Stop" -f `
    (Join-Path $PSScriptRoot "start_all.ps1"))
