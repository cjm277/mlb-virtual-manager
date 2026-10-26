# Re-measure step 5 of the dry run: how long `.venv/Scripts/python app.py` takes to answer, polling 127.0.0.1
# (the first run polled "localhost" with a 2 s timeout; PowerShell tries IPv6 first, so every poll timed out).
$root = Join-Path $env:TEMP 'p10'
$log = Join-Path $PSScriptRoot 'phase10_log.txt'
Copy-Item 'C:\Users\conra\OneDrive\Desktop\AI Foundations\.env' (Join-Path $root '.env')
Set-Location (Join-Path $root 'mlb-virtual-manager')
# the localhost behaviour itself, for the record
$s = Get-Date
$app = Start-Process -FilePath '.venv/Scripts/python.exe' -ArgumentList 'app.py' -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $PSScriptRoot 'phase10_app_out2.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'phase10_app_err2.txt')
$ready = $false
for ($i = 0; $i -lt 600; $i++) {
    try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 'http://127.0.0.1:8000/'; if ($r.StatusCode -eq 200) { $ready = $true; break } } catch {}
    Start-Sleep -Milliseconds 100
}
$d = [math]::Round(((Get-Date) - $s).TotalSeconds, 1)
$t = Get-Date; try { $null = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 'http://localhost:8000/'; $lh = 'ok' } catch { $lh = "failed: $_" }
$dl = [math]::Round(((Get-Date) - $t).TotalSeconds, 1)
Add-Content $log "`n=== 5 (re-measured). .venv/Scripts/python app.py -> http://127.0.0.1:8000/ answered 200: $ready, after $d s"
Add-Content $log "    (a request to http://localhost:8000/ from PowerShell took $dl s ($lh): it tries IPv6 first, which is why the first poll with a 2 s timeout never succeeded; a browser handles this transparently)"
Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
Set-Location $PSScriptRoot
Remove-Item (Join-Path $root '.env') -Force
Get-Content $log | Select-Object -Last 3
