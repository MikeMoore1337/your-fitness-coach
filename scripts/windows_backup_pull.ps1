[CmdletBinding()]
param(
    [ValidateSet("Pull", "Status")]
    [string]$Mode = "Pull",
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,
    [string]$SftpPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExitCodes = @{
    HEALTHY = 0
    STALE = 10
    MISSING = 11
    CORRUPTED = 12
    HOST_KEY = 20
    AUTHENTICATION = 21
    NETWORK = 22
    DISK_FULL = 23
    LOCKED = 24
    CONFIG_INVALID = 25
    PROMOTE_FAILED = 26
    UNEXPECTED = 27
}

function Throw-BackupPullError {
    param(
        [Parameter(Mandatory = $true)][string]$Code,
        [Parameter(Mandatory = $true)][string]$Message
    )
    $exception = New-Object System.Exception $Message
    $exception.Data["BackupCode"] = $Code
    throw $exception
}

function Get-PropertyValue {
    param([object]$Object, [Parameter(Mandatory = $true)][string]$Name)
    if ($null -eq $Object) {
        return $null
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Resolve-ConfiguredPath {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$BasePath
    )
    if ([IO.Path]::IsPathRooted($Value)) {
        return [IO.Path]::GetFullPath($Value)
    }
    return [IO.Path]::GetFullPath((Join-Path $BasePath $Value))
}

function Get-UtcString {
    return [DateTimeOffset]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
}

function ConvertTo-UtcDate {
    param([object]$Value, [string]$FieldName = "timestamp")
    try {
        if ($Value -is [DateTime]) {
            if ($Value.Kind -ne [DateTimeKind]::Utc) {
                Throw-BackupPullError "CORRUPTED" "$FieldName must be UTC"
            }
            return ([DateTimeOffset]$Value).ToUniversalTime()
        }
        $text = [string]$Value
        if (-not $text.EndsWith("Z")) {
            Throw-BackupPullError "CORRUPTED" "$FieldName must be UTC"
        }
        return [DateTimeOffset]::Parse($text).ToUniversalTime()
    }
    catch {
        if ($_.Exception.Data.Contains("BackupCode")) {
            throw
        }
        Throw-BackupPullError "CORRUPTED" "$FieldName is invalid"
    }
}

function Assert-SafeFileName {
    param([object]$Value, [Parameter(Mandatory = $true)][string]$FieldName)
    $text = [string]$Value
    if (-not [regex]::IsMatch($text, "^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")) {
        Throw-BackupPullError "CORRUPTED" "$FieldName is not a safe file name"
    }
    return $text
}

function Assert-Sha256 {
    param([object]$Value, [Parameter(Mandatory = $true)][string]$FieldName)
    $text = [string]$Value
    if (-not [regex]::IsMatch($text, "^[0-9a-f]{64}$")) {
        Throw-BackupPullError "CORRUPTED" "$FieldName is not a lowercase SHA-256 digest"
    }
    return $text
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Read-JsonObject {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $jsonParameters = @{}
        if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey("DateKind")) {
            $jsonParameters["DateKind"] = "String"
        }
        $value = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json @jsonParameters
    }
    catch {
        Throw-BackupPullError "CORRUPTED" "backup metadata is not valid JSON"
    }
    if ($null -eq $value -or $value -is [Array]) {
        Throw-BackupPullError "CORRUPTED" "backup metadata must be a JSON object"
    }
    return $value
}

function Assert-ManifestEntry {
    param([Parameter(Mandatory = $true)][object]$Manifest)
    if ((Get-PropertyValue $Manifest "schema_version") -ne 1) {
        Throw-BackupPullError "CORRUPTED" "unsupported backup manifest schema"
    }
    if ((Get-PropertyValue $Manifest "kind") -ne "yfc-backup-manifest") {
        Throw-BackupPullError "CORRUPTED" "unexpected backup manifest kind"
    }
    if ((Get-PropertyValue $Manifest "source") -ne "vps") {
        Throw-BackupPullError "CORRUPTED" "backup manifest source is not vps"
    }
    $archiveName = Assert-SafeFileName (Get-PropertyValue $Manifest "archive_name") "archive_name"
    $manifestName = Assert-SafeFileName (Get-PropertyValue $Manifest "manifest_name") "manifest_name"
    if ($manifestName -ne "$archiveName.manifest.json") {
        Throw-BackupPullError "CORRUPTED" "manifest_name does not match archive_name"
    }
    $size = [int64](Get-PropertyValue $Manifest "archive_size_bytes")
    if ($size -le 0) {
        Throw-BackupPullError "CORRUPTED" "archive_size_bytes must be positive"
    }
    [void](Assert-Sha256 (Get-PropertyValue $Manifest "archive_sha256") "archive_sha256")
    [void](ConvertTo-UtcDate (Get-PropertyValue $Manifest "created_at_utc") "created_at_utc")
    [void](ConvertTo-UtcDate (Get-PropertyValue $Manifest "published_at_utc") "published_at_utc")
    if (-not [regex]::IsMatch([string](Get-PropertyValue $Manifest "database_major"), "^[0-9]{1,3}$")) {
        Throw-BackupPullError "CORRUPTED" "database_major is invalid"
    }
    if (-not [regex]::IsMatch([string](Get-PropertyValue $Manifest "schema_revision"), "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")) {
        Throw-BackupPullError "CORRUPTED" "schema_revision is invalid"
    }
    if ((Get-PropertyValue $Manifest "verification_status") -ne "format_verified_pg_restore_list") {
        Throw-BackupPullError "CORRUPTED" "backup is not marked as pg_restore-list verified"
    }
    if ((Get-PropertyValue $Manifest "restore_status") -ne "not_run") {
        Throw-BackupPullError "CORRUPTED" "restore_status must remain not_run until Phase C"
    }
    $identity = Get-PropertyValue $Manifest "application_identity"
    if ($null -eq $identity -or [string](Get-PropertyValue $identity "status") -notin @("provided", "not_provided")) {
        Throw-BackupPullError "CORRUPTED" "application identity is missing"
    }
    foreach ($identityField in @("git_sha", "backend_image_digest", "bot_image_digest")) {
        if ([string]::IsNullOrWhiteSpace([string](Get-PropertyValue $identity $identityField))) {
            Throw-BackupPullError "CORRUPTED" "application identity is incomplete"
        }
    }
    if ($null -eq (Get-PropertyValue $Manifest "coverage")) {
        Throw-BackupPullError "CORRUPTED" "backup coverage is missing"
    }
    return $Manifest
}

function Assert-IndexEntry {
    param([Parameter(Mandatory = $true)][object]$Entry)
    $archiveName = Assert-SafeFileName (Get-PropertyValue $Entry "archive_name") "archive_name"
    $manifestName = Assert-SafeFileName (Get-PropertyValue $Entry "manifest_name") "manifest_name"
    if ($manifestName -ne "$archiveName.manifest.json") {
        Throw-BackupPullError "CORRUPTED" "index manifest_name does not match archive_name"
    }
    if ([int64](Get-PropertyValue $Entry "archive_size_bytes") -le 0) {
        Throw-BackupPullError "CORRUPTED" "index archive_size_bytes must be positive"
    }
    [void](Assert-Sha256 (Get-PropertyValue $Entry "archive_sha256") "archive_sha256")
    [void](ConvertTo-UtcDate (Get-PropertyValue $Entry "created_at_utc") "created_at_utc")
    if ((Get-PropertyValue $Entry "verification_status") -ne "format_verified_pg_restore_list") {
        Throw-BackupPullError "CORRUPTED" "index contains an unverified backup"
    }
    return $Entry
}

function Assert-BackupIndex {
    param([Parameter(Mandatory = $true)][object]$Index)
    if ((Get-PropertyValue $Index "schema_version") -ne 1) {
        Throw-BackupPullError "CORRUPTED" "unsupported backup index schema"
    }
    if ((Get-PropertyValue $Index "kind") -ne "yfc-backup-index") {
        Throw-BackupPullError "CORRUPTED" "unexpected backup index kind"
    }
    [void](ConvertTo-UtcDate (Get-PropertyValue $Index "generated_at_utc") "generated_at_utc")
    $entries = @((Get-PropertyValue $Index "backups"))
    if ($entries.Count -gt 10000) {
        Throw-BackupPullError "CORRUPTED" "backup index is too large"
    }
    $seen = @{}
    foreach ($entry in $entries) {
        [void](Assert-IndexEntry $entry)
        $name = [string](Get-PropertyValue $entry "archive_name")
        if ($seen.ContainsKey($name)) {
            Throw-BackupPullError "CORRUPTED" "backup index contains duplicate archive names"
        }
        $seen[$name] = $true
    }
    return $entries
}

function Read-Config {
    param([Parameter(Mandatory = $true)][string]$Path, [string]$SftpOverride)
    $configFullPath = [IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $configFullPath -PathType Leaf)) {
        Throw-BackupPullError "CONFIG_INVALID" "configuration file is missing"
    }
    $configDir = Split-Path -Parent $configFullPath
    $raw = Read-JsonObject $configFullPath
    $ssh = Get-PropertyValue $raw "ssh"
    if ($null -eq $ssh) {
        Throw-BackupPullError "CONFIG_INVALID" "ssh configuration is missing"
    }
    if ($null -ne (Get-PropertyValue $raw "password") -or $null -ne (Get-PropertyValue $ssh "password")) {
        Throw-BackupPullError "CONFIG_INVALID" "passwords are not supported; use an SSH identity"
    }
    $encryption = Get-PropertyValue $raw "encryption_at_rest"
    if ($null -eq $encryption) {
        Throw-BackupPullError "CONFIG_INVALID" "encryption_at_rest approval is required"
    }
    $encryptionMode = [string](Get-PropertyValue $encryption "mode")
    $encryptionApproved = [bool](Get-PropertyValue $encryption "approved")
    if ($encryptionMode -notin @("bitlocker", "file_encryption", "OWNER_APPROVAL_REQUIRED")) {
        Throw-BackupPullError "CONFIG_INVALID" "encryption_at_rest mode is unsupported"
    }
    $localValue = [string](Get-PropertyValue $raw "local_root")
    if ([string]::IsNullOrWhiteSpace($localValue)) {
        Throw-BackupPullError "CONFIG_INVALID" "local_root is required"
    }
    $localRoot = Resolve-ConfiguredPath $localValue $configDir
    [void](New-Item -ItemType Directory -Force -Path $localRoot)
    $hostName = [string](Get-PropertyValue $ssh "host")
    $userName = [string](Get-PropertyValue $ssh "user")
    $remoteRoot = ([string](Get-PropertyValue $ssh "remote_root")).TrimEnd("/")
    if ([string]::IsNullOrWhiteSpace($hostName) -or [string]::IsNullOrWhiteSpace($userName)) {
        Throw-BackupPullError "CONFIG_INVALID" "ssh host and user are required"
    }
    if (-not [regex]::IsMatch($remoteRoot, "^/[A-Za-z0-9._/-]+$") -or $remoteRoot.Contains("..")) {
        Throw-BackupPullError "CONFIG_INVALID" "ssh remote_root contains unsupported path characters"
    }
    $identityFile = Resolve-ConfiguredPath ([string](Get-PropertyValue $ssh "identity_file")) $configDir
    $knownHostsFile = Resolve-ConfiguredPath ([string](Get-PropertyValue $ssh "known_hosts_file")) $configDir
    $sftpValue = if ($null -ne $SftpOverride) { $SftpOverride } else { [string](Get-PropertyValue $ssh "sftp_path") }
    if ([string]::IsNullOrWhiteSpace($sftpValue)) {
        $sftpValue = "C:\Windows\System32\OpenSSH\sftp.exe"
    }
    $remoteIndex = [string](Get-PropertyValue $ssh "remote_index")
    if ([string]::IsNullOrWhiteSpace($remoteIndex)) { $remoteIndex = "index.json" }
    [void](Assert-SafeFileName $remoteIndex "remote_index")
    $port = if ($null -eq (Get-PropertyValue $ssh "port")) { 22 } else { [int](Get-PropertyValue $ssh "port") }
    $timeout = if ($null -eq (Get-PropertyValue $ssh "connect_timeout_seconds")) { 20 } else { [int](Get-PropertyValue $ssh "connect_timeout_seconds") }
    $retentionDays = if ($null -eq (Get-PropertyValue $raw "retention_days")) { 30 } else { [int](Get-PropertyValue $raw "retention_days") }
    $minimumValid = if ($null -eq (Get-PropertyValue $raw "minimum_valid_backups")) { 2 } else { [int](Get-PropertyValue $raw "minimum_valid_backups") }
    $staleHours = if ($null -eq (Get-PropertyValue $raw "stale_after_hours")) { 36 } else { [int](Get-PropertyValue $raw "stale_after_hours") }
    $minimumFree = if ($null -eq (Get-PropertyValue $raw "minimum_free_bytes")) { 104857600 } else { [int64](Get-PropertyValue $raw "minimum_free_bytes") }
    if ($port -lt 1 -or $port -gt 65535 -or $timeout -lt 1 -or $retentionDays -lt 1 -or $minimumValid -lt 1 -or $staleHours -lt 1 -or $minimumFree -lt 0) {
        Throw-BackupPullError "CONFIG_INVALID" "backup limits are invalid"
    }
    $lockValue = Get-PropertyValue $raw "lock_file"
    $statusValue = Get-PropertyValue $raw "status_file"
    $logValue = Get-PropertyValue $raw "log_file"
    $lockFile = if ($null -eq $lockValue) { Join-Path $localRoot "backup-pull.lock" } else { Resolve-ConfiguredPath ([string]$lockValue) $configDir }
    $statusFile = if ($null -eq $statusValue) { Join-Path $localRoot "backup-status.json" } else { Resolve-ConfiguredPath ([string]$statusValue) $configDir }
    $logFile = if ($null -eq $logValue) { Join-Path $localRoot "backup-pull.log" } else { Resolve-ConfiguredPath ([string]$logValue) $configDir }
    return [pscustomobject]@{
        LocalRoot = $localRoot
        IdentityFile = $identityFile
        KnownHostsFile = $knownHostsFile
        SftpPath = [IO.Path]::GetFullPath($sftpValue)
        Host = $hostName
        User = $userName
        Port = $port
        ConnectTimeoutSeconds = $timeout
        RemoteRoot = $remoteRoot
        RemoteIndex = $remoteIndex
        RetentionDays = $retentionDays
        MinimumValidBackups = $minimumValid
        StaleAfterHours = $staleHours
        MinimumFreeBytes = $minimumFree
        LockFile = $lockFile
        StatusFile = $statusFile
        LogFile = $logFile
        EncryptionAtRestMode = $encryptionMode
        EncryptionAtRestApproved = $encryptionApproved
    }
}

function Assert-SshFiles {
    param([Parameter(Mandatory = $true)][object]$Config)
    if (-not (Test-Path -LiteralPath $Config.IdentityFile -PathType Leaf)) {
        Throw-BackupPullError "CONFIG_INVALID" "SSH identity file is missing"
    }
    if (-not (Test-Path -LiteralPath $Config.KnownHostsFile -PathType Leaf)) {
        Throw-BackupPullError "CONFIG_INVALID" "pinned known_hosts file is missing"
    }
    if ((Get-Item -LiteralPath $Config.KnownHostsFile).Length -le 0) {
        Throw-BackupPullError "CONFIG_INVALID" "pinned known_hosts file is empty"
    }
    if (-not (Test-Path -LiteralPath $Config.SftpPath -PathType Leaf)) {
        Throw-BackupPullError "CONFIG_INVALID" "OpenSSH sftp executable is missing"
    }
}

function Acquire-BackupLock {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $parent = Split-Path -Parent $Path
        [void](New-Item -ItemType Directory -Force -Path $parent)
        $stream = [IO.File]::Open($Path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        $stream.SetLength(0)
        $writer = New-Object IO.StreamWriter($stream, (New-Object Text.UTF8Encoding($false)), 1024, $true)
        $writer.WriteLine("pid=$PID")
        $writer.WriteLine("started_at_utc=$(Get-UtcString)")
        $writer.Flush()
        $writer.Dispose()
        return $stream
    }
    catch [IO.IOException] {
        Throw-BackupPullError "LOCKED" "another backup pull is running"
    }
}

function Write-SanitizedLog {
    param([Parameter(Mandatory = $true)][object]$Config, [string]$Code, [string]$ArchiveName = "")
    $line = "$(Get-UtcString) code=$Code"
    if (-not [string]::IsNullOrWhiteSpace($ArchiveName)) { $line += " archive=$ArchiveName" }
    try {
        Add-Content -LiteralPath $Config.LogFile -Value $line -Encoding UTF8
    }
    catch {
        # Status and exit code remain authoritative when the optional log is unavailable.
    }
}

function Invoke-SftpGet {
    param(
        [Parameter(Mandatory = $true)][object]$Config,
        [Parameter(Mandatory = $true)][string]$RemoteName,
        [Parameter(Mandatory = $true)][string]$LocalPath,
        [Parameter(Mandatory = $true)][string]$IncomingRoot
    )
    [void](Assert-SafeFileName $RemoteName "remote_name")
    $batchPath = Join-Path $IncomingRoot ("batch-" + [guid]::NewGuid().ToString("N") + ".txt")
    $stdoutPath = Join-Path $IncomingRoot ("stdout-" + [guid]::NewGuid().ToString("N") + ".txt")
    $stderrPath = Join-Path $IncomingRoot ("stderr-" + [guid]::NewGuid().ToString("N") + ".txt")
    $localEscaped = $LocalPath.Replace('"', '\"')
    @(
        "cd $($Config.RemoteRoot)"
        "get $RemoteName `"$localEscaped`""
    ) | Set-Content -LiteralPath $batchPath -Encoding ASCII
    $arguments = @(
        "-oBatchMode=yes"
        "-oStrictHostKeyChecking=yes"
        "-oUserKnownHostsFile=$($Config.KnownHostsFile)"
        "-oConnectTimeout=$($Config.ConnectTimeoutSeconds)"
        "-i"
        $Config.IdentityFile
        "-P"
        [string]$Config.Port
        "-b"
        $batchPath
        "$($Config.User)@$($Config.Host)"
    )
    try {
        & $Config.SftpPath @arguments 1> $stdoutPath 2> $stderrPath
        $exitCode = $LASTEXITCODE
    }
    catch {
        $exitCode = 255
    }
    $diagnostic = ""
    if (Test-Path -LiteralPath $stderrPath) {
        $diagnostic = Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue
    }
    foreach ($temporaryPath in @($batchPath, $stdoutPath, $stderrPath)) {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }
    if ($exitCode -ne 0) {
        if ($diagnostic -match "Host key|REMOTE HOST IDENTIFICATION|known host|No host key") {
            Throw-BackupPullError "HOST_KEY" "pinned SSH host key was rejected"
        }
        if ($diagnostic -match "Permission denied|publickey|Authentication failed|No supported authentication") {
            Throw-BackupPullError "AUTHENTICATION" "SSH authentication failed"
        }
        if ($diagnostic -match "No such file|not found|Can't get|cannot find") {
            Throw-BackupPullError "MISSING" "remote backup object is missing"
        }
        Throw-BackupPullError "NETWORK" "SFTP transfer failed"
    }
    if (-not (Test-Path -LiteralPath $LocalPath -PathType Leaf)) {
        Throw-BackupPullError "MISSING" "SFTP did not create the expected file"
    }
}

function Write-AtomicStatus {
    param([Parameter(Mandatory = $true)][object]$Config, [Parameter(Mandatory = $true)][object]$Status)
    $parent = Split-Path -Parent $Config.StatusFile
    [void](New-Item -ItemType Directory -Force -Path $parent)
    $temporary = "$($Config.StatusFile).$([guid]::NewGuid().ToString('N')).partial"
    $json = $Status | ConvertTo-Json -Depth 12
    [IO.File]::WriteAllText($temporary, $json, (New-Object Text.UTF8Encoding($false)))
    $replacementBackup = "$($Config.StatusFile).$([guid]::NewGuid().ToString('N')).backup"
    try {
        # File.Replace is available in Windows PowerShell 5.1 and keeps a complete status file.
        if (Test-Path -LiteralPath $Config.StatusFile -PathType Leaf) {
            [IO.File]::Replace($temporary, $Config.StatusFile, $replacementBackup, $true)
        }
        else {
            [IO.File]::Move($temporary, $Config.StatusFile)
        }
    }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $replacementBackup -Force -ErrorAction SilentlyContinue
    }
}

function Get-LocalSnapshot {
    param([Parameter(Mandatory = $true)][object]$Config)
    $valid = New-Object Collections.ArrayList
    $invalid = New-Object Collections.ArrayList
    $files = @(Get-ChildItem -LiteralPath $Config.LocalRoot -Filter "*.manifest.json" -File -ErrorAction SilentlyContinue)
    foreach ($file in $files) {
        try {
            $manifest = Read-JsonObject $file.FullName
            [void](Assert-ManifestEntry $manifest)
            $archiveName = [string](Get-PropertyValue $manifest "archive_name")
            $archivePath = Join-Path $Config.LocalRoot $archiveName
            if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) {
                Throw-BackupPullError "CORRUPTED" "archive is missing"
            }
            $archiveItem = Get-Item -LiteralPath $archivePath
            if ([int64]$archiveItem.Length -ne [int64](Get-PropertyValue $manifest "archive_size_bytes") -or (Get-Sha256 $archivePath) -ne [string](Get-PropertyValue $manifest "archive_sha256")) {
                Throw-BackupPullError "CORRUPTED" "archive digest does not match manifest"
            }
            [void]$valid.Add([pscustomobject]@{
                    Manifest = $manifest
                    ManifestPath = $file.FullName
                    ArchivePath = $archivePath
                    ArchiveName = $archiveName
                    CreatedAt = ConvertTo-UtcDate (Get-PropertyValue $manifest "created_at_utc") "created_at_utc"
                })
        }
        catch {
            [void]$invalid.Add([pscustomobject]@{ Name = $file.Name; Reason = "CORRUPTED" })
        }
    }
    return [pscustomobject]@{ Valid = @($valid); Invalid = @($invalid) }
}

function Get-StatusObject {
    param([Parameter(Mandatory = $true)][object]$Config)
    $snapshot = Get-LocalSnapshot $Config
    $valid = @($snapshot.Valid | Sort-Object CreatedAt -Descending)
    $invalid = @($snapshot.Invalid)
    $state = "MISSING"
    $newest = $null
    if ($valid.Count -gt 0) {
        $newest = $valid[0]
        $ageHours = ([DateTimeOffset]::UtcNow - $newest.CreatedAt).TotalHours
        $state = if ($ageHours -gt $Config.StaleAfterHours) { "STALE" } else { "HEALTHY" }
        if ($invalid.Count -gt 0) { $state = "CORRUPTED" }
    }
    elseif ($invalid.Count -gt 0) {
        $state = "CORRUPTED"
    }
    $invalidNames = @($invalid | ForEach-Object { $_.Name })
    return [ordered]@{
        schema_version = 1
        kind = "yfc-backup-status"
        checked_at_utc = Get-UtcString
        state = $state
        valid_backup_count = $valid.Count
        invalid_backup_count = $invalid.Count
        last_successful_backup_utc = if ($null -eq $newest) { $null } else { $newest.Manifest.created_at_utc }
        newest_archive_name = if ($null -eq $newest) { $null } else { $newest.ArchiveName }
        invalid_files = $invalidNames
    }
}

function Get-StateExitCode {
    param([Parameter(Mandatory = $true)][string]$State)
    if ($ExitCodes.ContainsKey($State)) { return [int]$ExitCodes[$State] }
    return [int]$ExitCodes.UNEXPECTED
}

function Test-FreeSpace {
    param([Parameter(Mandatory = $true)][object]$Config, [Parameter(Mandatory = $true)][int64]$Bytes)
    $root = [IO.Path]::GetPathRoot($Config.LocalRoot)
    $drive = New-Object IO.DriveInfo($root)
    if (-not $drive.IsReady -or $drive.AvailableFreeSpace -lt ($Bytes + $Config.MinimumFreeBytes)) {
        Throw-BackupPullError "DISK_FULL" "local disk space is below the configured safety margin"
    }
}

function Invoke-Rotation {
    param([Parameter(Mandatory = $true)][object]$Config)
    $snapshot = Get-LocalSnapshot $Config
    $valid = @($snapshot.Valid | Sort-Object CreatedAt -Descending)
    $cutoff = [DateTimeOffset]::UtcNow.AddDays(-$Config.RetentionDays)
    $removed = 0
    foreach ($item in @($valid | Sort-Object CreatedAt)) {
        if ($item.CreatedAt -ge $cutoff -or ($valid.Count - $removed) -le $Config.MinimumValidBackups) {
            continue
        }
        try {
            Remove-Item -LiteralPath $item.ArchivePath -Force
            Remove-Item -LiteralPath $item.ManifestPath -Force
            $removed++
        }
        catch {
            Write-SanitizedLog $Config "ROTATION_FAILED" $item.ArchiveName
            Throw-BackupPullError "PROMOTE_FAILED" "backup rotation is incomplete"
        }
    }
    return $removed
}

function Invoke-Pull {
    param([Parameter(Mandatory = $true)][object]$Config)
    $lock = $null
    $incoming = Join-Path $Config.LocalRoot ".incoming"
    $downloaded = 0
    try {
        if (-not $Config.EncryptionAtRestApproved -or $Config.EncryptionAtRestMode -eq "OWNER_APPROVAL_REQUIRED") {
            Throw-BackupPullError "CONFIG_INVALID" "encryption-at-rest owner approval is not complete"
        }
        Assert-SshFiles $Config
        $lock = Acquire-BackupLock $Config.LockFile
        [void](New-Item -ItemType Directory -Force -Path $incoming)
        $indexTemp = Join-Path $incoming ("index-" + [guid]::NewGuid().ToString("N") + ".json.partial")
        Invoke-SftpGet $Config $Config.RemoteIndex $indexTemp $incoming
        $index = Read-JsonObject $indexTemp
        $entries = @(Assert-BackupIndex $index | Sort-Object { ConvertTo-UtcDate (Get-PropertyValue $_ "created_at_utc") "created_at_utc" } -Descending)
        $local = Get-LocalSnapshot $Config
        $localByName = @{}
        foreach ($item in @($local.Valid)) { $localByName[$item.ArchiveName] = $item }
        foreach ($entry in $entries) {
            $archiveName = [string](Get-PropertyValue $entry "archive_name")
            if ($localByName.ContainsKey($archiveName) -and [string](Get-PropertyValue $localByName[$archiveName].Manifest "archive_sha256") -eq [string](Get-PropertyValue $entry "archive_sha256")) {
                continue
            }
            $manifestName = [string](Get-PropertyValue $entry "manifest_name")
            $manifestTemp = Join-Path $incoming ("$manifestName.$([guid]::NewGuid().ToString('N')).partial")
            $archiveTemp = Join-Path $incoming ("$archiveName.$([guid]::NewGuid().ToString('N')).partial")
            Invoke-SftpGet $Config $manifestName $manifestTemp $incoming
            $manifest = Read-JsonObject $manifestTemp
            [void](Assert-ManifestEntry $manifest)
            foreach ($field in @("archive_name", "archive_size_bytes", "archive_sha256", "created_at_utc", "verification_status")) {
                if ([string](Get-PropertyValue $manifest $field) -ne [string](Get-PropertyValue $entry $field)) {
                    Throw-BackupPullError "CORRUPTED" "manifest and index disagree"
                }
            }
            Test-FreeSpace $Config ([int64](Get-PropertyValue $manifest "archive_size_bytes"))
            Invoke-SftpGet $Config $archiveName $archiveTemp $incoming
            $archiveItem = Get-Item -LiteralPath $archiveTemp
            if ([int64]$archiveItem.Length -ne [int64](Get-PropertyValue $manifest "archive_size_bytes") -or (Get-Sha256 $archiveTemp) -ne [string](Get-PropertyValue $manifest "archive_sha256")) {
                Throw-BackupPullError "CORRUPTED" "downloaded archive digest does not match manifest"
            }
            $archiveTarget = Join-Path $Config.LocalRoot $archiveName
            $manifestTarget = Join-Path $Config.LocalRoot $manifestName
            if ((Test-Path -LiteralPath $archiveTarget -PathType Leaf) -and -not (Test-Path -LiteralPath $manifestTarget -PathType Leaf)) {
                $existingArchive = Get-Item -LiteralPath $archiveTarget
                if ([int64]$existingArchive.Length -eq [int64](Get-PropertyValue $manifest "archive_size_bytes") -and (Get-Sha256 $archiveTarget) -eq [string](Get-PropertyValue $manifest "archive_sha256")) {
                    Remove-Item -LiteralPath $archiveTemp -Force
                    [IO.File]::Move($manifestTemp, $manifestTarget)
                    $downloaded++
                    continue
                }
            }
            if ((Test-Path -LiteralPath $archiveTarget -PathType Leaf) -or (Test-Path -LiteralPath $manifestTarget -PathType Leaf)) {
                Throw-BackupPullError "CORRUPTED" "refusing to overwrite an existing backup with a different digest"
            }
            $archivePromoted = $false
            try {
                [IO.File]::Move($archiveTemp, $archiveTarget)
                $archivePromoted = $true
                [IO.File]::Move($manifestTemp, $manifestTarget)
            }
            catch {
                if ($archivePromoted) {
                    Remove-Item -LiteralPath $archiveTarget -Force -ErrorAction SilentlyContinue
                }
                Throw-BackupPullError "PROMOTE_FAILED" "atomic local backup promotion failed"
            }
            $downloaded++
        }
        Remove-Item -LiteralPath $indexTemp -Force -ErrorAction SilentlyContinue
        $removed = Invoke-Rotation $Config
        $status = Get-StatusObject $Config
        $status.last_run_result = "SUCCESS"
        $status.last_run_at_utc = Get-UtcString
        $status.downloaded_count = $downloaded
        $status.rotated_count = $removed
        Write-AtomicStatus $Config $status
        Write-SanitizedLog $Config "SUCCESS"
        return $status
    }
    catch {
        $code = if ($null -ne $_.Exception.Data -and $_.Exception.Data.Contains("BackupCode")) { [string]$_.Exception.Data["BackupCode"] } else { "UNEXPECTED" }
        $status = Get-StatusObject $Config
        $status.last_run_result = "FAILED"
        $status.last_run_at_utc = Get-UtcString
        $status.last_failure_code = $code
        $status.downloaded_count = $downloaded
        try { Write-AtomicStatus $Config $status } catch {
        }
        Write-SanitizedLog $Config $code
        return $status
    }
    finally {
        Remove-Item -LiteralPath $incoming -Recurse -Force -ErrorAction SilentlyContinue
        if ($null -ne $lock) { $lock.Dispose() }
    }
}

function Invoke-Main {
    $config = $null
    try {
        $config = Read-Config $ConfigPath $SftpPath
        if ($Mode -eq "Status") {
            $status = Get-StatusObject $config
            [Console]::Out.WriteLine(($status | ConvertTo-Json -Depth 12))
            return (Get-StateExitCode $status.state)
        }
        $status = Invoke-Pull $config
        [Console]::Out.WriteLine(($status | ConvertTo-Json -Depth 12))
        if ($status.last_run_result -eq "FAILED") {
            return (Get-StateExitCode $status.last_failure_code)
        }
        return (Get-StateExitCode $status.state)
    }
    catch {
        $code = if ($null -ne $_.Exception.Data -and $_.Exception.Data.Contains("BackupCode")) { [string]$_.Exception.Data["BackupCode"] } else { "UNEXPECTED" }
        $status = [ordered]@{
            schema_version = 1
            kind = "yfc-backup-status"
            checked_at_utc = Get-UtcString
            state = $code
            last_run_result = "FAILED"
            last_failure_code = $code
        }
        if ($null -ne $config) {
            try { Write-AtomicStatus $config $status } catch {}
            Write-SanitizedLog $config $code
        }
        [Console]::Out.WriteLine(($status | ConvertTo-Json -Depth 12))
        return (Get-StateExitCode $code)
    }
}

$exitCode = Invoke-Main
exit $exitCode
