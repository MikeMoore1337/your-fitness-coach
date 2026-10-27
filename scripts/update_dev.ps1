[CmdletBinding()]
param(
    [ValidateSet('Check', 'Apply', 'Status')]
    [string]$Mode = 'Check',
    [string]$RepositoryPath = '',
    [ValidateSet(
        'None',
        'Register',
        'Unregister',
        'EnableCheck',
        'DisableCheck',
        'EnableAutoApply',
        'DisableAutoApply',
        'Lock',
        'Unlock',
        'SchedulerStatus',
        'ClearIncomplete'
    )]
    [string]$TaskAction = 'None',
    [switch]$Automatic,
    [switch]$ConfirmClearIncomplete,
    [string]$GitHubApiBaseUrl = 'https://api.github.com'
)

# Local-only DEV updater. It never uses production credentials or destructive DEV commands.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ExitCode = 0
$script:FailureCode = ''
$script:FailureSummary = ''
$script:Mutex = $null
$script:MutexHeld = $false
$script:InProgressOwned = $false
$script:CurrentResult = [ordered]@{
    schema = 1
    started_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    completed_at_utc = ''
    mode = $Mode
    repository = ''
    branch = ''
    installed_sha = ''
    available_sha = ''
    git = 'NOT_RUN'
    ci = 'NOT_RUN'
    ci_run = ''
    docker = 'NOT_RUN'
    health_live = 'NOT_RUN'
    health_ready = 'NOT_RUN'
    rbac = 'NOT_RUN'
    volume_before = 'NOT_RUN'
    volume_after = 'NOT_RUN'
    migration = 'NOT_APPLICABLE'
    backup = 'NOT_REQUIRED'
    backup_path = ''
    result = 'STARTED'
    error_code = ''
}

$script:RepoRoot = if ($RepositoryPath) {
    (Resolve-Path -LiteralPath $RepositoryPath -ErrorAction Stop).Path
} else {
    (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..') -ErrorAction Stop).Path
}
$script:RepoRoot = $script:RepoRoot.TrimEnd('\', '/')
$script:StateRoot = Join-Path $script:RepoRoot '.artifacts\runtime\dev-update'
$script:InProgressPath = Join-Path $script:StateRoot 'in-progress.json'
$script:ManualLockPath = Join-Path $script:StateRoot 'manual-acceptance.lock'
$script:AutoApplyPath = Join-Path $script:StateRoot 'auto-apply.enabled'
$script:LastResultPath = Join-Path $script:StateRoot 'last-result.json'
$script:TaskName = 'YFC-DEV-Update-Check'
$script:GitHubRepository = 'MikeMoore1337/your-fitness-coach'
$script:ExpectedOrigin = 'https://github.com/mikemoore1337/your-fitness-coach'
$script:ApiBaseUrl = $GitHubApiBaseUrl.TrimEnd('/')
$script:CurrentResult.repository = $script:RepoRoot

function Stop-Update {
    param(
        [Parameter(Mandatory = $true)][string]$Code,
        [Parameter(Mandatory = $true)][string]$Summary,
        [switch]$Deferred
    )
    $script:FailureCode = $Code
    $script:FailureSummary = $Summary
    $script:CurrentResult.error_code = $Code
    if ($Deferred) {
        $script:ExitCode = 2
    } else {
        $script:ExitCode = 1
    }
    throw [System.InvalidOperationException]::new($Summary)
}

function Save-Result {
    param([string]$LogName = '')
    $script:CurrentResult.completed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    New-Item -ItemType Directory -Path $script:StateRoot -Force | Out-Null
    $json = $script:CurrentResult | ConvertTo-Json -Depth 6
    Set-Content -LiteralPath $script:LastResultPath -Value $json -Encoding UTF8
    if (-not $LogName) {
        $LogName = 'update-{0}.json' -f (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmssfff')
    }
    Set-Content -LiteralPath (Join-Path $script:StateRoot $LogName) -Value $json -Encoding UTF8
}

function Enter-UpdateMutex {
    try {
        $script:Mutex = [System.Threading.Mutex]::new($false, 'Global\YFC_DEV_UPDATE')
        if (-not $script:Mutex.WaitOne(0)) {
            Stop-Update -Code 'UPDATE_IN_PROGRESS' -Summary 'Предыдущее обновление ещё выполняется.' -Deferred
        }
        $script:MutexHeld = $true
    } catch [System.Threading.AbandonedMutexException] {
        # The OS released a crashed process lock; this invocation now owns it.
        $script:MutexHeld = $true
    }
}

function Exit-UpdateMutex {
    if ($null -ne $script:Mutex) {
        if ($script:MutexHeld) {
            $script:Mutex.ReleaseMutex()
        }
        $script:Mutex.Dispose()
        $script:Mutex = $null
        $script:MutexHeld = $false
    }
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )
    $safeDirectory = 'safe.directory={0}' -f $script:RepoRoot.Replace('\', '/')
    $output = @(& git -c $safeDirectory -C $script:RepoRoot @Arguments 2>$null)
    $exitCode = $LASTEXITCODE
    if (-not $AllowFailure -and $exitCode -ne 0) {
        Stop-Update -Code 'GIT_COMMAND_FAILED' -Summary 'Git-команда завершилась ошибкой.'
    }
    [pscustomobject]@{
        Output   = $output
        ExitCode = $exitCode
    }
}

function Get-GitValue {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $result = Invoke-Git -Arguments $Arguments
    return (($result.Output -join "`n").Trim())
}

function Normalize-Origin {
    param([Parameter(Mandatory = $true)][string]$Value)
    $normalized = $Value.Trim().TrimEnd('/').ToLowerInvariant()
    $normalized = $normalized -replace '^git@github\.com:', 'https://github.com/'
    $normalized = $normalized -replace '^ssh://git@github\.com/', 'https://github.com/'
    if ($normalized.EndsWith('.git')) {
        $normalized = $normalized.Substring(0, $normalized.Length - 4)
    }
    return $normalized
}

function Get-GitContext {
    param([switch]$RequireClean)
    if (-not (Test-Path -LiteralPath (Join-Path $script:RepoRoot '.git'))) {
        Stop-Update -Code 'NOT_GIT_REPOSITORY' -Summary 'Локальный путь не является Git-репозиторием.'
    }
    $top = Get-GitValue -Arguments @('rev-parse', '--show-toplevel')
    if (([System.IO.Path]::GetFullPath($top)).TrimEnd('\', '/') -ne $script:RepoRoot) {
        Stop-Update -Code 'WRONG_REPOSITORY' -Summary 'Git-корень не совпадает с репозиторием DEV.'
    }
    $branch = Get-GitValue -Arguments @('symbolic-ref', '--quiet', '--short', 'HEAD')
    $script:CurrentResult.branch = $branch
    if ($branch -ne 'dev') {
        Stop-Update -Code 'WRONG_BRANCH' -Summary 'Обновление разрешено только из ветки dev.'
    }
    $origin = Normalize-Origin (Get-GitValue -Arguments @('remote', 'get-url', 'origin'))
    if ($origin -ne $script:ExpectedOrigin) {
        Stop-Update -Code 'WRONG_ORIGIN' -Summary 'origin не совпадает с MikeMoore1337/your-fitness-coach.'
    }
    $dirty = Get-GitValue -Arguments @('status', '--porcelain=v1', '--untracked-files=all')
    if ($RequireClean -and $dirty) {
        $script:CurrentResult.git = 'DIRTY'
        Stop-Update -Code 'GIT_DIRTY' -Summary 'Рабочая копия dev содержит незакоммиченные изменения.' -Deferred
    }
    [pscustomobject]@{
        Branch = $branch
        Origin = $origin
        Dirty  = [bool]$dirty
    }
}

function Update-RemoteDev {
    [void](Invoke-Git -Arguments @('fetch', 'origin', 'dev:refs/remotes/origin/dev'))
    $source = Get-GitValue -Arguments @('rev-parse', 'HEAD')
    $target = Get-GitValue -Arguments @('rev-parse', 'origin/dev')
    if ($source -notmatch '^[0-9a-f]{40}$' -or $target -notmatch '^[0-9a-f]{40}$') {
        Stop-Update -Code 'INVALID_SHA' -Summary 'Git не вернул полный commit SHA.'
    }
    $script:CurrentResult.installed_sha = $source
    $script:CurrentResult.available_sha = $target
    [pscustomobject]@{
        Source = $source
        Target = $target
    }
}

function Test-FastForward {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target
    )
    if ($Source -eq $Target) {
        return 'NO_UPDATE'
    }
    $sourceIsAncestor = Invoke-Git -Arguments @('merge-base', '--is-ancestor', $Source, $Target) -AllowFailure
    if ($sourceIsAncestor.ExitCode -eq 0) {
        return 'FAST_FORWARD'
    }
    $targetIsAncestor = Invoke-Git -Arguments @('merge-base', '--is-ancestor', $Target, $Source) -AllowFailure
    if ($targetIsAncestor.ExitCode -eq 0) {
        return 'LOCAL_AHEAD'
    }
    return 'DIVERGENT'
}

function Invoke-GitHubGet {
    param([Parameter(Mandatory = $true)][string]$Path)
    $uri = '{0}/repos/{1}/{2}' -f $script:ApiBaseUrl, $script:GitHubRepository, $Path
    try {
        return Invoke-RestMethod -Method Get -Uri $uri -Headers @{
            Accept     = 'application/vnd.github+json'
            'User-Agent' = 'YFC-DEV-Updater'
        } -TimeoutSec 20
    } catch {
        Stop-Update -Code 'CI_UNAVAILABLE' -Summary 'GitHub CI недоступен; обновление отложено.' -Deferred
    }
}

function Get-PostPushCi {
    param([Parameter(Mandatory = $true)][string]$TargetSha)
    $runs = Invoke-GitHubGet -Path ('actions/runs?branch=dev&event=push&head_sha={0}&per_page=20' -f $TargetSha)
    $run = @(
        $runs.workflow_runs |
            Where-Object {
                $_.name -eq 'CI' -and
                $_.event -eq 'push' -and
                $_.head_branch -eq 'dev' -and
                $_.head_sha -eq $TargetSha
            } |
            Sort-Object created_at -Descending
    ) | Select-Object -First 1
    if ($null -eq $run) {
        return [pscustomobject]@{
            State = 'PENDING'
            RunId = ''
            Url   = ''
        }
    }
    $runUrl = if ($run.html_url) { $run.html_url } else { $run.url }
    if ($run.status -ne 'completed') {
        return [pscustomobject]@{
            State = 'PENDING'
            RunId = [string]$run.id
            Url   = $runUrl
        }
    }
    if ($run.conclusion -ne 'success') {
        return [pscustomobject]@{
            State = 'FAILED'
            RunId = [string]$run.id
            Url   = $runUrl
        }
    }
    $jobs = Invoke-GitHubGet -Path ('actions/runs/{0}/jobs?per_page=100' -f $run.id)
    $aggregate = @($jobs.jobs | Where-Object { $_.name -eq 'branch-checks' }) | Select-Object -First 1
    if ($null -eq $aggregate -or $aggregate.status -ne 'completed') {
        return [pscustomobject]@{
            State = 'PENDING'
            RunId = [string]$run.id
            Url   = $runUrl
        }
    }
    if ($aggregate.conclusion -ne 'success') {
        return [pscustomobject]@{
            State = 'FAILED'
            RunId = [string]$run.id
            Url   = $runUrl
        }
    }
    [pscustomobject]@{
        State = 'PASS'
        RunId = [string]$run.id
        Url   = $runUrl
    }
}

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    if ($Arguments -contains 'down' -and
        ($Arguments -contains '--volumes' -or $Arguments -contains '-v')) {
        Stop-Update -Code 'DESTRUCTIVE_COMPOSE_BLOCKED' -Summary 'Опасная Docker Compose-команда запрещена в updater.'
    }
    $envPath = Join-Path $script:RepoRoot '.env.dev'
    if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
        Stop-Update -Code 'DEV_ENV_MISSING' -Summary 'Отсутствует .env.dev; updater не читает production .env.'
    }
    $composePath = Join-Path $script:RepoRoot 'compose.dev.yml'
    if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
        Stop-Update -Code 'DEV_COMPOSE_MISSING' -Summary 'Отсутствует compose.dev.yml.'
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Stop-Update -Code 'DOCKER_UNAVAILABLE' -Summary 'Docker CLI недоступен.' -Deferred
    }
    Push-Location $script:RepoRoot
    try {
        $output = @(& docker compose --env-file .env.dev -f compose.dev.yml @Arguments 2>$null)
        $composeExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($composeExitCode -ne 0) {
        Stop-Update -Code 'DOCKER_COMMAND_FAILED' -Summary 'Docker Compose-команда завершилась ошибкой.'
    }
    return $output
}

function Invoke-DevStart {
    $devScript = Join-Path $script:RepoRoot 'scripts\dev.ps1'
    if (-not (Test-Path -LiteralPath $devScript -PathType Leaf)) {
        Stop-Update -Code 'DEV_SCRIPT_MISSING' -Summary 'Не найден существующий scripts/dev.ps1.'
    }
    & $devScript -Action start *> $null
    if ($LASTEXITCODE -ne 0) {
        Stop-Update -Code 'DEV_START_FAILED' -Summary 'scripts/dev.ps1 -Action start завершился ошибкой.'
    }
}

function Get-DockerSummary {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        return [ordered]@{ Status = 'UNAVAILABLE'; Services = @() }
    }
    try {
        & docker info --format '{{.ServerVersion}}' *> $null
        if ($LASTEXITCODE -ne 0) {
            return [ordered]@{ Status = 'UNAVAILABLE'; Services = @() }
        }
        $services = @(Invoke-Compose -Arguments @('ps', '-a', '--format', '{{.Service}}={{.State}}'))
        return [ordered]@{ Status = 'PASS'; Services = @($services | ForEach-Object { [string]$_ }) }
    } catch {
        return [ordered]@{ Status = 'FAIL'; Services = @() }
    }
}

function Get-VolumeSnapshot {
    try {
        $volumeKeys = @(Invoke-Compose -Arguments @('config', '--volumes')) |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { $_ }
        $logicalName = $volumeKeys | Where-Object { $_ -eq 'dev_postgres_data' } | Select-Object -First 1
        if (-not $logicalName) {
            return [ordered]@{ Status = 'NOT_CONFIGURED'; Name = ''; CreatedAt = '' }
        }
        $names = @(& docker volume ls --filter 'label=com.docker.compose.project=yfc-dev' --format '{{.Name}}' 2>$null)
        $name = $names | Where-Object { ([string]$_).EndsWith($logicalName) } | Select-Object -First 1
        if (-not $name) {
            return [ordered]@{ Status = 'NOT_PRESENT'; Name = ''; CreatedAt = '' }
        }
        $inspect = @(& docker volume inspect ([string]$name) --format '{{json .}}' 2>$null)
        if ($LASTEXITCODE -ne 0 -or -not $inspect) {
            return [ordered]@{ Status = 'UNAVAILABLE'; Name = [string]$name; CreatedAt = '' }
        }
        $metadata = $inspect -join "`n" | ConvertFrom-Json
        return [ordered]@{
            Status    = 'PRESENT'
            Name      = [string]$metadata.Name
            CreatedAt = [string]$metadata.CreatedAt
        }
    } catch {
        return [ordered]@{ Status = 'UNAVAILABLE'; Name = ''; CreatedAt = '' }
    }
}

function Test-HealthEndpoint {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $response = Invoke-WebRequest -Uri ('http://127.0.0.1:18080{0}' -f $Path) -TimeoutSec 10 -UseBasicParsing
        return ($response.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Invoke-RbacSmoke {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        Stop-Update -Code 'PYTHON_UNAVAILABLE' -Summary 'Не найден launcher py для Python 3.14.'
    }
    Push-Location $script:RepoRoot
    try {
        & py -3.14 scripts/verify_dev_roles.py *> $null
        return ($LASTEXITCODE -eq 0)
    } finally {
        Pop-Location
    }
}

function Get-ChangedMigrations {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target
    )
    $raw = Get-GitValue -Arguments @(
        'diff', '--name-status', $Source, $Target, '--', 'backend/alembic/versions'
    )
    return @($raw -split "`r?`n" | Where-Object { $_.Trim() })
}

function Test-MigrationCompatibility {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target
    )
    $changes = @(Get-ChangedMigrations -Source $Source -Target $Target)
    if ($changes.Count -eq 0) {
        $script:CurrentResult.migration = 'NOT_APPLICABLE'
        return $false
    }
    $script:CurrentResult.migration = 'BACKUP_REQUIRED'
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        Stop-Update -Code 'PYTHON_UNAVAILABLE' -Summary 'Не найден launcher py для проверки миграций.' -Deferred
    }
    Push-Location $script:RepoRoot
    try {
        & py -3.14 scripts/check_online_migrations.py $Source $Target *> $null
        $validatorExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($validatorExitCode -ne 0) {
        Stop-Update -Code 'MIGRATION_REVIEW_REQUIRED' -Summary 'Проверка совместимости миграций не пройдена; автоматическое обновление остановлено.' -Deferred
    }
    return $true
}

function Invoke-Check {
    $gitContext = Get-GitContext
    if ($gitContext.Dirty) {
        $script:CurrentResult.git = 'DIRTY'
        $script:CurrentResult.result = 'DEFERRED_GIT_DIRTY'
        $script:ExitCode = 2
        Save-Result
        Write-Host 'YFC DEV: обновление отложено — рабочая копия dev содержит незакоммиченные изменения.'
        return
    }
    $context = Update-RemoteDev
    $ffState = Test-FastForward -Source $context.Source -Target $context.Target
    if ($ffState -eq 'NO_UPDATE') {
        $script:CurrentResult.git = 'PASS'
        $script:CurrentResult.result = 'NO_UPDATE'
        Save-Result
        Write-Host ('YFC DEV: обновлений нет; SHA {0}' -f $context.Source)
        return
    }
    if ($ffState -ne 'FAST_FORWARD') {
        $script:CurrentResult.git = $ffState
        $script:CurrentResult.result = 'DEFERRED_{0}' -f $ffState
        $script:ExitCode = 2
        Save-Result
        Write-Host ('YFC DEV: обновление отложено ({0}).' -f $ffState)
        return
    }
    $script:CurrentResult.git = 'FAST_FORWARD_AVAILABLE'
    if (Test-ManualLock) {
        $script:CurrentResult.result = 'DEFERRED_MANUAL_LOCK'
        $script:ExitCode = 2
        Save-Result
        Write-Host 'YFC DEV: обновление заблокировано ручной приёмкой.'
        return
    }
    if (Test-Path -LiteralPath $script:InProgressPath) {
        $script:CurrentResult.result = 'DEFERRED_INCOMPLETE_UPDATE'
        $script:ExitCode = 2
        Save-Result
        Write-Host 'YFC DEV: обнаружено незавершённое обновление; текущая версия сохранена.'
        return
    }
    $ci = Get-PostPushCi -TargetSha $context.Target
    $script:CurrentResult.ci = $ci.State
    $script:CurrentResult.ci_run = $ci.Url
    if ($ci.State -ne 'PASS') {
        $script:CurrentResult.result = 'DEFERRED_CI_{0}' -f $ci.State
        $script:ExitCode = 2
        Save-Result
        Write-Host ('YFC DEV: CI для {0} ещё не подтверждён ({1}).' -f $context.Target, $ci.State)
        return
    }
    $script:CurrentResult.result = 'UPDATE_AVAILABLE_CI_PASS'
    Save-Result
    Write-Host ('YFC DEV: доступно обновление {0}; CI exact-head PASS.' -f $context.Target)
    if ($Automatic -and (Test-AutoApplyEnabled)) {
        Invoke-Apply
    }
}

function Get-AvailableSha {
    try {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            return 'UNAVAILABLE'
        }
        $result = Invoke-Git -Arguments @('ls-remote', 'origin', 'refs/heads/dev') -AllowFailure
        if ($result.ExitCode -eq 0) {
            $remote = ($result.Output -join "`n").Trim()
            if ($remote -match '^([0-9a-f]{40})\s+refs/heads/dev$') {
                return $Matches[1]
            }
        }
    } catch {
        return 'UNAVAILABLE'
    }
    return 'UNAVAILABLE'
}

function Ensure-DevStackForBackup {
    try {
        $running = @(Invoke-Compose -Arguments @('ps', '--status', 'running', '--services')) |
            ForEach-Object { ([string]$_).Trim() }
        if ($running -contains 'db') {
            return
        }
    } catch {
        # Start below gives the normal, project-owned diagnostic path.
    }
    Invoke-DevStart
}

function Backup-DevDatabase {
    param([Parameter(Mandatory = $true)][string]$TargetSha)
    Ensure-DevStackForBackup
    $backupDir = Join-Path $script:StateRoot 'backups'
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    $shortSha = $TargetSha.Substring(0, 12)
    $backupPath = Join-Path $backupDir ('postgres-{0}-{1}.sql' -f (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss'), $shortSha)
    $errorPath = '{0}.stderr' -f $backupPath
    $docker = (Get-Command docker -ErrorAction Stop).Source
    $arguments = @(
        'compose', '--env-file', '.env.dev', '-f', 'compose.dev.yml',
        'exec', '-T', 'db', 'pg_dump', '-U', 'yfc_dev', '-d', 'yfc_dev',
        '--format=plain', '--no-owner', '--no-privileges'
    )
    $process = Start-Process -FilePath $docker -ArgumentList $arguments -WorkingDirectory $script:RepoRoot -Wait -PassThru `
        -RedirectStandardOutput $backupPath -RedirectStandardError $errorPath -WindowStyle Hidden
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $backupPath) -or
        (Get-Item -LiteralPath $backupPath).Length -lt 100) {
        Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $errorPath -Force -ErrorAction SilentlyContinue
        Stop-Update -Code 'DEV_BACKUP_FAILED' -Summary 'Резервная копия локальной DEV базы не создана.'
    }
    Remove-Item -LiteralPath $errorPath -Force -ErrorAction SilentlyContinue
    $script:CurrentResult.backup = 'PASS'
    $script:CurrentResult.backup_path = $backupPath
    return $backupPath
}

function Write-InProgress {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target
    )
    if (Test-Path -LiteralPath $script:InProgressPath) {
        Stop-Update -Code 'INCOMPLETE_UPDATE_PRESENT' -Summary 'Предыдущее обновление не завершено; сначала проверьте Status.' -Deferred
    }
    $payload = [ordered]@{
        pid = $PID
        started_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        source_sha = $Source
        target_sha = $Target
    } | ConvertTo-Json
    Set-Content -LiteralPath $script:InProgressPath -Value $payload -Encoding UTF8 -NoNewline
    $script:InProgressOwned = $true
}

function Remove-InProgress {
    if ($script:InProgressOwned -and (Test-Path -LiteralPath $script:InProgressPath)) {
        Remove-Item -LiteralPath $script:InProgressPath -Force -ErrorAction SilentlyContinue
    }
    $script:InProgressOwned = $false
}

function Test-ManualLock {
    return (Test-Path -LiteralPath $script:ManualLockPath)
}

function Test-AutoApplyEnabled {
    return (Test-Path -LiteralPath $script:AutoApplyPath)
}

function Format-OnOff {
    param([Parameter(Mandatory = $true)][bool]$Enabled)
    if ($Enabled) { return 'ON' }
    return 'OFF'
}

function Invoke-Apply {
    if ($Automatic -and -not (Test-AutoApplyEnabled)) {
        Stop-Update -Code 'AUTO_APPLY_DISABLED' -Summary 'Автоматическая установка выключена.' -Deferred
    }
    if (Test-ManualLock) {
        Stop-Update -Code 'MANUAL_ACCEPTANCE_LOCK' -Summary 'Обновление заблокировано ручной DEV-приёмкой.' -Deferred
    }
    if (Test-Path -LiteralPath $script:InProgressPath) {
        Stop-Update -Code 'INCOMPLETE_UPDATE_PRESENT' -Summary 'Предыдущее обновление не завершено; текущая версия сохранена.' -Deferred
    }
    $null = Get-GitContext -RequireClean
    $context = Update-RemoteDev
    $ffState = Test-FastForward -Source $context.Source -Target $context.Target
    if ($ffState -eq 'NO_UPDATE') {
        $script:CurrentResult.git = 'PASS'
        $script:CurrentResult.result = 'NO_UPDATE'
        Save-Result
        Write-Host ('YFC DEV: обновлений нет; пересборка не выполнялась.')
        return
    }
    if ($ffState -ne 'FAST_FORWARD') {
        Stop-Update -Code ('GIT_{0}' -f $ffState) -Summary 'Обновление не является безопасным fast-forward.' -Deferred
    }
    $ci = Get-PostPushCi -TargetSha $context.Target
    $script:CurrentResult.ci = $ci.State
    $script:CurrentResult.ci_run = $ci.Url
    if ($ci.State -ne 'PASS') {
        Stop-Update -Code ('CI_{0}' -f $ci.State) -Summary 'Post-push CI exact-head не завершён успешно; обновление отложено.' -Deferred
    }
    $hasMigrations = Test-MigrationCompatibility -Source $context.Source -Target $context.Target
    if ($hasMigrations) {
        Ensure-DevStackForBackup
    }
    $dockerBefore = Get-DockerSummary
    $script:CurrentResult.docker = $dockerBefore.Status
    if ($dockerBefore.Status -ne 'PASS') {
        Stop-Update -Code 'DOCKER_UNAVAILABLE' -Summary 'Docker Compose не подтверждён до fast-forward; обновление отложено.' -Deferred
    }
    $volumeBefore = Get-VolumeSnapshot
    $script:CurrentResult.volume_before = $volumeBefore.Status
    if ($volumeBefore.Status -in @('UNAVAILABLE', 'NOT_CONFIGURED')) {
        Stop-Update -Code 'VOLUME_CHECK_FAILED' -Summary 'Невозможно подтвердить PostgreSQL volume до обновления.' -Deferred
    }
    Write-InProgress -Source $context.Source -Target $context.Target
    try {
        if ($hasMigrations) {
            [void](Backup-DevDatabase -TargetSha $context.Target)
        }
        [void](Invoke-Git -Arguments @('merge', '--ff-only', 'origin/dev'))
        $script:CurrentResult.git = 'FAST_FORWARD_APPLIED'
        Invoke-DevStart
        $script:CurrentResult.health_live = if (Test-HealthEndpoint -Path '/health/live') { 'PASS' } else { 'FAIL' }
        if ($script:CurrentResult.health_live -ne 'PASS') {
            Stop-Update -Code 'HEALTH_LIVE_FAILED' -Summary '/health/live не вернул HTTP 200.'
        }
        $script:CurrentResult.health_ready = if (Test-HealthEndpoint -Path '/health/ready') { 'PASS' } else { 'FAIL' }
        if ($script:CurrentResult.health_ready -ne 'PASS') {
            Stop-Update -Code 'HEALTH_READY_FAILED' -Summary '/health/ready не вернул HTTP 200.'
        }
        $script:CurrentResult.rbac = if (Invoke-RbacSmoke) { 'PASS' } else { 'FAIL' }
        if ($script:CurrentResult.rbac -ne 'PASS') {
            Stop-Update -Code 'RBAC_FAILED' -Summary 'verify_dev_roles.py завершился ошибкой.'
        }
        $actual = Get-GitValue -Arguments @('rev-parse', 'HEAD')
        if ($actual -ne $context.Target) {
            Stop-Update -Code 'SHA_MISMATCH' -Summary 'После обновления HEAD не совпадает с проверенным target SHA.'
        }
        $script:CurrentResult.installed_sha = $actual
        $dockerSummary = Get-DockerSummary
        $script:CurrentResult.docker = $dockerSummary.Status
        if ($dockerSummary.Status -ne 'PASS') {
            Stop-Update -Code 'DOCKER_STATE_FAILED' -Summary 'Состояние Docker Compose после обновления не подтверждено.'
        }
        $volumeAfter = Get-VolumeSnapshot
        $script:CurrentResult.volume_after = $volumeAfter.Status
        if ($volumeBefore.Status -eq 'PRESENT' -and
            ($volumeAfter.Status -ne 'PRESENT' -or $volumeBefore.Name -ne $volumeAfter.Name -or
                $volumeBefore.CreatedAt -ne $volumeAfter.CreatedAt)) {
            Stop-Update -Code 'VOLUME_CHANGED' -Summary 'PostgreSQL volume изменился; автоматическое продолжение остановлено.'
        }
        $script:CurrentResult.result = 'PASS'
        Save-Result
        Write-Host ('YFC DEV: обновление PASS; установлен {0}' -f $actual)
    } finally {
        Remove-InProgress
    }
}

function Invoke-Status {
    $installed = 'UNAVAILABLE'
    $branch = 'UNAVAILABLE'
    try {
        $branch = Get-GitValue -Arguments @('symbolic-ref', '--quiet', '--short', 'HEAD')
        $installed = Get-GitValue -Arguments @('rev-parse', 'HEAD')
    } catch {
        # Status is diagnostic and should still show the remaining fields.
    }
    $available = Get-AvailableSha
    $docker = Get-DockerSummary
    $last = $null
    if (Test-Path -LiteralPath $script:LastResultPath) {
        try { $last = Get-Content -Raw -LiteralPath $script:LastResultPath | ConvertFrom-Json } catch { $last = $null }
    }
    Write-Host ('YFC DEV status | branch={0}' -f $branch)
    Write-Host ('installed_sha={0}' -f $installed)
    Write-Host ('available_sha={0}' -f $available)
    Write-Host ('containers={0}' -f $docker.Status)
    if ($docker.Services.Count -gt 0) {
        Write-Host ('container_services={0}' -f (($docker.Services -join ', ')))
    }
    Write-Host ('manual_acceptance_lock={0}' -f (Format-OnOff -Enabled (Test-ManualLock)))
    Write-Host ('auto_apply={0}' -f (Format-OnOff -Enabled (Test-AutoApplyEnabled)))
    if (Test-Path -LiteralPath $script:InProgressPath) {
        Write-Host 'in_progress=YES'
    } else {
        Write-Host 'in_progress=NO'
    }
    if ($null -ne $last) {
        Write-Host ('last_result={0} at {1}' -f $last.result, $last.completed_at_utc)
    } else {
        Write-Host 'last_result=NO_DATA'
    }
}

function Get-TaskHost {
    $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($null -ne $pwsh) { return $pwsh.Source }
    $powershell = Get-Command powershell -ErrorAction Stop
    return $powershell.Source
}

function Invoke-TaskAction {
    New-Item -ItemType Directory -Path $script:StateRoot -Force | Out-Null
    switch ($TaskAction) {
        'Register' {
            $scriptPath = Join-Path $script:RepoRoot 'scripts\update_dev.ps1'
            $hostPath = Get-TaskHost
            $escapedScript = $scriptPath.Replace('"', '\"')
            $action = New-ScheduledTaskAction -Execute $hostPath -Argument ('-NoLogo -NoProfile -ExecutionPolicy Bypass -File "{0}" -Mode Check -Automatic' -f $escapedScript)
            $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
                -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
            $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
                -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
            $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType InteractiveToken -RunLevel Limited
            Register-ScheduledTask -TaskName $script:TaskName -Action $action -Trigger $trigger `
                -Settings $settings -Principal $principal -Force | Out-Null
            Enable-ScheduledTask -TaskName $script:TaskName | Out-Null
            Remove-Item -LiteralPath $script:AutoApplyPath -Force -ErrorAction SilentlyContinue
            Write-Host 'Планировщик зарегистрирован: проверка каждые 5 минут; автоустановка выключена.'
        }
        'Unregister' {
            Unregister-ScheduledTask -TaskName $script:TaskName -Confirm:$false -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $script:AutoApplyPath -Force -ErrorAction SilentlyContinue
            Write-Host 'Планировщик отключён и удалён; данные DEV не изменялись.'
        }
        'EnableCheck' {
            Enable-ScheduledTask -TaskName $script:TaskName -ErrorAction Stop | Out-Null
            Write-Host 'Автоматическая проверка включена.'
        }
        'DisableCheck' {
            Disable-ScheduledTask -TaskName $script:TaskName -ErrorAction Stop | Out-Null
            Write-Host 'Автоматическая проверка отключена.'
        }
        'EnableAutoApply' {
            if ($null -eq (Get-ScheduledTask -TaskName $script:TaskName -ErrorAction SilentlyContinue)) {
                Stop-Update -Code 'TASK_NOT_REGISTERED' -Summary 'Сначала зарегистрируйте локальное задание.'
            }
            Set-Content -LiteralPath $script:AutoApplyPath -Value 'enabled' -Encoding ASCII -NoNewline
            Write-Host 'Автоматическая установка включена; CI, lock и fast-forward проверки обязательны.'
        }
        'DisableAutoApply' {
            Remove-Item -LiteralPath $script:AutoApplyPath -Force -ErrorAction SilentlyContinue
            Write-Host 'Автоматическая установка отключена.'
        }
        'Lock' {
            Set-Content -LiteralPath $script:ManualLockPath -Value 'locked' -Encoding ASCII -NoNewline
            Write-Host 'Обновления заблокированы для ручной DEV-приёмки.'
        }
        'Unlock' {
            Remove-Item -LiteralPath $script:ManualLockPath -Force -ErrorAction SilentlyContinue
            Write-Host 'Блокировка ручной DEV-приёмки снята.'
        }
        'SchedulerStatus' {
            $task = Get-ScheduledTask -TaskName $script:TaskName -ErrorAction SilentlyContinue
            if ($null -eq $task) {
                Write-Host 'scheduler=NOT_REGISTERED'
            } else {
                $info = Get-ScheduledTaskInfo -TaskName $script:TaskName
                Write-Host ('scheduler={0}; last_run={1}; next_run={2}' -f $task.State, $info.LastRunTime, $info.NextRunTime)
            }
            Write-Host ('auto_apply={0}' -f (Format-OnOff -Enabled (Test-AutoApplyEnabled)))
            Write-Host ('manual_acceptance_lock={0}' -f (Format-OnOff -Enabled (Test-ManualLock)))
        }
        'ClearIncomplete' {
            if (-not $ConfirmClearIncomplete) {
                Stop-Update -Code 'CONFIRMATION_REQUIRED' -Summary 'Для очистки незавершённого состояния нужен -ConfirmClearIncomplete.'
            }
            if (-not (Test-Path -LiteralPath $script:InProgressPath)) {
                Write-Host 'Незавершённое состояние отсутствует.'
                return
            }
            $payload = Get-Content -Raw -LiteralPath $script:InProgressPath | ConvertFrom-Json
            try {
                Get-Process -Id ([int]$payload.pid) -ErrorAction Stop | Out-Null
                Stop-Update -Code 'UPDATE_IN_PROGRESS' -Summary 'Процесс из незавершённого состояния ещё работает.' -Deferred
            } catch [Microsoft.PowerShell.Commands.ProcessCommandException] {
                # The recorded process no longer exists; the named mutex check below is authoritative.
            }
            Enter-UpdateMutex
            try {
                Remove-Item -LiteralPath $script:InProgressPath -Force
                Write-Host 'Зависшее состояние обновления очищено; база данных не откатывалась.'
            } finally {
                Exit-UpdateMutex
            }
        }
    }
}

try {
    New-Item -ItemType Directory -Path $script:StateRoot -Force | Out-Null
    if ($TaskAction -ne 'None') {
        Invoke-TaskAction
        exit 0
    }
    if ($Mode -eq 'Status') {
        Invoke-Status
        exit 0
    }
    Enter-UpdateMutex
    try {
        if ($Mode -eq 'Check') {
            Invoke-Check
        } else {
            Invoke-Apply
        }
    } finally {
        Remove-InProgress
        Exit-UpdateMutex
    }
    exit $script:ExitCode
} catch {
    if (-not $script:FailureCode) {
        $script:FailureCode = 'UPDATE_FAILED'
        $script:FailureSummary = 'Обновление остановлено из-за ошибки.'
        $script:ExitCode = 1
        $script:CurrentResult.error_code = $script:FailureCode
    }
    $script:CurrentResult.result = if ($script:ExitCode -eq 2) { 'DEFERRED' } else { 'FAIL' }
    try { Save-Result } catch { }
    Write-Error $script:FailureSummary
    exit $script:ExitCode
}
