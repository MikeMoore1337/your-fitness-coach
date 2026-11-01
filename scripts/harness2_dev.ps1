<#
.SYNOPSIS
    Optional YFC DEV entrypoint for the original pinned Harness2 via Toolkit #421.
.DESCRIPTION
    Delegates safe read-only operations to the existing Toolkit Windows/WSL2
    acceptance script. No inline Bash, benchmark installation, model execution,
    Codex/Claude CLI, Docker, YFC runtime or production dependencies.
#>
[CmdletBinding()]
param(
    [ValidateSet('Preflight', 'Status', 'SetupPreview', 'Check', 'RunPreview', 'Report', 'Artifacts')]
    [string]$Action = 'Status',
    [ValidateSet('lab', 'jb', 'wb')]
    [string]$Benchmark = 'lab',
    [ValidatePattern('^(auto|Ubuntu(?:-[0-9]{2}\.[0-9]{2})?)$')]
    [string]$Distribution = 'auto',
    [string]$ToolkitRoot = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Toolkit #479 fixed multiline Bash marshalling on PowerShell 5.1.
# This commit is the minimum supported Toolkit revision for the YFC bridge.
$minimumToolkitCommit = '397b5e9241e1266e82c81f5924c8a72b0c47eacf'
$upstreamPin = '1cfe254e8d25b15f37048c3730134686abe60335'

if ([string]::IsNullOrWhiteSpace($ToolkitRoot)) {
    $yfcRoot = Split-Path -Parent $PSScriptRoot
    $ToolkitRoot = Join-Path (Split-Path -Parent $yfcRoot) 'ai-development-toolkit'
}
if (-not (Test-Path -LiteralPath $ToolkitRoot -PathType Container)) {
    throw "HARNESS2_TOOLKIT_CHECKOUT_MISSING: $ToolkitRoot; specify -ToolkitRoot"
}
$toolkitRootPath = (Resolve-Path -LiteralPath $ToolkitRoot).ProviderPath
$relativeFiles = @(
    'integrations/harness2/acceptance.ps1',
    'integrations/harness2/preflight.sh',
    'integrations/harness2/cli.sh',
    'integrations/harness2/install.sh'
)
$checkedPaths = @($toolkitRootPath)
foreach ($relative in @('integrations', 'integrations/harness2') + $relativeFiles) {
    $checkedPaths += Join-Path $toolkitRootPath $relative
}
foreach ($path in $checkedPaths) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "HARNESS2_TOOLKIT_INCOMPLETE: $path"
    }
    $entry = Get-Item -LiteralPath $path -Force
    if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "HARNESS2_TOOLKIT_UNTRUSTED_PATH: $path"
    }
}

# Never execute a script supplied by an unrelated checkout or a modified local file.
if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
    throw 'HARNESS2_GIT_UNAVAILABLE'
}
$originOutput = @(& git.exe -C $toolkitRootPath remote get-url origin 2>$null)
$allowedOrigins = @(
    'https://github.com/MikeMoore1337/ai-development-toolkit.git',
    'https://github.com/MikeMoore1337/ai-development-toolkit',
    'git@github.com:MikeMoore1337/ai-development-toolkit.git'
)
if ($LASTEXITCODE -ne 0 -or $originOutput.Count -ne 1 -or
    $originOutput[0].Trim() -notin $allowedOrigins) {
    throw 'HARNESS2_TOOLKIT_ORIGIN_MISMATCH'
}
$gitRootOutput = @(& git.exe -C $toolkitRootPath rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or $gitRootOutput.Count -ne 1 -or
    -not (Test-Path -LiteralPath $gitRootOutput[0] -PathType Container) -or
    (Resolve-Path -LiteralPath $gitRootOutput[0]).ProviderPath -ine $toolkitRootPath) {
    throw 'HARNESS2_TOOLKIT_NOT_REPO_ROOT'
}
& git.exe -C $toolkitRootPath merge-base --is-ancestor $minimumToolkitCommit HEAD 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'HARNESS2_TOOLKIT_REVISION_TOO_OLD_OR_SHALLOW'
}
& git.exe -C $toolkitRootPath ls-files --error-unmatch -- @relativeFiles 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'HARNESS2_TOOLKIT_UNTRACKED_INTEGRATION'
}
& git.exe -C $toolkitRootPath diff --quiet HEAD -- @relativeFiles 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'HARNESS2_TOOLKIT_MODIFIED'
}
# A clean working tree alone is insufficient: a locally committed replacement
# of acceptance.ps1 could otherwise inherit the legitimate Toolkit origin.
# Compare the four executable scripts to the reviewed Toolkit #479 Git tree.
& git.exe -C $toolkitRootPath diff --quiet $minimumToolkitCommit HEAD -- @relativeFiles 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'HARNESS2_TOOLKIT_SOURCE_REVISION_MISMATCH'
}
$cliPath = Join-Path $toolkitRootPath 'integrations/harness2/cli.sh'
$expectedPinLine = 'readonly UPSTREAM_SHA="' + $upstreamPin + '"'
if (-not [IO.File]::ReadAllText($cliPath).Contains($expectedPinLine)) {
    throw 'HARNESS2_UPSTREAM_PIN_CHANGED'
}

# The Toolkit owns WSL distro discovery, Python 3.12 preflight, source integrity,
# native CLI checks, safe result enumeration and controlled upstream dry runs.
$acceptancePath = Join-Path $toolkitRootPath 'integrations/harness2/acceptance.ps1'
& $acceptancePath -Action $Action -Benchmark $Benchmark -Distribution $Distribution
