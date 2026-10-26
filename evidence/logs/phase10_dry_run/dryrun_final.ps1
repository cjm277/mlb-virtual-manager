# Phase 10, final run: fresh clone of the latest commit, README steps exactly, then USE the web app end to end
# (the assignment's "follow your own README, and use the app"), then the automated tests on the clean clone.
param([string]$root = (Join-Path $env:TEMP 'p10'))
$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot 'phase10_final_log.txt'
if (Test-Path $root) { Remove-Item -Recurse -Force $root }
New-Item -ItemType Directory -Force $root | Out-Null
Copy-Item 'C:\Users\conra\OneDrive\Desktop\AI Foundations\.env' (Join-Path $root '.env')   # one level above the clone
$env:PIP_NO_CACHE_DIR = '1'
Set-Content $log "Phase 10 final dry run on $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ($env:COMPUTERNAME)"
Add-Content $log "Folder: $root (brand new); .env one level above the clone; pip cache disabled; python: $(& python --version 2>&1)"
$t0 = Get-Date
function Step($name, [scriptblock]$cmd, [int]$lines = 6) {
    $s = Get-Date
    Add-Content $log "`n=== $name  (start +$([int]((Get-Date) - $t0).TotalSeconds)s)"
    $out = & $cmd 2>&1 | Out-String
    $code = $LASTEXITCODE
    $d = [math]::Round(((Get-Date) - $s).TotalSeconds, 1)
    Add-Content $log (($out -split "`n" | Where-Object { $_.Trim() -and $_ -notmatch 'NativeCommandError|CategoryInfo|^\s*\+ |^At ' } | Select-Object -Last $lines) -join "`n")
    Add-Content $log "--- exit $code, $d s"
}
Set-Location $root
Step '1. git clone https://github.com/cjm277/mlb-virtual-manager.git' { git clone -q https://github.com/cjm277/mlb-virtual-manager.git } 2
Set-Location (Join-Path $root 'mlb-virtual-manager')
Add-Content $log "commit: $(git log --oneline -1)"
Step '3a. python -m venv .venv' { python -m venv .venv } 2
Step '3b. .venv/Scripts/python -m pip install -r requirements.txt' { .venv/Scripts/python -m pip install -q -r requirements.txt } 2
Step '4. .venv/Scripts/python -m backend.config' { .venv/Scripts/python -m backend.config } 5
Add-Content $log "`n=== 5. .venv/Scripts/python app.py  (start +$([int]((Get-Date) - $t0).TotalSeconds)s)"
$s = Get-Date
$app = Start-Process -FilePath '.venv/Scripts/python.exe' -ArgumentList 'app.py' -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $PSScriptRoot 'p10_app_out.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'p10_app_err.txt')
for ($i = 0; $i -lt 600; $i++) {
    try { if ((Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 'http://127.0.0.1:8000/').StatusCode -eq 200) { break } } catch {}
    Start-Sleep -Milliseconds 100
}
Add-Content $log "app answered after $([math]::Round(((Get-Date) - $s).TotalSeconds, 1)) s"
$setup = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
Add-Content $log "`n##### SETUP TIME (clone -> app answering): $setup s #####"
Step '6. Use the app: open, pick, build, dropdown edit, chat, download packets' { .venv/Scripts/python (Join-Path $PSScriptRoot 'flow.py') } 12
Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
Step '7. Automated tests on the clean clone: .venv/Scripts/python -m pytest -q' { .venv/Scripts/python -m pytest -q -p no:cacheprovider } 4
Add-Content $log "`n##### TOTAL: $([math]::Round(((Get-Date) - $t0).TotalSeconds, 1)) s #####"
Set-Location $PSScriptRoot
Remove-Item (Join-Path $root '.env') -Force
Add-Content $log "(.env copy removed)"
Get-Content $log
