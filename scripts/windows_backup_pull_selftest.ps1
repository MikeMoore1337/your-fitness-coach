[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pullScript = Join-Path $scriptRoot "windows_backup_pull.ps1"
$shellName = if ($PSVersionTable.PSEdition -eq "Desktop") { "powershell.exe" } else { "pwsh.exe" }
$pwsh = Join-Path $PSHOME $shellName
$fixtureTime = [DateTimeOffset]::Parse("2026-10-18T12:00:00Z")
Write-Host "Runtime: $($PSVersionTable.PSVersion) ($pwsh)"
$runtimeRoot = Join-Path (Split-Path -Parent $scriptRoot) ".artifacts\runtime\tests"
$root = Join-Path $runtimeRoot ("yfc-backup-selftest-" + [guid]::NewGuid().ToString("N"))
$remote = Join-Path $root "remote"
$local = Join-Path $root "local"
$configPath = Join-Path $root "config.json"
$fakeSftp = Join-Path $root "fake-sftp.cmd"
$fakeSftpHelper = Join-Path $root "fake-sftp-helper.ps1"
$identity = Join-Path $root "identity"
$knownHosts = Join-Path $root "known_hosts"
$outputPath = Join-Path $root "output.txt"
$errorPath = Join-Path $root "error.txt"
$holdPath = Join-Path $root "sftp-hold"
$startedPath = Join-Path $root "sftp-started"
$firstOutputPath = Join-Path $root "first-output.txt"
$firstErrorPath = Join-Path $root "first-error.txt"
$clockPath = Join-Path $root "clock.txt"

function Set-TestTime {
    param([DateTimeOffset]$Now)
    [IO.File]::WriteAllText($clockPath, $Now.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"))
}

function Write-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][object]$Value)
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function New-Manifest {
    param(
        [Parameter(Mandatory = $true)][string]$ArchiveName,
        [Parameter(Mandatory = $true)][string]$CreatedAt,
        [Parameter(Mandatory = $true)][string]$Digest,
        [Parameter(Mandatory = $true)][int64]$Size
    )
    return [ordered]@{
        schema_version = 2
        kind = "yfc-backup-manifest"
        source = "vps"
        archive_name = $ArchiveName
        manifest_name = "$ArchiveName.manifest.json"
        archive_size_bytes = $Size
        archive_sha256 = $Digest
        created_at_utc = $CreatedAt
        published_at_utc = $CreatedAt
        database_major = "16"
        schema_revision = "20261018_01"
        archive_format = "age-v1"
        age_version = "v1.3.2"
        recipient = ("age1" + ("q" * 58))
        verification_status = "format_verified_pg_restore_list"
        restore_status = "not_run"
        application_identity = [ordered]@{
            status = "not_provided"
            git_sha = "unknown"
            backend_image_digest = "unknown"
            bot_image_digest = "unknown"
        }
        coverage = [ordered]@{ postgresql = "included" }
    }
}

function Add-RemoteBackup {
    param(
        [Parameter(Mandatory = $true)][string]$ArchiveName,
        [Parameter(Mandatory = $true)][byte[]]$Bytes,
        [Parameter(Mandatory = $true)][string]$CreatedAt,
        [string]$ManifestDigest
    )
    $Bytes = [Text.Encoding]::ASCII.GetBytes("age-encryption.org/v1`n-> X25519 ") + $Bytes
    $archivePath = Join-Path $remote $ArchiveName
    [IO.File]::WriteAllBytes($archivePath, $Bytes)
    $digest = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($ManifestDigest)) { $ManifestDigest = $digest }
    $manifest = New-Manifest $ArchiveName $CreatedAt $ManifestDigest ([int64]$Bytes.Length)
    Write-JsonFile (Join-Path $remote "$ArchiveName.manifest.json") $manifest
    return [ordered]@{
        manifest_name = "$ArchiveName.manifest.json"
        archive_name = $ArchiveName
        archive_size_bytes = [int64]$Bytes.Length
        archive_sha256 = $ManifestDigest
        created_at_utc = $CreatedAt
        published_at_utc = $CreatedAt
        archive_format = "age-v1"
        age_version = "v1.3.2"
        recipient = ("age1" + ("q" * 58))
        verification_status = "format_verified_pg_restore_list"
    }
}

function Write-RemoteIndex {
    param([Parameter(Mandatory = $true)][object[]]$Entries)
    Write-JsonFile (Join-Path $remote "index.json") ([ordered]@{
            schema_version = 2
            kind = "yfc-backup-index"
            generated_at_utc = [IO.File]::ReadAllText($clockPath)
            backups = @($Entries)
        })
}

function Invoke-PullCase {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][int]$ExpectedCode, [string]$Failure)
    $before = @{}
    if ($ExpectedCode -ge 11) {
        foreach ($file in @(Get-ChildItem -LiteralPath $local -File | Where-Object { $_.Name -like "*.dump.age" -or $_.Name -like "*.manifest.json" })) {
            $before[$file.FullName] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        }
    }
    $env:YFC_FAKE_SFTP_FAILURE = $Failure
    & $pwsh "-NoProfile" "-File" $pullScript "-Mode" "Pull" "-ConfigPath" $configPath "-SftpPath" $fakeSftp 1> $outputPath 2> $errorPath
    $exitCode = $LASTEXITCODE
    Remove-Item Env:YFC_FAKE_SFTP_FAILURE -ErrorAction SilentlyContinue
    if ($exitCode -ne $ExpectedCode) {
        $statusPath = Join-Path $local "backup-status.json"
        $logPath = Join-Path $local "backup-pull.log"
        throw "$Name expected exit code $ExpectedCode, got ${exitCode}: stdout=$(Get-Content $outputPath -Raw) stderr=$(Get-Content $errorPath -Raw) status=$(if (Test-Path $statusPath) { Get-Content $statusPath -Raw }) log=$(if (Test-Path $logPath) { Get-Content $logPath -Raw })"
    }
    foreach ($path in $before.Keys) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $before[$path]) {
            throw "$Name deleted or changed a pre-existing backup: $path"
        }
    }
    Write-Host "PASS $Name ($ExpectedCode)"
}

function Get-OutputStatus {
    return (Get-Content -LiteralPath $outputPath -Raw | ConvertFrom-Json)
}

function Invoke-StatusCase {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][int]$ExpectedCode)
    & $pwsh "-NoProfile" "-File" $pullScript "-Mode" "Status" "-ConfigPath" $configPath "-SftpPath" $fakeSftp 1> $outputPath 2> $errorPath
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne $ExpectedCode) {
        throw "$Name expected exit code $ExpectedCode, got ${exitCode}: stdout=$(Get-Content $outputPath -Raw) stderr=$(Get-Content $errorPath -Raw)"
    }
    Write-Host "PASS $Name ($ExpectedCode)"
    return (Get-Content -LiteralPath $outputPath -Raw | ConvertFrom-Json)
}

function Wait-ForFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    for ($attempt = 0; $attempt -lt 200; $attempt++) {
        if (Test-Path -LiteralPath $Path -PathType Leaf) { return }
        Start-Sleep -Milliseconds 50
    }
    throw "timed out waiting for $Path"
}

try {
    [void](New-Item -ItemType Directory -Force -Path $remote, $local)
    # Override only the clock in an isolated runner; production has no test-time setting.
    $source = [IO.File]::ReadAllText($pullScript)
    $mainCall = '$exitCode = Invoke-Main'
    if ([regex]::Matches($source, [regex]::Escape($mainCall)).Count -ne 1) { throw "expected one main entry point" }
    $clockOverride = @'
function Get-NowUtc {
    return [DateTimeOffset]::Parse([IO.File]::ReadAllText($env:YFC_SELFTEST_CLOCK_FILE))
}
'@
    $pullScript = Join-Path $root "pull-under-test.ps1"
    [IO.File]::WriteAllText($pullScript, $source.Replace($mainCall, "$clockOverride`n$mainCall"))
    $env:YFC_SELFTEST_CLOCK_FILE = $clockPath
    Set-TestTime ($fixtureTime.AddHours(1))
    [IO.File]::WriteAllText($identity, "synthetic-key", (New-Object Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($knownHosts, "backup.example ssh-ed25519 AAAAsynthetic", (New-Object Text.UTF8Encoding($false)))
    $fakeSource = @'
@echo off
if "%YFC_FAKE_SFTP_FAILURE%"=="HOST_KEY" (echo Host key verification failed 1>&2 & exit /b 255)
if "%YFC_FAKE_SFTP_FAILURE%"=="AUTHENTICATION" (echo Permission denied (publickey) 1>&2 & exit /b 255)
if "%YFC_FAKE_SFTP_FAILURE%"=="NETWORK" (echo Connection timed out 1>&2 & exit /b 255)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0fake-sftp-helper.ps1" %*
exit /b %ERRORLEVEL%
'@
    $fakeHelperSource = @'
param()
foreach ($required in @("-F", "NUL", "-oBatchMode=yes", "-oStrictHostKeyChecking=yes", "-oGlobalKnownHostsFile=NUL", "-oIdentitiesOnly=yes", "-oIdentityAgent=none")) {
    if ($args -notcontains $required) { throw "missing SSH isolation option: $required" }
}
$batch = $args[([array]::IndexOf($args, "-b") + 1)]
$remoteRoot = $env:YFC_FAKE_REMOTE_ROOT
foreach ($line in @(Get-Content -LiteralPath $batch)) {
    if ($line -match '^get\s+(\S+)\s+"(.+)"$') {
        $source = Join-Path $remoteRoot $matches[1]
        $destination = $matches[2].Replace('\"', '"')
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { exit 0 }
        if ($env:YFC_FAKE_SFTP_FAILURE -eq "INTERRUPT" -and $source.EndsWith(".age")) {
            [IO.File]::WriteAllText($destination, "partial")
            [Console]::Error.WriteLine("Connection lost")
            exit 255
        }
        Copy-Item -LiteralPath $source -Destination $destination -Force
        if (-not [string]::IsNullOrWhiteSpace($env:YFC_FAKE_SFTP_STARTED_FILE)) {
            [IO.File]::WriteAllText($env:YFC_FAKE_SFTP_STARTED_FILE, "started")
            while (Test-Path -LiteralPath $env:YFC_FAKE_SFTP_HOLD_FILE -PathType Leaf) {
                Start-Sleep -Milliseconds 50
            }
        }
    }
}
exit 0
'@
    Set-Content -LiteralPath $fakeSftp -Value $fakeSource -Encoding ASCII
    Set-Content -LiteralPath $fakeSftpHelper -Value $fakeHelperSource -Encoding UTF8
    $env:YFC_FAKE_REMOTE_ROOT = $remote

    $config = [ordered]@{
        local_root = $local
        retention_days = 7
        minimum_valid_backups = 2
        stale_after_hours = 26
        minimum_free_bytes = 0
        encryption_at_rest = [ordered]@{
            mode = "age"
            recipient = ("age1" + ("q" * 58))
            approved = $true
            key_recovery_document = "synthetic-only"
        }
        lock_file = (Join-Path $local "backup-pull.lock")
        status_file = (Join-Path $local "backup-status.json")
        log_file = (Join-Path $local "backup-pull.log")
        ssh = [ordered]@{
            host = "backup.example"
            user = "yfc-backup-readonly"
            port = 22
            identity_file = $identity
            known_hosts_file = $knownHosts
            remote_root = "/synthetic"
            remote_index = "index.json"
            connect_timeout_seconds = 2
            sftp_path = $fakeSftp
        }
    }
    Write-JsonFile $configPath $config

    $entry = Add-RemoteBackup "fitminiapp-20261018T120000Z.dump.age" ([Text.Encoding]::UTF8.GetBytes("synthetic-one")) ($fixtureTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"))
    Write-RemoteIndex @($entry)
    Invoke-PullCase "success" 0 ""
    $persistedSuccess = Get-Content -LiteralPath $config.status_file -Raw | ConvertFrom-Json
    if ($persistedSuccess.status_write_result -ne "SUCCESS") { throw "successful status write must persist SUCCESS in the status file" }
    Invoke-PullCase "repeat-is-idempotent" 0 ""

    foreach ($case in @(
        @{ Name = "younger-than-26h"; Seconds = 93599; Code = 0; State = "HEALTHY" },
        @{ Name = "exactly-26h"; Seconds = 93600; Code = 0; State = "HEALTHY" },
        @{ Name = "older-than-26h"; Seconds = 93601; Code = 10; State = "STALE" }
    )) {
        Set-TestTime ($fixtureTime.AddSeconds($case.Seconds))
        $status = Invoke-StatusCase $case.Name $case.Code
        if ($status.state -ne $case.State -or $status.freshness_state -ne $case.State -or [DateTimeOffset]$status.last_successful_backup_utc -ne [DateTimeOffset]$entry.created_at_utc) {
            throw "$($case.Name) must use source creation time and a strict >26h threshold"
        }
    }
    $receivedAt = (Get-OutputStatus).last_successful_copy_received_at_utc
    Invoke-PullCase "scheduler-success-without-new-archive-is-stale" 10 ""
    $noNewArchive = Get-OutputStatus
    if ($noNewArchive.state -ne "STALE" -or $noNewArchive.last_pull_result -ne "SUCCESS" -or $noNewArchive.downloaded_count -ne 0 -or $noNewArchive.last_successful_copy_received_at_utc -ne $receivedAt) {
        throw "successful hourly polling must not refresh the source backup age or copy receipt"
    }

    $config.Remove("stale_after_hours")
    Write-JsonFile $configPath $config
    Invoke-StatusCase "default-threshold-is-26h" 10 | Out-Null
    $config.stale_after_hours = 27
    Write-JsonFile $configPath $config
    Invoke-StatusCase "explicit-threshold-override" 0 | Out-Null
    $config.stale_after_hours = 0
    Write-JsonFile $configPath $config
    Invoke-StatusCase "invalid-threshold-rejected" 25 | Out-Null
    $config.stale_after_hours = 26
    Write-JsonFile $configPath $config

    # Re-publication and a new download receipt cannot make an old source dump fresh.
    $republished = New-Manifest $entry.archive_name $entry.created_at_utc $entry.archive_sha256 $entry.archive_size_bytes
    $republished.published_at_utc = [IO.File]::ReadAllText($clockPath)
    Write-JsonFile (Join-Path $remote $entry.manifest_name) $republished
    $entry.published_at_utc = $republished.published_at_utc
    Write-RemoteIndex @($entry)
    Remove-Item -LiteralPath (Join-Path $local $entry.manifest_name), (Join-Path $local $entry.archive_name) -Force
    Invoke-PullCase "repeat-download-and-publication-do-not-reset-age" 10 ""
    $redownloaded = Get-OutputStatus
    if ($redownloaded.downloaded_count -ne 1 -or $redownloaded.state -ne "STALE" -or [DateTimeOffset]$redownloaded.last_successful_backup_utc -ne [DateTimeOffset]$entry.created_at_utc -or $redownloaded.last_successful_copy_received_at_utc -eq $receivedAt) {
        throw "new receipt and publication must retain old source creation time"
    }
    Invoke-PullCase "vps-unavailable-with-stale-source" 22 "NETWORK"
    $unavailable = Invoke-StatusCase "vps-failure-and-staleness-remain-visible" 22
    if ($unavailable.state -ne "NETWORK" -or $unavailable.freshness_state -ne "STALE" -or $unavailable.last_pull_result -ne "FAILED" -or $unavailable.last_failure_code -ne "NETWORK") {
        throw "VPS failure and stale source must remain separate diagnostics"
    }

    Set-TestTime ($fixtureTime.AddHours(1))
    $entry.published_at_utc = $entry.created_at_utc
    Write-JsonFile (Join-Path $remote $entry.manifest_name) (New-Manifest $entry.archive_name $entry.created_at_utc $entry.archive_sha256 $entry.archive_size_bytes)
    Copy-Item -LiteralPath (Join-Path $remote $entry.manifest_name) -Destination (Join-Path $local $entry.manifest_name) -Force
    Write-RemoteIndex @($entry)
    Invoke-PullCase "freshness-fixture-recovery" 0 ""

    $config.encryption_at_rest.mode = "none"
    $config.encryption_at_rest.plaintext_risk_acknowledged = $true
    Write-JsonFile $configPath $config
    Invoke-PullCase "plaintext-opt-in-cannot-bypass-age" 25 ""
    $config.encryption_at_rest.mode = "age"
    Write-JsonFile $configPath $config

    $legacy = Join-Path $local "legacy.dump"
    [IO.File]::WriteAllText($legacy, "preserve-legacy")
    Invoke-PullCase "legacy-plaintext-requires-migration" 25 ""
    if ([IO.File]::ReadAllText($legacy) -ne "preserve-legacy") { throw "legacy copy changed" }
    Remove-Item -LiteralPath $legacy -Force

    Remove-Item -LiteralPath (Join-Path $local $entry.manifest_name) -Force
    Invoke-PullCase "orphan-archive-recovery" 0 ""

    foreach ($badVersion in @(1, "2", $true, 2.5)) {
        $badIndex = [ordered]@{ schema_version = $badVersion; kind = "yfc-backup-index"; generated_at_utc = $fixtureTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"); backups = @($entry) }
        Write-JsonFile (Join-Path $remote "index.json") $badIndex
        Invoke-PullCase "reject-schema-$badVersion" 12 ""
    }
    foreach ($mutation in @("archive_format", "age_version", "recipient", "archive_size_bytes")) {
        $changed = [ordered]@{}
        foreach ($key in $entry.Keys) { $changed[$key] = $entry[$key] }
        $changed[$mutation] = if ($mutation -eq "recipient") { "age1" + ("p" * 58) } elseif ($mutation -eq "archive_size_bytes") { "100" } else { "unsupported" }
        Write-RemoteIndex @($changed)
        Invoke-PullCase "reject-index-$mutation" 12 ""
    }
    $renamed = Add-RemoteBackup "renamed.dump.age" ([Text.Encoding]::UTF8.GetBytes("placeholder")) ($fixtureTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"))
    [IO.File]::WriteAllText((Join-Path $remote $renamed.archive_name), "PGDMP plaintext disguised as age")
    $renamed.archive_size_bytes = (Get-Item (Join-Path $remote $renamed.archive_name)).Length
    $renamed.archive_sha256 = (Get-FileHash (Join-Path $remote $renamed.archive_name)).Hash.ToLowerInvariant()
    $renamedManifest = New-Manifest $renamed.archive_name $renamed.created_at_utc $renamed.archive_sha256 $renamed.archive_size_bytes
    Write-JsonFile (Join-Path $remote $renamed.manifest_name) $renamedManifest
    Write-RemoteIndex @($renamed)
    Invoke-PullCase "plaintext-renamed-to-age-rejected-even-with-valid-hash" 12 ""

    $badEntry = Add-RemoteBackup "fitminiapp-20261018T120100Z.dump.age" ([Text.Encoding]::UTF8.GetBytes("synthetic-two")) ($fixtureTime.AddMinutes(1).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")) ("0" * 64)
    Write-RemoteIndex @($badEntry, $entry)
    Invoke-PullCase "interrupted-ciphertext-transfer" 22 "INTERRUPT"
    Invoke-PullCase "checksum-mismatch-preserves-valid-copy" 12 ""
    $corruptedDownload = Get-OutputStatus
    if ($corruptedDownload.valid_backup_count -ne 1 -or (Test-Path -LiteralPath (Join-Path $local $badEntry.archive_name))) { throw "corrupted download must not become a verified copy" }

    $truncated = Add-RemoteBackup "truncated.dump.age" ([Text.Encoding]::UTF8.GetBytes("complete-archive")) ($fixtureTime.AddMinutes(2).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"))
    [IO.File]::WriteAllText((Join-Path $remote $truncated.archive_name), "short")
    Write-RemoteIndex @($truncated, $entry)
    Invoke-PullCase "truncated-transfer-preserves-sole-copy" 12 ""

    $missingEntry = [ordered]@{
        manifest_name = "fitminiapp-20261018T120200Z.dump.age.manifest.json"
        archive_name = "fitminiapp-20261018T120200Z.dump.age"
        archive_size_bytes = 4
        archive_sha256 = ("1" * 64)
        created_at_utc = "2026-10-18T12:02:00Z"
        published_at_utc = "2026-10-18T12:02:00Z"
        archive_format = "age-v1"
        age_version = "v1.3.2"
        recipient = ("age1" + ("q" * 58))
        verification_status = "format_verified_pg_restore_list"
    }
    Write-RemoteIndex @($missingEntry, $entry)
    Invoke-PullCase "missing-manifest" 11 ""

    $unsafeEntry = [ordered]@{
        manifest_name = "../outside.dump.age.manifest.json"
        archive_name = "../outside.dump.age"
        archive_size_bytes = 4
        archive_sha256 = ("2" * 64)
        created_at_utc = "2026-10-18T12:02:00Z"
        published_at_utc = "2026-10-18T12:02:00Z"
        archive_format = "age-v1"
        age_version = "v1.3.2"
        recipient = ("age1" + ("q" * 58))
        verification_status = "format_verified_pg_restore_list"
    }
    Write-RemoteIndex @($unsafeEntry, $entry)
    Invoke-PullCase "unsafe-index-name" 12 ""
    if (Test-Path -LiteralPath (Join-Path $root "outside.dump.age")) { throw "unsafe manifest/index name escaped the local root" }

    Write-RemoteIndex @($entry)
    Invoke-PullCase "pinned-host-key-rejection" 20 "HOST_KEY"
    Invoke-PullCase "authentication-failure" 21 "AUTHENTICATION"
    Invoke-PullCase "network-timeout" 22 "NETWORK"

    $lockStream = [IO.File]::Open($config.lock_file, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try { Invoke-PullCase "concurrent-lock" 24 "" } finally { $lockStream.Dispose() }

    $concurrentEntry = Add-RemoteBackup "fitminiapp-20261018T121000Z.dump.age" ([Text.Encoding]::UTF8.GetBytes("synthetic-concurrent")) ($fixtureTime.AddMinutes(10).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"))
    Write-RemoteIndex @($concurrentEntry, $entry)
    [IO.File]::WriteAllText($holdPath, "hold", (New-Object Text.UTF8Encoding($false)))
    Remove-Item -LiteralPath $startedPath -Force -ErrorAction SilentlyContinue
    $env:YFC_FAKE_SFTP_HOLD_FILE = $holdPath
    $env:YFC_FAKE_SFTP_STARTED_FILE = $startedPath
    $firstArguments = "-NoProfile -File `"$pullScript`" -Mode Pull -ConfigPath `"$configPath`" -SftpPath `"$fakeSftp`""
    $firstProcess = $null
    try {
        $statusBefore = (Get-FileHash -LiteralPath $config.status_file -Algorithm SHA256).Hash
        $firstProcess = Start-Process -FilePath $pwsh -ArgumentList $firstArguments -WindowStyle Hidden -PassThru -RedirectStandardOutput $firstOutputPath -RedirectStandardError $firstErrorPath
        Wait-ForFile $startedPath
        $incomingDirs = @(Get-ChildItem -LiteralPath $local -Directory -Filter ".incoming-*" -ErrorAction SilentlyContinue)
        if ($incomingDirs.Count -ne 1) { throw "expected one isolated incoming directory while the first pull is held" }
        $incomingFilesBefore = @(Get-ChildItem -LiteralPath $incomingDirs[0].FullName -File | Sort-Object FullName | ForEach-Object { "$($_.FullName)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" })
        Invoke-PullCase "concurrent-lock-isolated" 24 "" | Out-Null
        $incomingFilesAfter = @(Get-ChildItem -LiteralPath $incomingDirs[0].FullName -File | Sort-Object FullName | ForEach-Object { "$($_.FullName)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" })
        if ((ConvertTo-Json $incomingFilesBefore) -ne (ConvertTo-Json $incomingFilesAfter)) { throw "locked pull changed the first pull temporary files" }
        $statusAfter = (Get-FileHash -LiteralPath $config.status_file -Algorithm SHA256).Hash
        if ($statusBefore -ne $statusAfter) { throw "locked pull changed the shared status file" }
        Remove-Item -LiteralPath $holdPath -Force
        if (-not $firstProcess.WaitForExit(15000)) { throw "first pull did not finish after lock release" }
        $firstStatus = Get-Content -LiteralPath $firstOutputPath -Raw | ConvertFrom-Json
        if ($firstStatus.last_run_result -ne "SUCCESS" -or $firstStatus.state -ne "HEALTHY" -or $firstStatus.downloaded_count -lt 1) { throw "first pull did not report successful continuation after lock release: $(Get-Content $firstOutputPath -Raw) $(Get-Content $firstErrorPath -Raw)" }
        if (-not (Test-Path -LiteralPath (Join-Path $local $concurrentEntry.archive_name) -PathType Leaf)) { throw "first pull did not promote its backup after lock release" }
        Write-Host "PASS concurrent-isolation-and-resume (24 then 0)"
    }
    finally {
        Remove-Item -LiteralPath $holdPath -Force -ErrorAction SilentlyContinue
        Remove-Item Env:YFC_FAKE_SFTP_HOLD_FILE -ErrorAction SilentlyContinue
        Remove-Item Env:YFC_FAKE_SFTP_STARTED_FILE -ErrorAction SilentlyContinue
        if ($null -ne $firstProcess -and -not $firstProcess.HasExited) { $firstProcess.Kill() }
    }

    $diskEntry = Add-RemoteBackup "fitminiapp-20261018T120300Z.dump.age" ([Text.Encoding]::UTF8.GetBytes("synthetic-three")) ($fixtureTime.AddMinutes(3).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"))
    Write-RemoteIndex @($diskEntry, $entry)
    $config.minimum_free_bytes = [int64]1000000000000000
    Write-JsonFile $configPath $config
    Invoke-PullCase "low-disk-margin" 23 ""
    $config.minimum_free_bytes = 0
    Write-JsonFile $configPath $config

    Write-RemoteIndex @($concurrentEntry, $entry)
    Invoke-PullCase "failed-pull-with-fresh-copy" 22 "NETWORK"
    $failedFresh = Get-OutputStatus
    if ($failedFresh.state -ne "NETWORK" -or $failedFresh.local_backup_state -ne "HEALTHY" -or $failedFresh.last_pull_result -ne "FAILED") {
        throw "failed pull with a fresh copy must expose NETWORK while preserving local HEALTHY state"
    }

    $localManifests = @(Get-ChildItem -LiteralPath $local -Filter "*.manifest.json" -File)
    foreach ($manifestPath in $localManifests) {
        $stale = Get-Content -LiteralPath $manifestPath.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $stale.created_at_utc = "2020-01-01T00:00:00Z"
        $stale.published_at_utc = "2020-01-01T00:00:00Z"
        Write-JsonFile $manifestPath.FullName $stale
    }
    Invoke-PullCase "failed-pull-with-stale-copy" 22 "NETWORK"
    $failedStale = Get-OutputStatus
    if ($failedStale.state -ne "NETWORK" -or $failedStale.freshness_state -ne "STALE" -or $failedStale.last_failure_code -ne "NETWORK") {
        throw "failed pull with a stale copy must expose NETWORK and STALE separately"
    }

    Copy-Item -LiteralPath (Join-Path $remote $entry.manifest_name) -Destination (Join-Path $local $entry.manifest_name) -Force
    Copy-Item -LiteralPath (Join-Path $remote $concurrentEntry.manifest_name) -Destination (Join-Path $local $concurrentEntry.manifest_name) -Force
    Invoke-PullCase "successful-pull-after-failure" 0 ""
    $recovered = Get-OutputStatus
    if ($recovered.state -ne "HEALTHY" -or $recovered.last_pull_result -ne "SUCCESS" -or $recovered.last_failure_code -ne "NETWORK" -or [string]::IsNullOrWhiteSpace($recovered.last_successful_sync_at_utc)) {
        throw "successful recovery must restore HEALTHY and retain the prior failure record"
    }

    $statusDirectory = Join-Path $local "status-target-directory"
    [void](New-Item -ItemType Directory -Force -Path $statusDirectory)
    $originalStatusPath = $config.status_file
    $config.status_file = $statusDirectory
    Write-JsonFile $configPath $config
    Invoke-PullCase "failed-status-write" 22 "NETWORK"
    $failedStatusWrite = Get-OutputStatus
    if ($failedStatusWrite.status_write_result -ne "FAILED") { throw "failed status write must be visible in the pull result" }
    $failureSidecarPath = "$($config.status_file).failure"
    if (-not (Test-Path -LiteralPath $failureSidecarPath -PathType Leaf)) { throw "failed status write must preserve a failure sidecar" }
    $failureSidecar = Get-Content -LiteralPath $failureSidecarPath -Raw | ConvertFrom-Json
    if ($failureSidecar.last_run_result -ne "FAILED" -or $failureSidecar.last_failure_code -ne "NETWORK") { throw "failure sidecar must preserve the failed pull" }
    $statusAfterWriteFailure = Invoke-StatusCase "failed-status-write-retains-error" 22
    if ($statusAfterWriteFailure.state -ne "NETWORK" -or $statusAfterWriteFailure.last_failure_code -ne "NETWORK") { throw "status sidecar did not preserve the failed pull when the primary status write failed" }
    Invoke-PullCase "successful-status-write-failure" 27 ""
    $successfulStatusWriteFailure = Get-OutputStatus
    if ($successfulStatusWriteFailure.state -ne "UNEXPECTED" -or $successfulStatusWriteFailure.last_run_result -ne "FAILED" -or $successfulStatusWriteFailure.last_failure_code -ne "UNEXPECTED" -or $successfulStatusWriteFailure.status_write_result -ne "FAILED") {
        throw "a successful sync with a failed status write must report an UNEXPECTED persisted failure"
    }
    $statusAfterSuccessfulWriteFailure = Invoke-StatusCase "successful-status-write-failure-retains-error" 27
    if ($statusAfterSuccessfulWriteFailure.state -ne "UNEXPECTED" -or $statusAfterSuccessfulWriteFailure.last_failure_code -ne "UNEXPECTED") {
        throw "Status must retain a failed status write after re-evaluating local files"
    }
    $config.status_file = $originalStatusPath
    Write-JsonFile $configPath $config
    Invoke-PullCase "status-write-recovery" 0 "" | Out-Null

    foreach ($manifestPath in @(Get-ChildItem -LiteralPath $local -Filter "*.manifest.json" -File)) {
        $future = Get-Content -LiteralPath $manifestPath.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $future.created_at_utc = "2999-01-01T00:00:00Z"
        $future.published_at_utc = "2999-01-01T00:00:00Z"
        Write-JsonFile $manifestPath.FullName $future
    }
    $futureStatus = Invoke-StatusCase "future-timestamp-is-corrupted" 12
    if ($futureStatus.state -ne "CORRUPTED" -or $futureStatus.local_backup_state -ne "CORRUPTED") { throw "a substantially future backup timestamp must not be HEALTHY" }
    Copy-Item -LiteralPath (Join-Path $remote $entry.manifest_name) -Destination (Join-Path $local $entry.manifest_name) -Force
    Copy-Item -LiteralPath (Join-Path $remote $concurrentEntry.manifest_name) -Destination (Join-Path $local $concurrentEntry.manifest_name) -Force

    $corruptArchivePath = Join-Path $local $concurrentEntry.archive_name
    [IO.File]::WriteAllText($corruptArchivePath, "corrupted-local-copy", (New-Object Text.UTF8Encoding($false)))
    $corruptStatus = Invoke-StatusCase "corrupted-local-copy" 12
    if ($corruptStatus.state -ne "CORRUPTED" -or $corruptStatus.invalid_backup_count -lt 1) { throw "a damaged local archive must be CORRUPTED" }
    Copy-Item -LiteralPath (Join-Path $remote $concurrentEntry.archive_name) -Destination $corruptArchivePath -Force

    foreach ($days in @(9, 8, 6)) {
        $old = Add-RemoteBackup "retention-$days.dump.age" ([Text.Encoding]::UTF8.GetBytes("retention-$days")) ($fixtureTime.AddDays(-$days).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"))
        Copy-Item -LiteralPath (Join-Path $remote $old.archive_name) -Destination (Join-Path $local $old.archive_name)
        Copy-Item -LiteralPath (Join-Path $remote $old.manifest_name) -Destination (Join-Path $local $old.manifest_name)
    }
    $rotationLock = [IO.File]::Open((Join-Path $local "retention-9.dump.age.manifest.json"), [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try { Invoke-PullCase "rotation-failure-preserves-verified-copies" 26 "" } finally { $rotationLock.Dispose() }
    Invoke-PullCase "seven-day-rotation" 0 ""
    $rotated = Get-OutputStatus
    if ($rotated.rotated_count -ne 2 -or $rotated.valid_backup_count -ne 3) { throw "rotation must remove exactly the two expired copies" }
    foreach ($days in @(9, 8)) {
        foreach ($suffix in @(".dump.age", ".dump.age.manifest.json")) {
            if (Test-Path -LiteralPath (Join-Path $local "retention-$days$suffix")) { throw "expired backup was not removed" }
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $local "retention-6.dump.age"))) { throw "rotation removed an in-window backup" }

    # Advance archive age without running a pull: models the interval while the PC is off.
    $statusBeforeOffline = (Get-FileHash -LiteralPath $config.status_file -Algorithm SHA256).Hash
    foreach ($manifestPath in @(Get-ChildItem -LiteralPath $local -Filter "*.manifest.json" -File)) {
        $offline = Get-Content -LiteralPath $manifestPath.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $offline.created_at_utc = $fixtureTime.AddDays(-10).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
        $offline.published_at_utc = $offline.created_at_utc
        Write-JsonFile $manifestPath.FullName $offline
    }
    $offlineStatus = Invoke-StatusCase "pc-offline-stale-without-pull" 10
    if ($offlineStatus.valid_backup_count -ne 3 -or $offlineStatus.freshness_state -ne "STALE") { throw "offline copies must remain valid but stale" }
    if ((Get-FileHash -LiteralPath $config.status_file -Algorithm SHA256).Hash -ne $statusBeforeOffline) { throw "Status must not rewrite the last pull receipt" }
    Invoke-PullCase "offline-vps-failure-preserves-expired-copies" 22 "NETWORK"

    $catchup = Add-RemoteBackup "catchup.dump.age" ([Text.Encoding]::UTF8.GetBytes("after-offline")) ($fixtureTime.AddMinutes(15).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"))
    Write-RemoteIndex @($catchup, $concurrentEntry, $entry)
    Invoke-PullCase "pc-restart-catchup-and-minimum-two" 0 ""
    $caughtUp = Get-OutputStatus
    if ($caughtUp.downloaded_count -ne 1 -or $caughtUp.rotated_count -ne 2 -or $caughtUp.valid_backup_count -ne 2 -or $caughtUp.newest_archive_name -ne $catchup.archive_name) {
        throw "catchup must download the new archive and preserve two verified copies even outside retention"
    }

    foreach ($backupPath in @(Get-ChildItem -LiteralPath $local -File | Where-Object { $_.Name -like "*.dump.age" -or $_.Name -like "*.manifest.json" })) {
        Remove-Item -LiteralPath $backupPath.FullName -Force
    }
    $missingStatus = Invoke-StatusCase "missing-local-copies" 11
    if ($missingStatus.state -ne "MISSING" -or $missingStatus.local_backup_state -ne "MISSING") { throw "absence of local copies must be MISSING" }
    Invoke-PullCase "vps-unavailable-without-local-copies" 22 "NETWORK"
    $noCopies = Get-OutputStatus
    if ($noCopies.state -ne "NETWORK" -or $noCopies.freshness_state -ne "MISSING" -or $noCopies.valid_backup_count -ne 0) { throw "network failure must not hide missing independent copies" }
    Copy-Item -LiteralPath (Join-Path $remote $entry.archive_name) -Destination (Join-Path $local $entry.archive_name) -Force
    Copy-Item -LiteralPath (Join-Path $remote $entry.manifest_name) -Destination (Join-Path $local $entry.manifest_name) -Force
    Copy-Item -LiteralPath (Join-Path $remote $concurrentEntry.archive_name) -Destination (Join-Path $local $concurrentEntry.archive_name) -Force
    Copy-Item -LiteralPath (Join-Path $remote $concurrentEntry.manifest_name) -Destination (Join-Path $local $concurrentEntry.manifest_name) -Force

    $config.encryption_at_rest.approved = $false
    Write-JsonFile $configPath $config
    Invoke-PullCase "encryption-approval-gate" 25 ""
    $config.encryption_at_rest.approved = "false"
    Write-JsonFile $configPath $config
    Invoke-PullCase "encryption-approval-type-gate" 25 ""
    [IO.File]::WriteAllText($configPath, "{", (New-Object Text.UTF8Encoding($false)))
    Invoke-PullCase "malformed-config" 25 ""
    [IO.File]::WriteAllText($configPath, "[]", (New-Object Text.UTF8Encoding($false)))
    Invoke-PullCase "non-object-config" 25 ""
    Write-Host "Synthetic Windows pull scenarios passed. Root: $root"
}
finally {
    Remove-Item Env:YFC_SELFTEST_CLOCK_FILE -ErrorAction SilentlyContinue
    Remove-Item Env:YFC_FAKE_REMOTE_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:YFC_FAKE_SFTP_FAILURE -ErrorAction SilentlyContinue
    Remove-Item Env:YFC_FAKE_SFTP_HOLD_FILE -ErrorAction SilentlyContinue
    Remove-Item Env:YFC_FAKE_SFTP_STARTED_FILE -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
