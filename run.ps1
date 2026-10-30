# Isonomy project runner (ASCII only, so Windows PowerShell 5.1 can parse it)
# Usage: .\run.ps1
# Does four things: self-check -> build site -> read ledger -> print verdict
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== 1/3 invariant check ==" -ForegroundColor Cyan
python engine\check.py
$checkExit = $LASTEXITCODE

Write-Host ""
Write-Host "== 2/3 build static site ==" -ForegroundColor Cyan
python engine\sitegen.py

Write-Host ""
Write-Host "== 3/3 ledger verdict ==" -ForegroundColor Cyan
$ledgerPath = "data\ledger.csv"
if (Test-Path $ledgerPath) {
    python engine\ledger.py $ledgerPath
    $ledgerExit = $LASTEXITCODE
} else {
    Write-Host "missing $ledgerPath"
    $ledgerExit = 2
}

Write-Host ""
if ($checkExit -ne 0) {
    Write-Host ">>> MODEL CHECK FAILED: fix the code first, do not scale." -ForegroundColor Red
    exit 1
}
switch ($ledgerExit) {
    0 { Write-Host ">>> CONTINUE: gates allow progress." -ForegroundColor Green }
    1 { Write-Host ">>> FIX: model or scaling broken, do not add money." -ForegroundColor Yellow }
    2 { Write-Host ">>> KILL/EMPTY: pass V1 first (one real payment)." -ForegroundColor Red }
}
exit $ledgerExit
