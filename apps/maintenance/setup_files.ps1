# setup_files.ps1
$ErrorActionPreference = "Stop"

Write-Host "创建空 __init__.py..." -ForegroundColor Green
New-Item src\interfaces\http\__init__.py -Force | Out-Null
New-Item src\interfaces\clients\__init__.py -Force | Out-Null
New-Item tests\__init__.py -Force | Out-Null

Write-Host "删除多余文件..." -ForegroundColor Green
if (Test-Path src\application\event_service.py) {
    Remove-Item src\application\event_service.py -Force
}

Write-Host "创建待填代码的空文件..." -ForegroundColor Green
$files = @(
    "src\interfaces\http\deps.py",
    "src\interfaces\http\work_orders.py",
    "src\interfaces\http\spare_parts.py",
    "src\interfaces\http\integration.py",
    "src\interfaces\clients\member_a.py",
    "src\interfaces\clients\member_b.py",
    "src\interfaces\clients\member_d.py"
)
foreach ($f in $files) {
    if (-not (Test-Path $f)) {
        New-Item $f -Force | Out-Null
        Write-Host "  创建 $f" -ForegroundColor Yellow
    }
}

Write-Host "`n完成！现在用 VS Code 打开项目，把这 7 个文件的代码贴进去。" -ForegroundColor Cyan
Write-Host "代码在之前的回复里，按文件名找。" -ForegroundColor Cyan