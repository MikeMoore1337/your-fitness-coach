<#
.SYNOPSIS
    Read-only integration with the ORIGINAL Harness2 upstream installed via Toolkit #421.
.DESCRIPTION
    Uses supported Ubuntu WSL2 and native harness2-check/harness2-report CLI.
    Does not install, fork, run benchmarks, use Codex CLI, call models or access YFC data.
#>
[CmdletBinding()]
param(
    [ValidateSet("Status", "Check", "Report")]
    [string]$Action = "Status",
    [ValidateSet("lab", "jb", "wb")]
    [string]$Benchmark = "lab"
)
$ErrorActionPreference = "Stop"
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "WSL2_UNAVAILABLE"
}

$command = @'
set -Eeuo pipefail
pin="1cfe254e8d25b15f37048c3730134686abe60335"
upstream="https://github.com/google-research/harness2.git"
dir="$HOME/.local/share/ai-development-toolkit/harness2-$pin"
src="$dir/source"
bin="$dir/.venv/bin"
[[ -d "$dir" && ! -L "$dir" && -d "$src" && ! -L "$src" ]] || { echo "HARNESS2_NOT_INSTALLED" >&2; exit 2; }
[[ -f "$dir/.adt-original-harness2" && "$(cat "$dir/.adt-original-harness2")" == "$pin" ]] || { echo "HARNESS2_MARKER_MISMATCH" >&2; exit 2; }
[[ "$(git -C "$src" rev-parse HEAD 2>/dev/null)" == "$pin" ]] || { echo "HARNESS2_SHA_MISMATCH" >&2; exit 2; }
[[ "$(git -C "$src" remote get-url origin 2>/dev/null)" == "$upstream" ]] || { echo "HARNESS2_ORIGIN_MISMATCH" >&2; exit 2; }
[[ -x "$bin/harness2-check" && -x "$bin/harness2-report" ]] || { echo "HARNESS2_INCOMPLETE" >&2; exit 2; }
cd -- "$src"
case "$1" in
  Status) printf "HARNESS2_ORIGINAL=VERIFIED\nUPSTREAM_SHA=%s\nMODEL_RUNS=NOT_REQUESTED\n" "$pin" ;;
  Check) exec "$bin/harness2-check" --bench "$2" ;;
  Report) exec "$bin/harness2-report" --bench "$2" --k 1 --mode parallel ;;
  *) echo "UNSUPPORTED_ACTION" >&2; exit 2 ;;
esac
'@
# The Bash program and action values are fixed literals, not user-injected shell.
& wsl.exe --distribution Ubuntu --exec bash -lc $command "_" $Action $Benchmark
if ($LASTEXITCODE -ne 0) {
    throw "HARNESS2_UPSTREAM_EXIT_$LASTEXITCODE"
}
