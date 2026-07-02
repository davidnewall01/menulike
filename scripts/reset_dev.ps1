# Reset dev: stop server, drop DB, run migrations, seed, start server.
# Usage: .\scripts\reset_dev.ps1

$port = 8000
$env:PGPASSWORD = "menulike"
$pgArgs = @("-U", "menulike", "-h", "localhost", "-p", "5433")

# --- Stop server ---
$procs = Get-Process python* -ErrorAction SilentlyContinue
if ($procs) {
    Write-Host "Killing $($procs.Count) python process(es)..."
    $procs | Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

# --- Drop & recreate DB ---
Write-Host ""
Write-Host "--- Dropping and recreating database ---"

# Terminate all other connections to the DB first
psql @pgArgs -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'menulike' AND pid <> pg_backend_pid();" 2>$null | Out-Null

psql @pgArgs -d postgres -c "DROP DATABASE IF EXISTS menulike;"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Drop failed - aborting." -ForegroundColor Red
    exit 1
}

psql @pgArgs -d postgres -c "CREATE DATABASE menulike;"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Create failed - aborting." -ForegroundColor Red
    exit 1
}

Write-Host "Database recreated."

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
Write-Host "--- Seeding Kin ---"
python -m scripts.seed_kin
if ($LASTEXITCODE -ne 0) {
    Write-Host "Seed (Kin) failed - aborting." -ForegroundColor Red
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
