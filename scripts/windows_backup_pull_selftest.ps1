[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pullScript = Join-Path $scriptRoot "windows_backup_pull.ps1"
$pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if ([string]::IsNullOrWhiteSpace($pwsh)) { $pwsh = (Get-Command powershell).Source }
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
        schema_version = 1
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
        verification_status = "format_verified_pg_restore_list"
    }
}

function Write-RemoteIndex {
    param([Parameter(Mandatory = $true)][object[]]$Entries)
    Write-JsonFile (Join-Path $remote "index.json") ([ordered]@{
            schema_version = 1
            kind = "yfc-backup-index"
            generated_at_utc = "2026-10-18T12:00:00Z"
            backups = @($Entries)
        })
}

function Invoke-PullCase {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][int]$ExpectedCode, [string]$Failure)
    $env:YFC_FAKE_SFTP_FAILURE = $Failure
    & $pwsh "-NoProfile" "-File" $pullScript "-Mode" "Pull" "-ConfigPath" $configPath "-SftpPath" $fakeSftp 1> $outputPath 2> $errorPath
    $exitCode = $LASTEXITCODE
    Remove-Item Env:YFC_FAKE_SFTP_FAILURE -ErrorAction SilentlyContinue
    if ($exitCode -ne $ExpectedCode) {
        $statusPath = Join-Path $local "backup-status.json"
        $logPath = Join-Path $local "backup-pull.log"
        throw "$Name expected exit code $ExpectedCode, got ${exitCode}: stdout=$(Get-Content $outputPath -Raw) stderr=$(Get-Content $errorPath -Raw) status=$(if (Test-Path $statusPath) { Get-Content $statusPath -Raw }) log=$(if (Test-Path $logPath) { Get-Content $logPath -Raw })"
    }
    Write-Host "PASS $Name ($ExpectedCode)"
}

try {
    [void](New-Item -ItemType Directory -Force -Path $remote, $local)
    [IO.File]::WriteAllText($identity, "synthetic-key", (New-Object Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($knownHosts, "backup.example ssh-ed25519 AAAAsynthetic", (New-Object Text.UTF8Encoding($false)))
    $fakeSource = @'
@echo off
if "%YFC_FAKE_SFTP_FAILURE%"=="HOST_KEY" (echo Host key verification failed 1>&2 & exit /b 255)
if "%YFC_FAKE_SFTP_FAILURE%"=="AUTHENTICATION" (echo Permission denied (publickey) 1>&2 & exit /b 255)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0fake-sftp-helper.ps1" %*
exit /b %ERRORLEVEL%
'@
    $fakeHelperSource = @'
param()
$batch = $args[([array]::IndexOf($args, "-b") + 1)]
$remoteRoot = $env:YFC_FAKE_REMOTE_ROOT
foreach ($line in @(Get-Content -LiteralPath $batch)) {
    if ($line -match '^get\s+(\S+)\s+"(.+)"$') {
        $source = Join-Path $remoteRoot $matches[1]
        $destination = $matches[2].Replace('\"', '"')
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { exit 0 }
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}
exit 0
'@
    Set-Content -LiteralPath $fakeSftp -Value $fakeSource -Encoding ASCII
    Set-Content -LiteralPath $fakeSftpHelper -Value $fakeHelperSource -Encoding UTF8
    $env:YFC_FAKE_REMOTE_ROOT = $remote

    $config = [ordered]@{
        local_root = $local
        retention_days = 30
        minimum_valid_backups = 2
        stale_after_hours = 36
        minimum_free_bytes = 0
        encryption_at_rest = [ordered]@{
            mode = "bitlocker"
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

    $entry = Add-RemoteBackup "fitminiapp-20261018T120000Z.dump" ([Text.Encoding]::UTF8.GetBytes("synthetic-one")) "2026-10-18T12:00:00Z"
    Write-RemoteIndex @($entry)
    Invoke-PullCase "success" 0 ""
    Invoke-PullCase "repeat-is-idempotent" 0 ""
    Remove-Item -LiteralPath (Join-Path $local $entry.manifest_name) -Force
    Invoke-PullCase "orphan-archive-recovery" 0 ""

    $badEntry = Add-RemoteBackup "fitminiapp-20261018T120100Z.dump" ([Text.Encoding]::UTF8.GetBytes("synthetic-two")) "2026-10-18T12:01:00Z" ("0" * 64)
    Write-RemoteIndex @($badEntry, $entry)
    Invoke-PullCase "checksum-mismatch-preserves-valid-copy" 12 ""

    $missingEntry = [ordered]@{
        manifest_name = "fitminiapp-20261018T120200Z.dump.manifest.json"
        archive_name = "fitminiapp-20261018T120200Z.dump"
        archive_size_bytes = 4
        archive_sha256 = ("1" * 64)
        created_at_utc = "2026-10-18T12:02:00Z"
        verification_status = "format_verified_pg_restore_list"
    }
    Write-RemoteIndex @($missingEntry, $entry)
    Invoke-PullCase "missing-manifest" 11 ""

    Write-RemoteIndex @($entry)
    Invoke-PullCase "pinned-host-key-rejection" 20 "HOST_KEY"

    $localManifest = Join-Path $local $entry.manifest_name
    $stale = Get-Content -LiteralPath $localManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $stale.created_at_utc = "2020-01-01T00:00:00Z"
    $stale.published_at_utc = "2020-01-01T00:00:00Z"
    Write-JsonFile $localManifest $stale
    & $pwsh "-NoProfile" "-File" $pullScript "-Mode" "Status" "-ConfigPath" $configPath "-SftpPath" $fakeSftp 1> $outputPath 2> $errorPath
    $statusExitCode = $LASTEXITCODE
    if ($statusExitCode -ne 10) { throw "stale status expected exit code 10, got $statusExitCode" }
    Write-Host "PASS stale-status (10)"

    $config.encryption_at_rest.approved = $false
    Write-JsonFile $configPath $config
    Invoke-PullCase "encryption-approval-gate" 25 ""
    Write-Host "Synthetic Windows pull scenarios passed. Root: $root"
}
finally {
    Remove-Item Env:YFC_FAKE_REMOTE_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:YFC_FAKE_SFTP_FAILURE -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
