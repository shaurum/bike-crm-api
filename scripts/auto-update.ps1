#Requires -Version 5.1
<#
  Автообновление CRM на Windows-ПК из GitHub Releases (не через git pull).

  Как работает:
    1. Читает GITHUB_TOKEN из .env (Fine-grained PAT, Contents: Read).
    2. Смотрит последний Release (тег v*) на github.com/shaurum/bike-crm-api.
    3. Если тег новее установленного (.release_tag):
         - режим «auto» (backend/.update_mode) → скачивает zip, раскладывает
           файлы, собирает образы, миграции, перезапуск стека;
         - режим «manual» → только пишет «доступна версия», установка по
           кнопке «Проверить и установить» в CRM (файл backend/.update_requested).

  Состояние: backend/.update_state.json (читает API /api/v1/system/version).

  Ручной запуск:   powershell -ExecutionPolicy Bypass -File scripts\auto-update.ps1
  Принудительно:   ... -Apply   (игнорирует режим manual и защиту от правок)
#>
[CmdletBinding()]
param(
    [switch]$Apply
)

# NB: PS 5.1 кидает NativeCommandError на stderr нативных команд при Stop —
# оставляем Continue и проверяем $LASTEXITCODE явно.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

$stateFile   = Join-Path $root "backend\.update_state.json"
$requestFile = Join-Path $root "backend\.update_requested"
$modeFile    = Join-Path $root "backend\.update_mode"
$logFile     = Join-Path $root "backend\.update.log"
$tagFile     = Join-Path $root ".release_tag"
$lockPath    = Join-Path $env:TEMP "bike-crm-update.lock"
$repoApi     = "https://api.github.com/repos/shaurum/bike-crm-api"

function Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $logFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Read-EnvValue([string]$name) {
    $envPath = Join-Path $root ".env"
    if (-not (Test-Path $envPath)) { return $null }
    foreach ($line in [System.IO.File]::ReadAllLines($envPath)) {
        if ($line -match "^\s*$name\s*=\s*(.*)\s*$") {
            $val = $Matches[1].Trim().Trim('"').Trim("'")
            if ($val -ne "") { return $val }
        }
    }
    return $null
}

function Read-Mode {
    try {
        if (Test-Path $modeFile) {
            $mode = ([System.IO.File]::ReadAllText($modeFile)).Trim()
            if ($mode -eq "auto" -or $mode -eq "manual") { return $mode }
        }
    } catch {}
    return "auto"
}

function Read-CurrentTag {
    try {
        if (Test-Path $tagFile) {
            $tag = ([System.IO.File]::ReadAllText($tagFile)).Trim()
            if ($tag -ne "") { return $tag }
        }
    } catch {}
    return ""
}

function Write-CurrentTag([string]$tag) {
    [System.IO.File]::WriteAllText($tagFile, $tag, (New-Object System.Text.UTF8Encoding($false)))
}

function Write-State([string]$updating, [string]$note, [string]$latestTag, [bool]$available) {
    $localSha = "null"; $localDate = "null"
    if (Test-Path (Join-Path $root ".git")) {
        $short = git rev-parse --short HEAD 2>$null
        if ($short) { $localSha = '"' + $short + '"' }
        $date = git log -1 --format=%cI 2>$null
        if ($date) { $localDate = '"' + $date + '"' }
    }
    $curTag = Read-CurrentTag
    $curTagJson = if ($curTag -ne "") { '"' + $curTag + '"' } else { "null" }
    $remoteJson = if ($latestTag) { '"' + $latestTag + '"' } else { "null" }
    $availJson = if ($available) { "true" } else { "false" }
    $lastCheck = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $mode = Read-Mode
    $json = @"
{
  "current_sha": $localSha,
  "current_date": $localDate,
  "current_tag": $curTagJson,
  "remote_sha": $remoteJson,
  "update_available": $availJson,
  "updating": $updating,
  "last_check": "$lastCheck",
  "auto_update": true,
  "mode": "$mode",
  "note": "$note"
}
"@
    # UTF8 без BOM — json.loads в API не принимает BOM
    [System.IO.File]::WriteAllText($stateFile, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# --- Лок: второй экземпляр просто выходит ------------------------------------
$lock = $null
try {
    $lock = [System.IO.File]::Open(
        $lockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch {
    exit 0
}

try {
    Set-Location $root

    $token = Read-EnvValue "GITHUB_TOKEN"
    if (-not $token) {
        Write-State "false" "нет GITHUB_TOKEN в .env — обновления недоступны" "" $false
        Log "GITHUB_TOKEN не задан"
        exit 0
    }

    # --- Последний релиз ------------------------------------------------------
    $headers = @{
        "Authorization"       = "token $token"
        "Accept"              = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
    }
    try {
        $release = Invoke-RestMethod -Uri "$repoApi/releases/latest" -Headers $headers -TimeoutSec 30
    } catch {
        Write-State "false" "нет связи с GitHub Releases" "" $false
        Log "releases/latest: $($_.Exception.Message)"
        exit 0
    }

    $latestTag = [string]$release.tag_name
    if (-not $latestTag) {
        Write-State "false" "релизов нет" "" $false
        exit 0
    }

    $currentTag = Read-CurrentTag
    $available = ($latestTag -ne $currentTag)
    $mode = Read-Mode
    $requested = Test-Path $requestFile

    if (-not $available -and -not $requested) {
        Write-State "false" "актуальная версия ($latestTag)" $latestTag $false
        exit 0
    }

    $mustApply = $requested -or $Apply -or ($mode -eq "auto")

    if ($available -and -not $mustApply) {
        Write-State "false" "доступна $latestTag — установите вручную (Настройки → Обновление)" $latestTag $true
        exit 0
    }

    # Защита разработки: не затираем несcommitted правки без -Apply
    if ($available -and -not $Apply -and (Test-Path (Join-Path $root ".git"))) {
        $dirty = git status --porcelain 2>$null
        if ($dirty) {
            Write-State "false" "есть локальные изменения — автообновление пропущено (нужен -Apply)" $latestTag $true
            Log "локальные правки, обновление не применено"
            exit 0
        }
    }

    # --- Установка ------------------------------------------------------------
    $asset = $null
    foreach ($a in @($release.assets)) {
        if ($a.name -like "*.zip") { $asset = $a; break }
    }
    if (-not $asset) {
        Write-State "false" "в релизе $latestTag нет zip-артефакта" $latestTag $true
        Log "нет zip-артефакта в $latestTag"
        exit 1
    }

    Write-State "true" "установка $latestTag" $latestTag $true
    Log "установка $latestTag (asset: $($asset.name))"

    $zipPath = Join-Path $env:TEMP "bike-crm-update.zip"
    $extractDir = Join-Path $env:TEMP "bike-crm-update-extract"
    Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $extractDir -ErrorAction SilentlyContinue

    & curl.exe -sS -L `
        -H "Authorization: token $token" `
        -H "Accept: application/octet-stream" `
        -o $zipPath $asset.url
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $zipPath)) {
        Write-State "false" "ошибка скачивания $latestTag" $latestTag $true
        Log "скачивание не удалось"
        exit 1
    }

    try {
        Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force -ErrorAction Stop
    } catch {
        Write-State "false" "ошибка распаковки" $latestTag $true
        Log "распаковка: $($_.Exception.Message)"
        exit 1
    }

    $src = Get-ChildItem $extractDir -Directory | Select-Object -First 1
    if (-not $src) {
        Write-State "false" "пустой архив" $latestTag $true
        exit 1
    }

    # zip собран через git archive — в нём нет .env, data/, .update_*,
    # раскладываем поверх рабочей копии
    & robocopy $src.FullName $root /E /XF ".env" /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) {
        Write-State "false" "ошибка копирования файлов" $latestTag $true
        Log "robocopy failed ($LASTEXITCODE)"
        exit 1
    }

    docker compose build -q 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-State "false" "ошибка сборки образов" $latestTag $true; Log "build failed"; exit 1 }

    docker compose run --rm api alembic upgrade head 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-State "false" "ошибка миграций" $latestTag $true; Log "alembic failed"; exit 1 }

    docker compose up -d 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-State "false" "ошибка запуска контейнеров" $latestTag $true; Log "compose up failed"; exit 1 }

    Write-CurrentTag $latestTag

    # Синхронизируем локальный .git с раскладанными файлами, чтобы
    # защита «есть локальные изменения» не срабатывала на следующий релиз
    if (Test-Path (Join-Path $root ".git")) {
        git add -A 2>$null | Out-Null
        git -c user.name="auto-update" -c user.email="auto-update@local" `
            commit -q -m "chore: release $latestTag" --allow-empty 2>$null | Out-Null
    }

    Remove-Item -Force $requestFile -ErrorAction SilentlyContinue
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    Write-State "false" "обновлено до $latestTag ($stamp)" $latestTag $false
    Log "обновлено до $latestTag"
} finally {
    if ($lock) { $lock.Close() }
}
