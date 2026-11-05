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
           кнопке в CRM (файл backend/.update_requested).
    4. В backend/.update_requested может лежать тег (например v1.1.4) —
       тогда ставится именно эта версия: так работает выбор версии и откат.

  Состояние: backend/.update_state.json (читает API /api/v1/system/version):
  кроме версии там этап установки (stage), общий прогресс, процент скачивания,
  время начала и конца и текст ошибки последней установки.

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

# Этапы, на которых установка идёт прямо сейчас
$activeStages = @("checking", "downloading", "extracting", "copying", "building", "migrating", "restarting")

# Сведения о последней установке; переживают холостые запуски по расписанию
$script:job = [ordered]@{
    stage            = "idle"
    progress         = 0
    target_tag       = $null
    started_at       = $null
    finished_at      = $null
    error            = $null
    download_percent = $null
    download_bytes   = $null
    download_total   = $null
}
$script:latestTag = ""

function Now-Utc { (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") }

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

function Read-RequestedTag {
    # «1» или пусто — последняя версия; тег — конкретная версия
    try {
        if (Test-Path $requestFile) {
            $req = ([System.IO.File]::ReadAllText($requestFile)).Trim()
            if ($req -match '^v[0-9A-Za-z._-]+$') { return $req }
        }
    } catch {}
    return ""
}

function Restore-Job {
    try {
        if (-not (Test-Path $stateFile)) { return }
        $prev = [System.IO.File]::ReadAllText($stateFile) | ConvertFrom-Json
        foreach ($key in @($script:job.Keys)) {
            if ($prev.PSObject.Properties.Name -contains $key) { $script:job[$key] = $prev.$key }
        }
        if ($activeStages -contains $script:job.stage) {
            # Лок свободен, а этап «в процессе» — прошлый запуск оборвался (выключили ПК и т.п.)
            $script:job.stage = "error"
            $script:job.error = "установка прервана: скрипт остановился на этапе «$($prev.stage)»"
            $script:job.finished_at = Now-Utc
        }
    } catch {}
}

function Write-State([string]$updating, [string]$note, [string]$latestTag, [bool]$available) {
    $localSha = $null; $localDate = $null
    if (Test-Path (Join-Path $root ".git")) {
        $short = git rev-parse --short HEAD 2>$null
        if ($short) { $localSha = [string]$short }
        $date = git log -1 --format=%cI 2>$null
        if ($date) { $localDate = [string]$date }
    }
    $curTag = Read-CurrentTag
    $state = [ordered]@{
        current_sha      = $localSha
        current_date     = $localDate
        current_tag      = $(if ($curTag -ne "") { $curTag } else { $null })
        remote_sha       = $(if ($latestTag) { $latestTag } else { $null })
        update_available = $available
        updating         = ($updating -eq "true")
        last_check       = Now-Utc
        auto_update      = $true
        mode             = Read-Mode
        note             = $note
    }
    foreach ($key in $script:job.Keys) { $state[$key] = $script:job[$key] }
    # ConvertTo-Json экранирует кавычки и кириллицу; UTF8 без BOM — json.loads в API не принимает BOM
    $json = $state | ConvertTo-Json -Depth 3
    [System.IO.File]::WriteAllText($stateFile, $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Set-Stage([string]$stage, [int]$progress, [string]$note) {
    if ($script:job.stage -ne $stage) { Log "этап: $stage — $note" }
    $script:job.stage = $stage
    $script:job.progress = $progress
    Write-State "true" $note $script:latestTag $true
}

function Fail-Update([string]$note) {
    $script:job.stage = "error"
    $script:job.error = $note
    $script:job.finished_at = Now-Utc
    Write-State "false" $note $script:latestTag $true
    Log "ошибка: $note"
}

function Quote-Arg([string]$value) {
    if ($value -match '[\s"]') { return '"' + ($value -replace '"', '\"') + '"' }
    return $value
}

function Invoke-Download([string[]]$extra, [string]$url, [string]$dest, [long]$total, [string]$token) {
    # curl в отдельном процессе: пока он качает, по размеру файла считаем процент
    Remove-Item -Force $dest -ErrorAction SilentlyContinue
    $curlArgs = @("-sS", "-L") + $extra + @(
        "-H", "Authorization: token $token",
        "-H", "Accept: application/octet-stream",
        "-o", $dest, $url
    )
    $argLine = ($curlArgs | ForEach-Object { Quote-Arg $_ }) -join " "
    $proc = Start-Process -FilePath "curl.exe" -ArgumentList $argLine -NoNewWindow -PassThru
    $null = $proc.Handle  # без этого PS 5.1 теряет ExitCode у Start-Process
    $lastPct = -1
    while (-not $proc.HasExited) {
        Start-Sleep -Milliseconds 1000
        if ($total -gt 0 -and (Test-Path $dest)) {
            $bytes = (Get-Item $dest).Length
            $pct = [int][Math]::Min(99, [Math]::Floor($bytes * 100 / $total))
            if ($pct -ne $lastPct) {
                $lastPct = $pct
                $script:job.download_percent = $pct
                $script:job.download_bytes = $bytes
                Set-Stage "downloading" (5 + [int]($pct * 0.3)) "скачивание $($script:job.target_tag): $pct%"
            }
        }
    }
    $proc.WaitForExit()
    return $proc.ExitCode
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
    Restore-Job

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
    $script:latestTag = $latestTag
    if (-not $latestTag) {
        Write-State "false" "релизов нет" "" $false
        exit 0
    }

    $currentTag = Read-CurrentTag
    $available = ($latestTag -ne $currentTag)
    $mode = Read-Mode
    $requested = Test-Path $requestFile
    $requestedTag = Read-RequestedTag

    # Выбрана конкретная версия (в том числе откат) — берём её релиз
    $targetTag = $latestTag
    if ($requestedTag -and $requestedTag -ne $latestTag) {
        try {
            $release = Invoke-RestMethod -Uri "$repoApi/releases/tags/$requestedTag" -Headers $headers -TimeoutSec 30
            $targetTag = [string]$release.tag_name
        } catch {
            Remove-Item -Force $requestFile -ErrorAction SilentlyContinue
            $script:job.target_tag = $requestedTag
            Fail-Update "версия $requestedTag не найдена на GitHub"
            exit 1
        }
    }

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
    if (-not $Apply -and (Test-Path (Join-Path $root ".git"))) {
        $dirty = git status --porcelain 2>$null
        if ($dirty) {
            Write-State "false" "есть локальные изменения — автообновление пропущено (нужен -Apply)" $latestTag $available
            Log "локальные правки, обновление не применено"
            exit 0
        }
    }

    # --- Установка ------------------------------------------------------------
    $script:job.target_tag = $targetTag
    $script:job.started_at = Now-Utc
    $script:job.finished_at = $null
    $script:job.error = $null
    $script:job.download_percent = $null
    $script:job.download_bytes = $null
    $script:job.download_total = $null
    Set-Stage "checking" 2 "подготовка к установке $targetTag"

    $asset = $null
    foreach ($a in @($release.assets)) {
        if ($a.name -like "*.zip") { $asset = $a; break }
    }
    if (-not $asset) {
        Fail-Update "в релизе $targetTag нет zip-архива"
        exit 1
    }
    Log "установка $targetTag (asset: $($asset.name))"

    $zipPath = Join-Path $env:TEMP "bike-crm-update.zip"
    $extractDir = Join-Path $env:TEMP "bike-crm-update-extract"
    Remove-Item -Recurse -Force $extractDir -ErrorAction SilentlyContinue

    $total = [long]$asset.size
    $script:job.download_total = $total
    $script:job.download_percent = 0
    $script:job.download_bytes = 0
    Set-Stage "downloading" 5 "скачивание $targetTag"

    # Некоторые ПК: системный curl не доверяет корням (HTTPS-инспекция
    # антивируса подменяет сертификат) -> curl exit 60. Цепочка попыток:
    # 1) обычный curl; 2) schannel (сертификаты Windows); 3) без проверки TLS.
    $downloaded = $false
    $attempts = @(
        @(),
        @("--ssl-backend", "schannel"),
        @("-k")
    )
    foreach ($extra in $attempts) {
        $code = Invoke-Download $extra ([string]$asset.url) $zipPath $total $token
        if ($code -eq 0 -and (Test-Path $zipPath) -and ((Get-Item $zipPath).Length -gt 0)) {
            $downloaded = $true
            break
        }
        Log ("скачивание: попытка не удалась (exit=$code, extra=$($extra -join ' '))")
    }
    if (-not $downloaded) {
        Fail-Update "ошибка скачивания $targetTag"
        exit 1
    }
    $script:job.download_percent = 100
    $script:job.download_bytes = (Get-Item $zipPath).Length

    Set-Stage "extracting" 35 "распаковка архива"
    try {
        Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force -ErrorAction Stop
    } catch {
        Log "распаковка: $($_.Exception.Message)"
        Fail-Update "ошибка распаковки архива"
        exit 1
    }

    $src = Get-ChildItem $extractDir -Directory | Select-Object -First 1
    if (-not $src) {
        Fail-Update "пустой архив"
        exit 1
    }

    # zip собран через git archive — в нём нет .env, data/, .update_*,
    # раскладываем поверх рабочей копии
    Set-Stage "copying" 40 "копирование файлов"
    & robocopy $src.FullName $root /E /XF ".env" /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) {
        Log "robocopy failed ($LASTEXITCODE)"
        Fail-Update "ошибка копирования файлов"
        exit 1
    }

    Set-Stage "building" 45 "сборка образов (может занять несколько минут)"
    docker compose build -q 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail-Update "ошибка сборки образов"; exit 1 }

    Set-Stage "migrating" 80 "миграции базы данных"
    docker compose run --rm api alembic upgrade head 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail-Update "ошибка миграций базы данных"; exit 1 }

    Set-Stage "restarting" 90 "перезапуск CRM"
    docker compose up -d 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail-Update "ошибка запуска контейнеров"; exit 1 }
    # Dev-сервер фронтенда не видит смену файлов в смонтированной папке Windows,
    # а nginx помнит старые адреса контейнеров: перезапускаем оба
    docker compose restart frontend 2>$null | Out-Null
    docker compose restart nginx 2>$null | Out-Null

    Write-CurrentTag $targetTag

    # Синхронизируем локальный .git с раскладанными файлами, чтобы
    # защита «есть локальные изменения» не срабатывала на следующий релиз
    if (Test-Path (Join-Path $root ".git")) {
        git add -A 2>$null | Out-Null
        git -c user.name="auto-update" -c user.email="auto-update@local" `
            commit -q -m "chore: release $targetTag" --allow-empty 2>$null | Out-Null
    }

    Remove-Item -Force $requestFile -ErrorAction SilentlyContinue
    $script:job.stage = "done"
    $script:job.progress = 100
    $script:job.finished_at = Now-Utc
    Write-State "false" "установлена $targetTag" $latestTag ($latestTag -ne $targetTag)
    Log "обновлено до $targetTag"
} finally {
    if ($lock) { $lock.Close() }
}
