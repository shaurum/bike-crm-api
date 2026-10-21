#Requires -Version 5.1
<#
  Регистрирует автообновление CRM в Планировщике заданий Windows.

  Задача «BikeCrmAutoUpdate» запускает scripts\auto-update.ps1 каждые 5 минут
  (и при входе в систему). Скрипт подтягивает origin/main, собирает образы,
  применяет миграции и перезапускает стек.

    Установить:  powershell -ExecutionPolicy Bypass -File scripts\install-auto-update.ps1
    Удалить:     powershell -ExecutionPolicy Bypass -File scripts\install-auto-update.ps1 -Uninstall

  Требования: запущенный Docker Desktop и доступ к git-репозиторию
  (при первом fetch по HTTPS GitHub попросит авторизоваться — выполните
  `git fetch origin main` вручную один раз).
#>
param(
    [switch]$Uninstall
)

$taskName = "BikeCrmAutoUpdate"
$root = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $root "scripts\auto-update.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Host "[FAIL] Не найден скрипт: $scriptPath" -ForegroundColor Red
    exit 1
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Задача «$taskName» удалена." -ForegroundColor Yellow
    exit 0
}

$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

# Повтор каждые 5 минут; -StartWhenAvailable — выполнит пропущенный запуск после включения ПК
$triggerOnce = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours(9).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 9998)
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$triggers = @($triggerOnce, $triggerLogon)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 45)

$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host ""
Write-Host "Готово: задача «$taskName» зарегистрирована." -ForegroundColor Green
Write-Host "  - проверяет обновления каждые 5 минут и при входе в систему;"
Write-Host "  - состояние видно в CRM: Настройки → Обновление;"
Write-Host "  - ручная проверка: scripts\auto-update.ps1"
Write-Host "  - удаление: scripts\install-auto-update.ps1 -Uninstall"
Write-Host ""
