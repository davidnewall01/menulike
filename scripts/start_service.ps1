# Kill whatever holds port 8000, then start uvicorn with auto-reload.
# --reload picks up Python/template edits without a manual restart (dev only).
# Usage: .\scripts\start_service.ps1

$port = 8000

# Kill any lingering python processes (uvicorn + children) to free the port
$procs = Get-Process python* -ErrorAction SilentlyContinue
if ($procs) {
    Write-Host "Killing $($procs.Count) python process(es)..."
    $procs | Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

uvicorn app.main:app --port $port --reload
