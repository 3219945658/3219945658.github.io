# One-command publish (ASCII only: Windows PowerShell 5.1 parses no-BOM files as GBK)
# Usage: .\deploy.ps1 -Remote https://github.com/<user>/<repo>.git -Base https://<user>.github.io
param(
    [Parameter(Mandatory=$true)][string]$Remote,
    [Parameter(Mandatory=$true)][string]$Base,
    [string]$Branch = "main"
)
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== 1/5 rebuild site (base = $Base) ==" -ForegroundColor Cyan
python engine\sitegen.py --base $Base
if ($LASTEXITCODE -ne 0) { throw "sitegen failed" }

Write-Host ""
Write-Host "== 2/5 invariant check ==" -ForegroundColor Cyan
python engine\check.py
if ($LASTEXITCODE -ne 0) { throw "check failed: refuse to deploy" }

Write-Host ""
Write-Host "== 3/5 sync docs (Pages publishes /docs only) ==" -ForegroundColor Cyan
if (Test-Path "docs") { Remove-Item "docs" -Recurse -Force }
Copy-Item "out\site" "docs" -Recurse -Force
New-Item -ItemType File -Path "docs\.nojekyll" -Force | Out-Null
Write-Host ("docs files = " + (Get-ChildItem "docs" -Recurse -File).Count)

Write-Host ""
Write-Host "== 4/5 git commit ==" -ForegroundColor Cyan
if (-not (Test-Path ".git")) { git init | Out-Null }
git checkout -B $Branch | Out-Null
$gname = (git config --get user.name) 2>$null
if (-not $gname) { git config user.name "3219945658" }
$gemail = (git config --get user.email) 2>$null
if (-not $gemail) { git config user.email "3219945658@users.noreply.github.com" }

$ignore = @("__pycache__/", "*.pyc", "out/deliveries/")
Set-Content -Path ".gitignore" -Value $ignore -Encoding ASCII
git add -A
$msg = "site: publish " + (Get-Date -Format "yyyy-MM-dd HH:mm")
git commit -m $msg 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "(nothing new to commit)" }

Write-Host ""
Write-Host "== 5/5 push ==" -ForegroundColor Cyan
$existing = git remote 2>$null
if ($existing -contains "origin") {
    git remote set-url origin $Remote
} else {
    git remote add origin $Remote
}
git push -u origin $Branch 2>&1 | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "PUSH FAILED. Two usual causes:" -ForegroundColor Yellow
    Write-Host "  1) not signed in: run  git config --global credential.helper manager  then retry"
    Write-Host "  2) repo missing: create an empty public repo first (no README)"
    exit 1
}

Write-Host ""
Write-Host ">>> PUSHED." -ForegroundColor Green
Write-Host ">>> Repo -> Settings -> Pages -> Source: Deploy from a branch -> Branch: $Branch -> Folder: /docs -> Save" -ForegroundColor Green
Write-Host ">>> Site: $Base" -ForegroundColor Green
Write-Host ">>> P1 PASS = home page opens AND calc.html computes." -ForegroundColor Green
exit 0
