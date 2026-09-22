param(
    [string]$MemberA,
    [string]$MemberB,
    [string]$MemberC,
    [string]$MemberD,
    [switch]$SkipInstall
)

# Keep this PowerShell source ASCII-only. Windows PowerShell 5.1 may decode
# UTF-8 files without a BOM using the system code page, which can corrupt
# non-ASCII string literals and cause parser errors.
$ErrorActionPreference = "Stop"

function Assert-NativeSuccess {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

$RepositoryRoot = git rev-parse --show-toplevel 2>$null
if (-not $RepositoryRoot) {
    throw "Run this script inside a Git repository. Run 'git init' first if needed."
}

Set-Location $RepositoryRoot
Write-Host "Repository root: $RepositoryRoot"

$ProvidedMembers = @($MemberA, $MemberB, $MemberC, $MemberD) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
$ProvidedCount = $ProvidedMembers.Count
if ($ProvidedCount -ne 0 -and $ProvidedCount -ne 4) {
    throw "MemberA, MemberB, MemberC, and MemberD must be provided together."
}

if ($ProvidedCount -eq 4) {
    python scripts/configure_team.py --a $MemberA --b $MemberB --c $MemberC --d $MemberD
    Assert-NativeSuccess "Generate CODEOWNERS"
} else {
    Write-Warning "CODEOWNERS was not generated. Run again with all four GitHub usernames."
}

git config core.hooksPath .githooks
Assert-NativeSuccess "Configure Git hooks"
Write-Host "Repository-local Git hooks enabled."

if (-not $SkipInstall) {
    python -m pip install -r requirements-dev.txt
    Assert-NativeSuccess "Install validation dependencies"
}

python scripts/check_repo.py
Assert-NativeSuccess "Validate repository contracts"
python -m unittest discover -s tests -p "test_*.py"
Assert-NativeSuccess "Run contract tests"

Write-Host ""
Write-Host "Local setup completed. Next steps:"
Write-Host "1. Check the usernames in .github/CODEOWNERS."
Write-Host "2. Commit and push these files."
Write-Host "3. Follow the repository setup guide in docs/ to protect main."
