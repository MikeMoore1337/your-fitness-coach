"""Fail-closed host guard for bounded Hermes phases on a Hermes production host."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, cast


class _Fcntl(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_SH: int
    LOCK_UN: int

    def flock(self, file_descriptor: int, operation: int) -> None: ...


try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - systemd runs on Linux
    fcntl: _Fcntl | None = None
else:
    fcntl = cast(_Fcntl, _fcntl)

MIB = 1024 * 1024
MIN_MEMORY_AVAILABLE_MIB = 768
MAX_SWAP_USED_MIB = 512
MAX_LOAD1 = 1.50
MIN_DISK_FREE_MIB = 5 * 1024
DEFAULT_STATE_DIR = "/var/lib/hermes"
DEPLOYMENT_MODES = frozenset({"separate-vm", "colocated-isolated"})
SKIP_REASON_CODES = frozenset(
    {
        "insufficient_memory",
        "swap_pressure",
        "high_load",
        "insufficient_disk",
        "yfc_deploy_active",
        "hermes_overlap",
        "hermes_state_path_missing",
        "yfc_deploy_state_unavailable",
        "host_facts_unavailable",
        "guard_lock_unavailable",
    }
)
TRANSITION_SERVICES = frozenset(
    {
        "setup",
        "backend-blue",
        "backend-green",
        "worker-blue",
        "worker-green",
        "bot-blue",
        "bot-green",
    }
)


class GuardError(RuntimeError):
    """The host guard could not establish a safe decision."""


class GuardSkip(RuntimeError):
    """Hermes work must be skipped for this scheduled attempt."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class HostFacts:
    memory_available_mib: int
    swap_used_mib: int
    load1: float
    disk_free_mib: int


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason_code: str | None
    facts: HostFacts | None

    def as_dict(self, *, phase: str, mode: str) -> dict[str, object]:
        return {
            "status": "ready" if self.allowed else "skipped",
            "phase": phase,
            "mode": mode,
            "reason_code": self.reason_code,
            "facts": asdict(self.facts) if self.facts is not None else None,
            "thresholds": {
                "memory_available_min_mib": MIN_MEMORY_AVAILABLE_MIB,
                "swap_used_max_mib": MAX_SWAP_USED_MIB,
                "load1_max": MAX_LOAD1,
                "disk_free_min_mib": MIN_DISK_FREE_MIB,
            },
            "privacy": {"secrets_read": False, "secrets_logged": False},
        }


def _read_meminfo(path: Path = Path("/proc/meminfo")) -> tuple[int, int]:
    try:
        values = {
            line.split(":", 1)[0]: int(line.split()[1])
            for line in path.read_text(encoding="ascii").splitlines()
            if ":" in line and len(line.split()) >= 2
        }
        available = values["MemAvailable"] // 1024
        swap_used = max(0, values["SwapTotal"] - values["SwapFree"]) // 1024
    except (OSError, KeyError, ValueError, IndexError) as exc:
        raise GuardError("host_facts_unavailable") from exc
    return available, swap_used


def _read_load1(path: Path = Path("/proc/loadavg")) -> float:
    try:
        return float(path.read_text(encoding="ascii").split()[0])
    except (OSError, ValueError, IndexError) as exc:
        raise GuardError("host_facts_unavailable") from exc


def read_host_facts(state_dir: Path) -> HostFacts:
    state_dir = state_dir.absolute()
    if state_dir.is_symlink() or not state_dir.is_dir():
        raise GuardError("hermes_state_path_missing")
    memory_available_mib, swap_used_mib = _read_meminfo()
    try:
        disk_free_mib = shutil.disk_usage(state_dir).free // MIB
    except OSError as exc:
        raise GuardError("host_facts_unavailable") from exc
    return HostFacts(memory_available_mib, swap_used_mib, _read_load1(), disk_free_mib)


def evaluate_facts(facts: HostFacts, *, deployment_active: bool = False) -> GuardDecision:
    checks = (
        (deployment_active, "yfc_deploy_active"),
        (facts.memory_available_mib < MIN_MEMORY_AVAILABLE_MIB, "insufficient_memory"),
        (facts.swap_used_mib > MAX_SWAP_USED_MIB, "swap_pressure"),
        (facts.load1 > MAX_LOAD1, "high_load"),
        (facts.disk_free_mib < MIN_DISK_FREE_MIB, "insufficient_disk"),
    )
    reason_code = next((reason for failed, reason in checks if failed), None)
    return GuardDecision(reason_code is None, reason_code, facts)


def _docker_transition_active() -> bool | None:
    command = [
        "docker",
        "ps",
        "--filter",
        "label=com.docker.compose.project=fit-mini-app",
        "--format",
        '{{.Label "com.docker.compose.service"}}\t{{.Label "com.docker.compose.oneoff"}}',
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    rows = [line.split("\t", 1) for line in result.stdout.splitlines() if line.strip()]
    services = {row[0] for row in rows if row}
    if "setup" in services or any(len(row) > 1 and row[1].casefold() == "true" for row in rows):
        return True
    slot_services = services & TRANSITION_SERVICES
    return len(slot_services) >= 2


@contextlib.contextmanager
def _flock(
    path: Path,
    *,
    shared: bool,
    reason_code: str,
    mode: int | None = None,
) -> Iterator[None]:
    if fcntl is None:
        raise GuardError("guard_lock_unavailable")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise GuardError("guard_lock_unavailable")
    try:
        with path.open("r" if shared else "a+", encoding="ascii") as handle:
            if mode is not None:
                os.chmod(path, mode)
            operation = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
            try:
                fcntl.flock(handle.fileno(), operation | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise GuardSkip(reason_code) from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except GuardSkip:
        raise
    except (OSError, ValueError) as exc:
        raise GuardError("guard_lock_unavailable") from exc


@contextlib.contextmanager
def _deployment_boundary(
    state_dir: Path, deployment_lock: Path | None, mode: str
) -> Iterator[None]:
    if state_dir.is_symlink() or not state_dir.is_dir():
        raise GuardError("hermes_state_path_missing")
    with _flock(
        state_dir / ".phase.lock",
        shared=False,
        reason_code="hermes_overlap",
        mode=0o600,
    ):
        if mode != "colocated-isolated":
            yield
            return
        if (
            deployment_lock is None
            or deployment_lock.is_symlink()
            or not deployment_lock.is_file()
            or not deployment_lock.parent.is_dir()
        ):
            active = _docker_transition_active()
            if active is True:
                raise GuardSkip("yfc_deploy_active")
            raise GuardError("yfc_deploy_state_unavailable")
        # Do not chmod the shared YFC lock: its owner is yfc-deploy and the
        # deployment controller must retain its existing access mode.
        with _flock(deployment_lock, shared=True, reason_code="yfc_deploy_active"):
            yield


def _decision(state_dir: Path, deployment_lock: Path | None, mode: str) -> GuardDecision:
    with _deployment_boundary(state_dir, deployment_lock, mode):
        facts = read_host_facts(state_dir)
        return evaluate_facts(facts)


def _emit(decision: GuardDecision, *, phase: str, mode: str) -> None:
    print(json.dumps(decision.as_dict(phase=phase, mode=mode), sort_keys=True), flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "run"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--phase", choices=("discovery", "worker"), required=True)
        subparser.add_argument(
            "--mode", choices=sorted(DEPLOYMENT_MODES), default="separate-vm"
        )
        subparser.add_argument(
            "--state-dir",
            type=Path,
            default=Path(os.getenv("HERMES_GUARD_STATE_DIR", DEFAULT_STATE_DIR)),
        )
        subparser.add_argument(
            "--deployment-lock",
            type=Path,
            default=(
                Path(os.environ["HERMES_YFC_DEPLOYMENT_LOCK"])
                if os.environ.get("HERMES_YFC_DEPLOYMENT_LOCK")
                else None
            ),
        )
        if name == "run":
            subparser.add_argument("child_command", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        command = list(args.child_command)
        if command and command[0] == "--":
            command.pop(0)
        if not command:
            print(json.dumps({"error": "guard_command_missing"}), file=sys.stderr)
            return 2
        try:
            with _deployment_boundary(args.state_dir, args.deployment_lock, args.mode):
                decision = evaluate_facts(read_host_facts(args.state_dir))
                _emit(decision, phase=args.phase, mode=args.mode)
                if not decision.allowed:
                    return 0
                completed = subprocess.run(command, check=False, shell=False)
        except GuardSkip as exc:
            _emit(GuardDecision(False, exc.reason_code, None), phase=args.phase, mode=args.mode)
            return 0
        except GuardError as exc:
            _emit(GuardDecision(False, str(exc), None), phase=args.phase, mode=args.mode)
            return 1
        except OSError:
            _emit(
                GuardDecision(False, "guard_lock_unavailable", None),
                phase=args.phase,
                mode=args.mode,
            )
            return 1
        return completed.returncode
    try:
        decision = _decision(args.state_dir, args.deployment_lock, args.mode)
    except GuardSkip as exc:
        decision = GuardDecision(False, exc.reason_code, None)
    except GuardError as exc:
        decision = GuardDecision(False, str(exc), None)
    _emit(decision, phase=args.phase, mode=args.mode)
    if not decision.allowed:
        return 1 if args.command == "check" else 0
    if args.command == "check":
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
