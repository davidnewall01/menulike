
# =============================================================================
# Menulike -- Production Deployment Script
# =============================================================================
#
# Usage:
#   First ever deploy (empty prod DB, nothing to back up):
#     .\scripts\deploy_production.ps1 -FirstDeploy
#
#   Normal deploy (existing prod DB with real data):
#     1. (optional) $env:DATABASE_URL = "postgresql://..."
#     2. .\scripts\deploy_production.ps1
#
# Steps (normal):     backup DB → migrate → push to Railway → cleanup
# Steps (-FirstDeploy): migrate empty DB → push to Railway → cleanup (NO backup)
#
# Requires: pg_dump, alembic, git   (psql not needed for production deploys)
# =============================================================================

[CmdletBinding()]
param(
    # Skip the backup step for the very first deploy against a brand-new empty DB.
    [switch]$FirstDeploy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$BackupsDir = Join-Path $PSScriptRoot "backups"
$LogFile    = Join-Path $BackupsDir "deploy_log.txt"

# --- Logging ----------------------------------------------------------------

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "[$timestamp] [$Level] $Message"

    if (-not (Test-Path $BackupsDir)) {
        New-Item -ItemType Directory -Path $BackupsDir -Force | Out-Null
    }
    try { Add-Content -Path $LogFile -Value $entry -ErrorAction Stop }
    catch { <# logging is best-effort -- don't crash the deploy #> }

    switch ($Level) {
        "ERROR" { Write-Host $entry -ForegroundColor Red }
        "WARN"  { Write-Host $entry -ForegroundColor Yellow }
        "OK"    { Write-Host $entry -ForegroundColor Green }
        default { Write-Host $entry }
    }
}

function Confirm-Step {
    param([string]$Prompt)
    $response = Read-Host "$Prompt (y/N)"
    if ($response -ne "y") {
        Write-Log "User declined: $Prompt" "WARN"
        Write-Host "Deployment aborted." -ForegroundColor Yellow
        exit 0
    }
}

# --- Header -----------------------------------------------------------------

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Menulike Production Deployment" -ForegroundColor Cyan
if ($FirstDeploy) {
    Write-Host "  *** FIRST DEPLOY MODE (empty DB, no backup) ***" -ForegroundColor Yellow
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- DATABASE_URL -----------------------------------------------------------

if (-not $env:DATABASE_URL) {
    Write-Host "DATABASE_URL is not set." -ForegroundColor Yellow
    Write-Host "Enter the PRODUCTION database URL:" -ForegroundColor Gray
    $dbUrl = (Read-Host "postgresql://...").Trim()
    if (-not $dbUrl) {
        Write-Host "No URL provided. Aborted." -ForegroundColor Red
        exit 1
    }
    $env:DATABASE_URL = $dbUrl
}

# Mask password in display/logs
$displayUrl = $env:DATABASE_URL -replace '://([^:]+):([^@]+)@', '://$1:****@'
Write-Log "DATABASE_URL target: $displayUrl"

# --- Preflight: required tools ----------------------------------------------
# pg_dump only required when we actually back up (i.e. NOT first deploy).

$requiredTools = @("alembic", "git")
if (-not $FirstDeploy) { $requiredTools += "pg_dump" }

foreach ($tool in $requiredTools) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Log "$tool not found in PATH -- cannot proceed" "ERROR"
        exit 1
    }
}
Write-Log "Preflight checks passed" "OK"
Write-Host ""

# === Step 1: Backup DB (skipped on first deploy) ============================

$backupFile = $null

if ($FirstDeploy) {
    Write-Host "--- Step 1: Backup (SKIPPED -- first deploy, empty DB) ---" -ForegroundColor Cyan
    Write-Log "First deploy: skipping backup (nothing to back up on a new DB)" "WARN"
    Write-Host ""
}
else {
    Write-Host "--- Step 1: Database Backup ---" -ForegroundColor Cyan
    $backupResponse = Read-Host "Backup production database? (y/N)"
    if ($backupResponse -ne "y") {
        Write-Log "User skipped backup -- proceeding without backup" "WARN"
        Write-Host ""
    }
    else {

    if (-not (Test-Path $BackupsDir)) {
        New-Item -ItemType Directory -Path $BackupsDir -Force | Out-Null
        Write-Log "Created backups directory"
    }

    $backupFile = Join-Path $BackupsDir ("menulike_backup_{0}.sql" -f (Get-Date -Format "yyyy-MM-dd_HH-mm"))
    Write-Log "Running pg_dump to $backupFile"

    try {
        $ErrorActionPreference = "Continue"
        & pg_dump $env:DATABASE_URL --file=$backupFile --no-owner --no-acl 2>&1
        $pgExitCode = $LASTEXITCODE
        $ErrorActionPreference = "Stop"
        if ($pgExitCode -ne 0) { throw "pg_dump exited with code $pgExitCode" }

        $sizeKB = [math]::Round((Get-Item $backupFile).Length / 1KB, 1)
        Write-Log "Backup complete: $backupFile `($sizeKB KB`)" "OK"
    }
    catch {
        Write-Log "Backup FAILED: $_" "ERROR"
        Write-Host "Deployment aborted -- database was NOT modified." -ForegroundColor Red
        exit 1
    }

    # Cleanup old backups -- keep last 5
    $backups = @(Get-ChildItem $BackupsDir -Filter "menulike_backup_*.sql" | Sort-Object LastWriteTime -Descending)
    if ($backups.Count -gt 5) {
        $toRemove = $backups | Select-Object -Skip 5
        foreach ($old in $toRemove) {
            Remove-Item $old.FullName -Force
            Write-Log "Removed old backup: $($old.Name)"
        }
    }
    Write-Host ""

    } # end else (backup accepted)
}

# === Step 2: Run Migration ===================================================

Write-Host "--- Step 2: Alembic Migration ---" -ForegroundColor Cyan
if ($FirstDeploy) {
    Write-Host "  (Empty DB -- migrations build the schema from scratch)" -ForegroundColor Gray
}
Confirm-Step "Run alembic upgrade head against PRODUCTION?"

Write-Log "Running alembic upgrade head"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $projectRoot
try {
    $ErrorActionPreference = "Continue"
    $migrationOutput = & alembic upgrade head 2>&1
    $migrationExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    $migrationOutput = ($migrationOutput | Out-String)
    if ($migrationExitCode -ne 0) { throw "alembic exited with code $migrationExitCode" }

    $migrationOutput.Trim().Split("`n") | ForEach-Object {
        Write-Log "  alembic: $_"
    }
    Write-Log "Migration complete" "OK"
}
catch {
    Write-Log "Migration FAILED: $_" "ERROR"
    Write-Host ""
    Write-Host "Migration failed -- push will NOT proceed." -ForegroundColor Red
    if ($backupFile) {
        Write-Host "Backup available at: $backupFile" -ForegroundColor Yellow
        Write-Host ('To restore: psql $env:DATABASE_URL < ' + $backupFile) -ForegroundColor Yellow
    }
    exit 1
}
finally {
    Pop-Location
}
Write-Host ""

# === Step 3: Push to Railway =================================================

Write-Host "--- Step 3: Push to Railway ---" -ForegroundColor Cyan

$currentBranch = (git rev-parse --abbrev-ref HEAD 2>&1).Trim()
$aheadCount = (git rev-list --count "origin/main..HEAD" 2>&1).Trim()
Write-Log "Current branch: $currentBranch `($aheadCount commits ahead of origin/main`)"

# Warn if not on main
if ($currentBranch -ne "main") {
    Write-Host ""
    Write-Host "  *** WARNING ***" -ForegroundColor Yellow
    Write-Host "  You are on branch '$currentBranch', not 'main'." -ForegroundColor Yellow
    Write-Host "  Production deployments should only be made from 'main'." -ForegroundColor Yellow
    Write-Host "  Make sure you have merged your changes into main before proceeding." -ForegroundColor Yellow
    Write-Host ""
    Confirm-Step "Continue deploying non-main branch '$currentBranch' to PRODUCTION?"
}

Confirm-Step "Push $currentBranch to origin main?"

try {
    $ErrorActionPreference = "Continue"
    $pushOutput = & git push origin "${currentBranch}:main" 2>&1
    $pushExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    $pushOutput = ($pushOutput | Out-String)
    if ($pushExitCode -ne 0) { throw "git push exited with code $pushExitCode" }

    Write-Log "Push complete" "OK"
}
catch {
    Write-Log "Push FAILED: $_" "ERROR"
    Write-Host "Migration was already applied. You may need to push manually." -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# === Step 4: Cleanup =========================================================

Write-Host "--- Step 4: Cleanup ---" -ForegroundColor Cyan
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
Write-Log "DATABASE_URL cleared from environment"
Write-Log "Deployment complete" "OK"

# === Post-deploy checklist (menulike-specific) ==============================

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Deployment complete" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Post-deploy checklist:" -ForegroundColor Yellow
Write-Host "  1. Wait 2-3 min for Railway to build and deploy." -ForegroundColor Gray
Write-Host "  2. Confirm Railway env vars are set (esp. boot-critical):" -ForegroundColor Gray
Write-Host "       ENVIRONMENT=production" -ForegroundColor Gray
Write-Host "       JWT_SECRET_KEY=<strong random, NOT the dev sentinel>" -ForegroundColor Gray
Write-Host "       DATABASE_URL=<Railway Postgres>" -ForegroundColor Gray
Write-Host "       PLATFORM_BASE_DOMAIN=<your prod base domain>" -ForegroundColor Gray
Write-Host "       AWS_* / S3_* / ANTHROPIC_API_KEY / GOOGLE_MAPS_API_KEY" -ForegroundColor Gray
Write-Host "  3. Confirm GOOGLE_MAPS_API_KEY is the RESTRICTED key (referrer + Places API)." -ForegroundColor Gray
Write-Host "  4. Hit /health -- expect 200." -ForegroundColor Gray
Write-Host "  5. Open the platform subdomain, confirm a page renders (no 500)." -ForegroundColor Gray
Write-Host "  6. Log into admin; confirm dashboard + a content page render styled (admin.css served)." -ForegroundColor Gray
Write-Host "  7. Confirm S3: a photo loads on a public/admin page (bucket public-read policy in place)." -ForegroundColor Gray
Write-Host "  8. Check Railway deploy logs for errors." -ForegroundColor Gray
Write-Host ""
