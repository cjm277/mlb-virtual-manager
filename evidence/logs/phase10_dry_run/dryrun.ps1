# Phase 10: fresh-clone dry run, following README.md exactly, timed. Run with: powershell -NoProfile -File dryrun.ps1
param([string]$root = (Join-Path $env:TEMP 'p10'))
$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot 'phase10_log.txt'
if (Test-Path $root) { Remove-Item -Recurse -Force $root }
New-Item -ItemType Directory -Force $root | Out-Null
# The graders' layout: .env one folder above the clone (copied from the course root; never printed)
Copy-Item 'C:\Users\conra\OneDrive\Desktop\AI Foundations\.env' (Join-Path $root '.env')
# A fresh machine has no pip cache; don't let this one's cache flatter the time
$env:PIP_NO_CACHE_DIR = '1'
Set-Content $log "Phase 10 fresh-clone dry run on $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ($env:COMPUTERNAME)"
Add-Content $log "Folder: $root (brand new); .env placed one level above the clone; pip cache disabled"
Add-Content $log "python on PATH: $((Get-Command python).Source) $(& python --version 2>&1)"
$t0 = Get-Date
function Step($name, [scriptblock]$cmd) {
    $s = Get-Date
    Add-Content $log "`n=== $name  (start +$([int]((Get-Date) - $t0).TotalSeconds)s)"
    $out = & $cmd 2>&1 | Out-String
    $code = $LASTEXITCODE
    $d = [math]::Round(((Get-Date) - $s).TotalSeconds, 1)
    $tail = ($out -split "`n" | Where-Object { $_.Trim() } | Select-Object -Last 6) -join "`n"
    Add-Content $log $tail
    Add-Content $log "--- exit $code, $d s"
    return $d
}
Set-Location $root
$d1 = Step '1. git clone https://github.com/cjm277/mlb-virtual-manager.git' { git clone https://github.com/cjm277/mlb-virtual-manager.git }
Set-Location (Join-Path $root 'mlb-virtual-manager')
Add-Content $log "`n=== 2. API key: .env is one folder above the clone (README: 'looks for .env in this folder first, then in the folder above'); nothing to copy"
$d3a = Step '3a. python -m venv .venv' { python -m venv .venv }
$d3b = Step '3b. .venv/Scripts/python -m pip install -r requirements.txt' { .venv/Scripts/python -m pip install -r requirements.txt }
$d4 = Step '4. .venv/Scripts/python -m backend.config' { .venv/Scripts/python -m backend.config }
# 5. Start the app exactly as the README says, then wait until it answers
Add-Content $log "`n=== 5. .venv/Scripts/python app.py  (start +$([int]((Get-Date) - $t0).TotalSeconds)s)"
$s = Get-Date
$app = Start-Process -FilePath '.venv/Scripts/python.exe' -ArgumentList 'app.py' -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $PSScriptRoot 'phase10_app_out.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'phase10_app_err.txt')
$ready = $false
for ($i = 0; $i -lt 120; $i++) {
    try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://localhost:8000/'; if ($r.StatusCode -eq 200) { $ready = $true; break } } catch {}
    Start-Sleep -Milliseconds 500
}
$d5 = [math]::Round(((Get-Date) - $s).TotalSeconds, 1)
Add-Content $log "home page http://localhost:8000/ answered 200: $ready, after $d5 s"
$setup = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
Add-Content $log "`n##### SETUP TIME (clone -> app answering): $setup s = $([math]::Round($setup / 60, 1)) min #####"
try {
    $teams = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 'http://localhost:8000/api/teams').Content | ConvertFrom-Json
    Add-Content $log "GET /api/teams: $($teams.teams.Count) teams"
    $games = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 'http://localhost:8000/api/games?team_id=141&opponent_id=111').Content | ConvertFrom-Json
    Add-Content $log "GET /api/games (TOR vs BOS): $($games.Count) games"; $h = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 'http://localhost:8000/api/health').Content | ConvertFrom-Json; Add-Content $log "GET /api/health: ok=$($h.ok), model=$($h.model), api_key_found=$($h.api_key_found)"
} catch { Add-Content $log "API check error: $_" }
Stop-Process -Id $app.Id -Force
Add-Content $log "(app stopped)"
# The README's command-line alternative, which also proves a real plan builds (about 2 cents)
$d6 = Step '6a. .venv/Scripts/python run_plan.py --team TOR --opp BOS --list' { .venv/Scripts/python run_plan.py --team TOR --opp BOS --list }
$d7 = Step '6b. .venv/Scripts/python run_plan.py --team TOR --opp BOS --date 2027-05-03' { .venv/Scripts/python run_plan.py --team TOR --opp BOS --date 2027-05-03 }
$total = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
Add-Content $log "`n##### TOTAL incl. first plan: $total s = $([math]::Round($total / 60, 1)) min #####"
Set-Location $PSScriptRoot
Remove-Item (Join-Path $root '.env') -Force   # don't leave a copy of the key behind
Add-Content $log "(.env copy removed)"
Get-Content $log
