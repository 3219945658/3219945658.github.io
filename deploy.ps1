# One-command publish (ASCII only: Windows PowerShell 5.1 parses no-BOM files as GBK)
# Usage: .\deploy.ps1 -Remote https://github.com/<user>/<repo>.git -Base https://<user>.github.io
param(
    [Parameter(Mandatory=$true)][string]$Remote,
    [Parameter(Mandatory=$true)][string]$Base,
    [string]$Branch = "main"
)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# ---------- python phase: hard fail on any error ----------
$ErrorActionPreference = "Stop"

Write-Host "== 1/5 rebuild site (base = $Base) ==" -ForegroundColor Cyan
python engine\sitegen.py --base $Base
if ($LASTEXITCODE -ne 0) { throw "sitegen failed" }

Write-Host ""
Write-Host "== 2/5 invariant check ==" -ForegroundColor Cyan
python engine\check.py
if ($LASTEXITCODE -ne 0) { throw "check failed: refuse to deploy" }

Write-Host ""
Write-Host "== 3/5 sync site to repo root (Pages is already serving / root) ==" -ForegroundColor Cyan
Get-ChildItem "out\site" -File | ForEach-Object { Copy-Item $_.FullName (Join-Path $root $_.Name) -Force }
New-Item -ItemType File -Path ".nojekyll" -Force | Out-Null
if (Test-Path "docs") { Remove-Item "docs" -Recurse -Force }
Write-Host ("root html files = " + (Get-ChildItem $root -Filter *.html -File).Count)

# ---------- git phase: git writes progress to stderr, so never let that throw ----------
$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "== 4/5 git commit ==" -ForegroundColor Cyan
if (-not (Test-Path ".git")) { git init 2>&1 | Out-Null }
git checkout -B $Branch 2>&1 | Out-Null

$gname = (git config --get user.name) 2>$null
if (-not $gname) { git config user.name "3219945658"; $gname = "3219945658" }
$gemail = (git config --get user.email) 2>$null
if (-not $gemail) { git config user.email "3219945658@users.noreply.github.com"; $gemail = "3219945658@users.noreply.github.com" }

$ignore = @("__pycache__/", "*.pyc", "out/deliveries/")
Set-Content -Path ".gitignore" -Value $ignore -Encoding ASCII
git add -A 2>&1 | Out-Null

$hasCommit = (git rev-parse --verify HEAD 2>$null)
if (-not $hasCommit) {
    git commit -m ("site: first publish " + (Get-Date -Format "yyyy-MM-dd HH:mm")) 2>&1 | Out-Null
} else {
    git commit -m ("site: publish " + (Get-Date -Format "yyyy-MM-dd HH:mm")) 2>&1 | Out-Null
}

Write-Host ""
Write-Host "== 5/5 push ==" -ForegroundColor Cyan
$existing = git remote 2>$null
if ($existing -contains "origin") {
    git remote set-url origin $Remote 2>&1 | Out-Null
} else {
    git remote add origin $Remote 2>&1 | Out-Null
}

# If the remote already has history (e.g. an auto-created README), merge it
# without touching our tree: -s ours keeps every file we generated.
git fetch origin $Branch 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    $behind = (git rev-list --count "HEAD..origin/$Branch" 2>$null)
    if ($behind -and [int]$behind -gt 0) {
        Write-Host ("remote has " + $behind + " commit(s) we do not have; merging with -s ours (our tree wins)")
        git merge -s ours "origin/$Branch" --allow-unrelated-histories -m "merge: keep generated site tree" 2>&1 | Out-Null
    }
}

$pushLog = (git push -u origin $Branch 2>&1 | Out-String)
$pushCode = $LASTEXITCODE
Write-Host $pushLog

if ($pushCode -ne 0) {
    Write-Host ""
    Write-Host "PUSH FAILED. Two usual causes:" -ForegroundColor Yellow
    Write-Host "  1) not signed in: run  git config --global credential.helper manager  and retry"
    Write-Host "  2) repo missing: create an empty public repo first"
    exit 1
}

Write-Host ""
Write-Host ">>> PUSHED." -ForegroundColor Green
Write-Host ">>> Repo -> Settings -> Pages -> Source: Deploy from a branch -> Branch: $Branch -> Folder: /docs -> Save" -ForegroundColor Green
Write-Host ">>> Site: $Base" -ForegroundColor Green
Write-Host ">>> P1 PASS = home page opens AND calc.html computes." -ForegroundColor Green
exit 0
