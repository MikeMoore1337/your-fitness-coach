#!/usr/bin/env python3
"""#1249: narrow, owner-gated production environment diagnostic and repair.

Runs only via the manually dispatched production GitHub Actions workflow.
Never sources environment values, prints credentials, or starts containers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

APP_ROOT = Path("/srv/yfc/fit-mini-app")
ENV_FILE = APP_ROOT / ".env"
MARKER = APP_ROOT / ".artifacts/operations/deployments/last-successful-revision"
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ENV_READ_ERRORS = (OSError, UnicodeError)
DOCKER_COMMAND_ERRORS = (OSError, subprocess.SubprocessError)
SYMLINK_ERRORS = (OSError, ValueError)


class RecoveryError(RuntimeError):
    pass


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bash_valid(data: bytes) -> bool:
    result = subprocess.run(
        ["bash", "-n"],
        input=data,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
        check=False,
    )
    return result.returncode == 0


def env_data() -> tuple[bytes, os.stat_result]:
    try:
        info = ENV_FILE.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise RecoveryError("env file is not a private regular file")
        return ENV_FILE.read_bytes(), info
    except OSError as exc:
        raise RecoveryError(f"env file unavailable: {type(exc).__name__}") from None


def safe_line_key(data: bytes) -> str | None:
    try:
        lines = data.decode("utf-8").splitlines()
        if len(lines) < 30:
            return None
        matched = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", lines[29])
        return matched.group(1) if matched else None
    except UnicodeError:
        return None


def container_summary() -> dict[str, object]:
    output: dict[str, object] = {}
    for name in ("backend", "worker", "bot"):
        try:
            p = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--filter",
                    f"label=com.docker.compose.service={name}",
                    "--format",
                    "{{.State}}",
                ],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            if p.returncode:
                output[name] = {"available": False}
                continue
            states = [state.strip() for state in p.stdout.splitlines() if state.strip()]
            output[name] = {
                "available": True,
                "total": len(states),
                "running": sum(s == "running" for s in states),
                "exited": sum(s == "exited" for s in states),
            }
        except DOCKER_COMMAND_ERRORS:
            output[name] = {"available": False}
    return output


def inspect() -> dict[str, object]:
    data, info = env_data()
    try:
        baseline = MARKER.read_text(encoding="ascii").strip()
    except ENV_READ_ERRORS:
        baseline = ""
    current = APP_ROOT / "current"
    link_target = ""
    if current.is_symlink():
        try:
            link_target = str(current.resolve(strict=True).relative_to(APP_ROOT / "releases"))
        except SYMLINK_ERRORS:
            link_target = "untrusted"
    release_path = APP_ROOT / "releases" / baseline
    deployment_sha = ""
    if GIT_SHA_RE.fullmatch(baseline):
        with suppress(OSError, UnicodeError):
            deployment_sha = (release_path / ".deployment-sha").read_text(encoding="ascii").strip()
    return {
        "incident": 1249,
        "operation": "inspect",
        "env_present": True,
        "env_owner_is_operator": info.st_uid == os.geteuid(),
        "env_private": not bool(info.st_mode & 0o077),
        "env_sha256": checksum(data),
        "env_bash_syntax_valid": bash_valid(data),
        "line_30_key": safe_line_key(data),
        "baseline_revision": baseline if GIT_SHA_RE.fullmatch(baseline) else "INVALID",
        "current_release_relative": link_target,
        "baseline_release_exists": release_path.is_dir()
        if GIT_SHA_RE.fullmatch(baseline)
        else False,
        "baseline_deployment_marker_matches": bool(baseline and deployment_sha == baseline),
        "compose_service_states": container_summary(),
        "application_mutation": False,
    }


def candidate_fix(data: bytes, expected_key: str) -> bytes:
    if bash_valid(data):
        raise RecoveryError("environment already parses; refusing unnecessary mutation")
    try:
        source = data.decode("utf-8")
    except UnicodeError:
        raise RecoveryError("environment is not UTF-8") from None
    lines = source.splitlines(keepends=True)
    if len(lines) < 30:
        raise RecoveryError("environment has fewer than 30 lines")
    original = lines[29]
    suffix = "\r\n" if original.endswith("\r\n") else ("\n" if original.endswith("\n") else "")
    raw = original[: -len(suffix)] if suffix else original
    found = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", raw)
    if not found or found.group(1) != expected_key:
        raise RecoveryError("line 30 key does not match requested key")
    value = found.group(2)
    if not value or not any(char in value for char in "()"):
        raise RecoveryError("line 30 has no supported unquoted-parenthesis problem")
    if any(char in value for char in "\\$\x60\x22\x27;&|<>"):
        raise RecoveryError("line 30 contains complex shell syntax; manual review required")
    lines[29] = f"{expected_key}={shlex.quote(value)}{suffix}"
    proposed = "".join(lines).encode("utf-8")
    if not bash_valid(proposed):
        raise RecoveryError("narrow line-30 correction did not produce valid Bash syntax")
    return proposed


def fix_env(expected_hash: str, expected_key: str) -> dict[str, object]:
    if not SHA_RE.fullmatch(expected_hash) or not KEY_RE.fullmatch(expected_key):
        raise RecoveryError("invalid expected checksum or key")
    before, info = env_data()
    if checksum(before) != expected_hash:
        raise RecoveryError("environment changed since inspection; refusing mutation")
    if info.st_uid != os.geteuid():
        raise RecoveryError("operator does not own environment file")
    after = candidate_fix(before, expected_key)
    backup = ENV_FILE.with_name(f".env.incident-1249.{int(time.time())}.bak")
    temporary = ENV_FILE.with_name(f".env.incident-1249.{os.getpid()}.tmp")
    if backup.exists() or temporary.exists():
        raise RecoveryError("recovery backup/temporary already exists")
    try:
        for dest, payload in ((backup, before), (temporary, after)):
            with os.fdopen(os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
        # A further change between inspection and atomic replacement must fail closed.
        latest, _ = env_data()
        if checksum(latest) != expected_hash:
            raise RecoveryError("environment was modified concurrently")
        os.replace(temporary, ENV_FILE)
        if not bash_valid(ENV_FILE.read_bytes()):
            raise RecoveryError("post-repair syntax verification failed")
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "incident": 1249,
        "operation": "fix_env",
        "line": 30,
        "key": expected_key,
        "backup_created": True,
        "env_sha256_after": checksum(ENV_FILE.read_bytes()),
        "env_bash_syntax_valid": True,
        "containers_started": False,
        "application_mutation": False,
    }


def self_test() -> None:
    prefix = ("SAFE=value\n" * 29).encode()
    assert not bash_valid(prefix + b"TEST_KEY=thing(hello)\n")
    candidate = candidate_fix(prefix + b"TEST_KEY=thing(hello)\n", "TEST_KEY")
    assert candidate.splitlines()[29] == b"TEST_KEY='thing(hello)'"
    assert bash_valid(candidate)
    try:
        candidate_fix(prefix + b"TEST_KEY=$(echo hello)\n", "TEST_KEY")
    except RecoveryError:
        pass
    else:
        raise AssertionError("complex shell expressions must be rejected")
    print("INCIDENT_1249_SELF_TEST=PASS")


def main() -> int:
    try:
        mode = sys.argv[1] if len(sys.argv) > 1 else ""
        if mode == "--self-test":
            self_test()
            return 0
        if mode == "inspect" and len(sys.argv) == 2:
            result = inspect()
        elif mode == "fix_env" and len(sys.argv) == 4:
            result = fix_env(sys.argv[2], sys.argv[3])
        else:
            raise RecoveryError("unsupported operation or arguments")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (RecoveryError, subprocess.TimeoutExpired) as exc:
        print(
            json.dumps({"incident": 1249, "status": "BLOCKED", "reason": str(exc)}), file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
