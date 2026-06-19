# Reset dev: stop server, run migrations, seed, start server.
# Usage: .\scripts\reset_dev.ps1

$port = 8000

# --- Stop server ---
$ps = netstat -ano | Select-String ":$port\s" |
    ForEach-Object { ($_ -split '\s+')[-1] } |
    Sort-Object -Unique |
    Where-Object { $_ -ne '0' }

foreach ($p in $ps) {
    Write-Host "Killing PID $p (holding port $port)"
    taskkill /F /PID $p 2>$null | Out-Null
}
Start-Sleep -Seconds 1

# --- Migrations ---
Write-Host ""
Write-Host "--- Running migrations ---"
alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host "Migration failed - aborting." -ForegroundColor Red
    exit 1
}

# --- Seed ---
Write-Host ""
Write-Host "--- Seeding Porto Azzurro ---"
python -m scripts.seed_porto_azzurro
if ($LASTEXITCODE -ne 0) {
    Write-Host "Seed (Porto) failed - aborting." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "--- Seeding admin users ---"
python -m scripts.seed_admin_users
if ($LASTEXITCODE -ne 0) {
    Write-Host "Seed (users) failed - aborting." -ForegroundColor Red
    exit 1
}

# --- Start server ---
Write-Host ""
Write-Host "--- Starting uvicorn on port $port ---"
uvicorn app.main:app --port $port
