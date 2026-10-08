#Requires -Version 5.1
<#
  Bootstrap a fresh Windows dev machine for bike-crm-api.
  Usage (from repo root):
    powershell -ExecutionPolicy Bypass -File scripts\setup-new-pc.ps1
    powershell -ExecutionPolicy Bypass -File scripts\setup-new-pc.ps1 -EnvFile "F:\path\to\.env"
#>
param(
    [string]$EnvFile = ""
)

# NB: PS 5.1 throws NativeCommandError on native-command stderr when Stop - keep Continue,
# exit codes are checked explicitly via $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

function Fail($msg) {
    Write-Host "[FAIL] $msg" -ForegroundColor Red
    exit 1
}
function Step($msg) {
    Write-Host "==> $msg" -ForegroundColor Cyan
}
function Ok($msg) {
    Write-Host "    OK: $msg" -ForegroundColor Green
}
function Warn($msg) {
    Write-Host "    WARN: $msg" -ForegroundColor Yellow
}

# --- 1. Prerequisites -------------------------------------------------------
Step "Checking prerequisites (git, docker)..."

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "Git not found. Install: winget install --id Git.Git -e --source winget"
}
Ok "git found"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker not found. Install: winget install --id Docker.DockerDesktop -e --source winget (then reboot)"
}
try {
    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "daemon not running" }
} catch {
    Fail "Docker daemon is not running. Start Docker Desktop and retry."
}
Ok "docker running"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Warn "Node.js not found (optional, needed for 'npx tsc'). Install: winget install --id OpenJS.NodeJS.LTS"
}

if (-not (Test-Path (Join-Path $root ".git"))) {
    Fail "Not a git repository: $root. Run from the cloned repo root."
}

# --- 2. .env ----------------------------------------------------------------
Step "Preparing .env..."
$envPath = Join-Path $root ".env"
if (Test-Path $envPath) {
    Ok ".env already exists"
} elseif ($EnvFile -ne "") {
    if (-not (Test-Path $EnvFile)) { Fail "EnvFile not found: $EnvFile" }
    Copy-Item $EnvFile $envPath
    Ok ".env copied from $EnvFile"
} else {
    $legacy = "F:\Github\bike-crm-api\.env"
    if (Test-Path $legacy) {
        Copy-Item $legacy $envPath
        Ok ".env copied from $legacy"
    } else {
        Copy-Item (Join-Path $root ".env.example") $envPath
        Warn ".env created from .env.example - integrations (Avito/Telegram/Email) stay disabled until you fill in secrets"
    }
}

# --- 3. Ports ---------------------------------------------------------------
Step "Checking ports (3000, 8000, 5433, 6380)..."
# Docker Desktop (WSL2 backend) itself proxies published ports via wslrelay/wslservice - ignore those
$ignore = @("wslrelay", "wslservice", "com.docker.backend", "com.docker.build", "vmmemWSL")
$ports = @(3000, 8000, 5433, 6380)
foreach ($p in $ports) {
    $busy = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $p } |
        ForEach-Object {
            $procName = (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName
            if ($procName -and ($ignore -notcontains $procName)) {
                [pscustomobject]@{ Port = $p; Name = $procName; Pid = $_.OwningProcess }
            }
        }
    if ($busy) {
        Fail "Port $($busy[0].Port) is busy ($($busy[0].Name), pid $($busy[0].Pid)). Free the port or change *_PORT in .env"
    }
}
Ok "ports are free (or taken by Docker itself)"

# --- 4. Build & up ----------------------------------------------------------
Step "Building and starting the stack (docker compose up -d --build)..."
Push-Location $root
try {
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed" }

    # --- 5. Migrations ------------------------------------------------------
    Step "Running database migrations..."
    $deadline = (Get-Date).AddSeconds(90)
    $dbReady = $false
    while ((Get-Date) -lt $deadline) {
        docker compose exec -T postgres pg_isready -U postgres | Out-Null
        if ($LASTEXITCODE -eq 0) { $dbReady = $true; break }
        Start-Sleep -Seconds 3
    }
    if (-not $dbReady) { Fail "Postgres did not become ready in 90s" }
    docker compose exec -T api alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Fail "alembic upgrade failed" }
    Ok "migrations applied"

    # --- 6. Wait for API ----------------------------------------------------
    Step "Waiting for API on :8000..."
    $deadline = (Get-Date).AddSeconds(120)
    $apiUp = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) { $apiUp = $true; break }
        } catch { Start-Sleep -Seconds 3 }
    }
    if (-not $apiUp) { Warn "API not answering yet - check: docker compose logs api" } else { Ok "API is up" }
}
finally {
    Pop-Location
}

# --- 7. Summary -------------------------------------------------------------
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
Write-Host "  CRM:      http://localhost:3000"
Write-Host "  Register: http://localhost:3000/register   (FIRST user on a fresh DB becomes admin)"
Write-Host "  API docs: http://localhost:8000/docs"
Write-Host ""
Write-Host "  Stop:     docker compose stop"
Write-Host "  Rebuild:  docker compose up -d --build"
Write-Host "  Typecheck: cd frontend; npx tsc --noEmit"
