# Kill whatever holds port 8000, then start uvicorn with auto-reload.
# --reload picks up Python/template edits without a manual restart (dev only).
# Usage: .\scripts\start_service.ps1

$port = 8000

# Kill all processes holding the port (including child processes)
$ps = netstat -ano | Select-String ":$port\s" |
    ForEach-Object { ($_ -split '\s+')[-1] } |
    Sort-Object -Unique |
    Where-Object { $_ -ne '0' }

foreach ($p in $ps) {
    Write-Host "Killing PID $p (holding port $port)"
    # Kill the process tree — uvicorn may have spawned children
    taskkill /F /T /PID $p 2>$null | Out-Null
}

# Wait until port is actually free (up to 10 seconds).
# Windows can hold ghost sockets briefly after the process exits.
for ($i = 0; $i -lt 20; $i++) {
    $still = netstat -ano | Select-String ":$port\s" | Select-String "LISTENING"
    if (-not $still) { break }
    if ($i -eq 0) { Write-Host "Waiting for port $port to free..." }
    Start-Sleep -Milliseconds 500
}

$final = netstat -ano | Select-String ":$port\s" | Select-String "LISTENING"
if ($final) {
    Write-Host "ERROR: port $port still occupied after 10s. Try restarting manually." -ForegroundColor Red
    exit 1
}

uvicorn app.main:app --port $port --reload
