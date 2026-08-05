<#
.SYNOPSIS
    One-command deploy of the production stack on this machine.

.DESCRIPTION
    Pull → build → back up the database → restart → health check, with an
    automatic rollback to the previous images if the stack doesn't come up.

    This is the CD half of the pipeline. It is deliberately *local*: the box
    sits behind a Cloudflare Tunnel with no inbound ports, so GitHub's cloud
    runners cannot reach it. CI proves the commit is good; this script ships it.

    See docs/ci-cd.md for the full flow.

.PARAMETER SkipPull
    Deploy the working tree as-is, without `git pull`.

.PARAMETER SkipBackup
    Skip the SQLite backup. Don't use this on a normal deploy.

.PARAMETER TimeoutSeconds
    How long to wait for /api/health before declaring failure and rolling back.

.EXAMPLE
    .\deploy.ps1

.EXAMPLE
    .\deploy.ps1 -SkipPull      # ship local changes without pulling
#>
#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$SkipPull,
    [switch]$SkipBackup,
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$Compose  = 'docker-compose.prod.yml'
$Services = @('smartlearning-backend', 'smartlearning-frontend')
$HealthUrl = 'http://127.0.0.1/api/health'

function Write-Step  { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok    { param($m) Write-Host "    OK  $m" -ForegroundColor Green }
function Write-Warn2 { param($m) Write-Host "    !   $m" -ForegroundColor Yellow }
function Fail        { param($m) Write-Host "`nFAILED: $m" -ForegroundColor Red; exit 1 }

# --- 1. Preflight ------------------------------------------------------------
Write-Step '1/7 Preflight'

docker info *> $null
if (-not $?) { Fail 'Docker is not running. Start Docker Desktop and retry.' }
Write-Ok 'Docker is up'

if (-not (Test-Path '.env.cloud')) {
    Fail '.env.cloud is missing. Copy .env.cloud.example and fill it in.'
}
Write-Ok '.env.cloud present'

# The dev uvicorn and the container share one SQLite file. Two writers corrupt it.
$devApi = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($devApi) {
    $owner = Get-Process -Id $devApi[0].OwningProcess -ErrorAction SilentlyContinue
    if ($owner -and $owner.ProcessName -notmatch 'docker|com.docker') {
        Fail "Something else is on :8000 ($($owner.ProcessName), pid $($owner.Id)) — likely the dev server. Stop it first; it shares the SQLite file."
    }
}
Write-Ok 'No dev server holding the database'

# --- 2. Pull -----------------------------------------------------------------
Write-Step '2/7 Source'
if ($SkipPull) {
    Write-Warn2 'Skipping git pull (-SkipPull); deploying the working tree'
} else {
    git pull --ff-only
    if (-not $?) { Fail 'git pull failed (diverged branch? local edits?). Resolve, then retry.' }
    Write-Ok 'Up to date with origin'
}
$sha = (git rev-parse --short HEAD).Trim()
Write-Ok "Deploying $sha"

# --- 3. Tag rollback images --------------------------------------------------
# Must happen BEFORE the build: the build overwrites the :latest tag, and this
# extra tag is the only thing keeping the previous image from being pruned.
Write-Step '3/7 Tagging current images as :rollback'
$rollbackReady = $true
foreach ($svc in $Services) {
    docker image inspect "${svc}:latest" *> $null
    if ($?) {
        docker tag "${svc}:latest" "${svc}:rollback"
        Write-Ok "${svc}:rollback"
    } else {
        Write-Warn2 "no existing ${svc}:latest — first deploy, nothing to roll back to"
        $rollbackReady = $false
    }
}

# --- 4. Build ----------------------------------------------------------------
# Built while the old stack is still serving, so downtime starts at step 5.
Write-Step '4/7 Building images'
docker compose -f $Compose build
if (-not $?) { Fail 'Image build failed. Old stack is untouched and still running.' }
Write-Ok 'Images built'

# --- 5. Stop + back up -------------------------------------------------------
Write-Step '5/7 Stopping stack and backing up the database'
docker compose -f $Compose down
Write-Ok 'Stack stopped'

if ($SkipBackup) {
    Write-Warn2 'Skipping backup (-SkipBackup)'
} else {
    $db = 'backend/data/smartlearning.db'
    if (Test-Path $db) {
        # Copy with the stack down, so it is guaranteed consistent — and before
        # `up`, which runs `alembic upgrade head` and may migrate the schema.
        $stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
        $backup = "$db.backup-$stamp"
        Copy-Item $db $backup
        Write-Ok "Backed up to $backup"

        # Keep the 10 most recent; older ones are noise.
        Get-ChildItem 'backend/data' -Filter 'smartlearning.db.backup-*' |
            Sort-Object LastWriteTime -Descending |
            Select-Object -Skip 10 |
            Remove-Item -Force -ErrorAction SilentlyContinue
    } else {
        Write-Warn2 "No database at $db yet — nothing to back up"
    }
}

# --- 6. Start ----------------------------------------------------------------
Write-Step '6/7 Starting stack'
docker compose -f $Compose up -d --remove-orphans
if (-not $?) { Fail 'docker compose up failed.' }
Write-Ok 'Containers started'

# --- 7. Health check ---------------------------------------------------------
Write-Step "7/7 Waiting for $HealthUrl (up to ${TimeoutSeconds}s)"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$healthy  = $false
while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -eq 200) { $healthy = $true; break }
    } catch {
        # nginx or the backend isn't accepting connections yet; keep waiting.
    }
    Start-Sleep -Seconds 3
}

if ($healthy) {
    Write-Ok "Healthy — $sha is live"
    Write-Host "`nPublic: https://sl.zz34zz.uk" -ForegroundColor Green
    Write-Host "Logs:   docker compose -f $Compose logs -f backend"
    exit 0
}

# --- Rollback ----------------------------------------------------------------
Write-Host "`n!!! Health check failed after ${TimeoutSeconds}s" -ForegroundColor Red
Write-Host "--- backend logs (last 50) ---" -ForegroundColor Yellow
docker compose -f $Compose logs --tail 50 backend

if (-not $rollbackReady) {
    Fail 'No previous images to roll back to. Stack is up but unhealthy — investigate with the logs above.'
}

Write-Step 'Rolling back to previous images'
docker compose -f $Compose down
foreach ($svc in $Services) {
    docker tag "${svc}:rollback" "${svc}:latest"
}
docker compose -f $Compose up -d
Write-Warn2 'Rolled back to the previous images.'
Write-Warn2 'NOTE: a schema migration that already ran is NOT undone by this.'
Write-Warn2 'If the new version migrated the database, restore the backup from step 5.'
Fail "Deploy of $sha failed and was rolled back."
