# Kill whatever holds port 8000, then start uvicorn.
# Usage: .\scripts\dev.ps1

$port = 8000
$ps = netstat -ano | Select-String ":$port\s" |
    ForEach-Object { ($_ -split '\s+')[-1] } |
    Sort-Object -Unique |
    Where-Object { $_ -ne '0' }

foreach ($p in $ps) {
    Write-Host "Killing PID $p (holding port $port)"
    taskkill /F /PID $p 2>$null | Out-Null
}

Start-Sleep -Seconds 1
uvicorn app.main:app --port $port
