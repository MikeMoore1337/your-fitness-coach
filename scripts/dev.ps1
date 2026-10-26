[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'status', 'logs', 'reset')]
    [string]$Action = 'start',
    [switch]$ConfirmReset
)

# Windows 11 / PowerShell: local-only YFC development.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    $envPath = Join-Path $root '.env.dev'
    $composePath = Join-Path $root 'compose.dev.yml'
    if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
        throw 'compose.dev.yml не найден. Переключитесь на ветку YFC с поддержкой DEV.'
    }

    function Invoke-DevCompose {
        param([string[]]$Arguments)
        & docker compose --env-file .env.dev -f compose.dev.yml @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Ошибка Docker Compose ($LASTEXITCODE)."
        }
    }

    if ($Action -eq 'reset' -and -not $ConfirmReset) {
        throw 'Удаление тестовой базы требует явного подтверждения: -Action reset -ConfirmReset'
    }
    if ($Action -eq 'start' -and -not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
        $python = Get-Command py -ErrorAction SilentlyContinue
        if ($null -eq $python) {
            throw 'Установите Python 3.14 (py -3.14) или создайте .env.dev по шаблону.'
        }
        & py -3.14 scripts/bootstrap_dev_env.py
        if ($LASTEXITCODE -ne 0) {
            throw 'Не удалось создать отдельные секреты DEV.'
        }
    }
    if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
        throw 'Отсутствует .env.dev. Запустите сначала -Action start.'
    }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker CLI отсутствует. Установите и запустите Docker Desktop с WSL2.'
    }
    & docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Engine недоступен. Запустите Docker Desktop и дождитесь Ready.'
    }

    if ($Action -eq 'start') {
        Invoke-DevCompose -Arguments @('config', '--quiet')
        Invoke-DevCompose -Arguments @('up', '-d', '--build', 'backend')
        $ready = $false
        for ($attempt = 0; $attempt -lt 45; $attempt++) {
            try {
                $response = Invoke-WebRequest -Uri 'http://127.0.0.1:18080/health/ready' -TimeoutSec 3 -UseBasicParsing
                if ($response.StatusCode -eq 200) {
                    $ready = $true
                    break
                }
            } catch {
                Start-Sleep -Seconds 2
            }
        }
        if (-not $ready) {
            throw 'DEV запущен, но /health/ready не ответил. Проверьте: .\scripts\dev.ps1 -Action logs'
        }
        Write-Host 'DEV готов: http://127.0.0.1:18080/login'
    } elseif ($Action -eq 'stop') {
        Invoke-DevCompose -Arguments @('down')
    } elseif ($Action -eq 'status') {
        Invoke-DevCompose -Arguments @('ps')
    } elseif ($Action -eq 'logs') {
        Invoke-DevCompose -Arguments @('logs', '--tail', '100', 'backend', 'setup', 'db')
    } elseif ($Action -eq 'reset') {
        Write-Warning 'Удаление ТОЛЬКО томов проекта Compose yfc-dev. Все данные DEV будут потеряны.'
        Invoke-DevCompose -Arguments @('down', '--volumes')
        Write-Host 'Изолированная база DEV удалена. Следующий -Action start создаст новую.'
    }
}
finally {
    Pop-Location
}
