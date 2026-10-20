# recover-deploy.ps1 - one-click recovery for the SmartLearning public deployment after a reboot.
#
# Why this is needed:
#   Docker Desktop 4.75.0 on this machine has a socket-cleanup bug. Every unclean
#   exit / reboot leaves a dangling, undeletable AF_UNIX socket reparse point at
#     %LOCALAPPDATA%\Docker\run\dockerInference
#     %LOCALAPPDATA%\docker-secrets-engine\engine.sock
#   On next start Docker tries to remove it, fails ("The file cannot be accessed
#   by the system"), and crashes. Setting EnableDockerAI:false does NOT prevent it.
#
# Workaround:
#   Before starting Docker, move the poisoned socket dirs aside (they can't be
#   deleted, but the parent dir can be renamed). Docker then recreates clean dirs.
#
# Usage (after reboot + login):
#   powershell -ExecutionPolicy Bypass -File D:\Project\smartLearning\recover-deploy.ps1
#
# Note: cloudflared runs as an auto-start Windows service; this script only brings
# the Docker origin back up.

$ErrorActionPreference = 'Continue'
function Say($m) { Write-Host "[recover] $m" }

Say "1/5 Stopping leftover Docker processes + resetting WSL backend..."
Get-Process -EA SilentlyContinue | Where-Object { $_.ProcessName -match 'docker|com\.docker' } |
    Stop-Process -Force -EA SilentlyContinue
Start-Sleep -Seconds 2
wsl.exe --shutdown 2>&1 | Out-Null
Start-Sleep -Seconds 3

Say "2/5 Moving poisoned socket dirs aside (cannot delete, only rename)..."
$suffix = "broken-" + (Get-Date -Format "yyyyMMdd-HHmmss")
foreach ($d in @(
    "$env:LOCALAPPDATA\Docker\run",
    "$env:LOCALAPPDATA\docker-secrets-engine"
)) {
    if (Test-Path -LiteralPath $d) {
        try {
            Rename-Item -LiteralPath $d -NewName ((Split-Path $d -Leaf) + "." + $suffix) -EA Stop
            Say "   moved aside: $d"
        } catch { Say "   skipped ($d): $($_.Exception.Message)" }
    }
}

Say "3/5 Launching Docker Desktop..."
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

Say "4/5 Waiting for engine + containers (up to ~4 min)..."
$up = $false
foreach ($n in 1..24) {
    Start-Sleep -Seconds 10
    $out = & docker ps --format '{{.Names}}' 2>&1
    if ($out -match 'smartlearning-backend') {
        Say "   engine up, containers running (~$($n*10)s)"; $up = $true; break
    }
    Say "   t=$($n*10)s not ready yet..."
}
if (-not $up) {
    Say "Engine still down - it may have crashed again. If a crash dialog appeared with the same socket error, just run this script once more."
    exit 1
}

Say "   waiting for backend health..."
foreach ($n in 1..12) {
    $st = & docker inspect -f '{{.State.Health.Status}}' smartlearning-backend 2>&1
    if ($st -eq 'healthy') { Say "   backend healthy"; break }
    Start-Sleep -Seconds 5
}

Say "5/5 Verifying local + public..."
$local  = (& curl.exe -s -o NUL -w "%{http_code}" --max-time 10 http://127.0.0.1:80/ 2>&1)
$public = (& curl.exe -s -o NUL -w "%{http_code}" --max-time 12 https://sl.zz34zz.uk/ 2>&1)
Say "   local  nginx:80      -> HTTP $local"
Say "   public sl.zz34zz.uk  -> HTTP $public"
if ($public -eq '200') { Say "OK - public site is reachable." }
else { Say "WARN local=$local public=$public. If local is 200 but public isn't, check the tunnel: Get-Service Cloudflared" }
