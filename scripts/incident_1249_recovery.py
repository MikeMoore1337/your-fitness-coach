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


def bash_parse_error_line(data: bytes) -> int | None:
    # Never expose shell stderr or the values of environment variables.
    result = subprocess.run(
        ["bash", "-n"],
        input=data,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )
    if result.returncode == 0:
        return None
    matched = re.search(rb"line (\d+):", result.stderr)
    return int(matched.group(1)) if matched else None


def safe_key_at_line(data: bytes, line_number: int | None) -> str | None:
    if line_number is None or line_number < 1:
        return None
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeError:
        return None
    if line_number > len(lines):
        return None
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", lines[line_number - 1])
    return match.group(1) if match else None


def quote_plain_assignment_for_preview(line: str, required_key: str) -> str | None:
    # Preview only. Never evaluate, print, or change the original assignment.
    suffix = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
    raw = line[: -len(suffix)] if suffix else line
    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", raw)
    if not match or match.group(1) != required_key:
        return None
    value = match.group(2)
    if not value or any(
        char in value for char in (chr(92), "$", "`", '"', "'", ";", "&", "|", "<", ">", "#")
    ):
        return None
    return f"{required_key}={shlex.quote(value)}{suffix}"


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


def stopped_runtime_candidate_summary(baseline_revision: str) -> dict[str, object]:
    # This reports only service state, OCI revision labels and configuration validity.
    # Never inspect or print environment variables, container logs or secret values.
    report: dict[str, object] = {
        "service_states": {},
        "baseline_revision_verified": False,
        "backend_worker_same_image": False,
        "compose_config_valid": False,
    }
    services: dict[str, dict[str, object]] = {}
    image_ids: dict[str, str] = {}
    for service in ("backend", "worker", "bot", "db", "edge"):
        try:
            ids = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--filter",
                    f"label=com.docker.compose.service={service}",
                    "--format",
                    "{{.ID}}",
                ],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            if ids.returncode != 0:
                services[service] = {"available": False}
                continue
            container_ids = [line.strip() for line in ids.stdout.splitlines() if line.strip()]
            if len(container_ids) != 1:
                services[service] = {
                    "available": True,
                    "container_count": len(container_ids),
                }
                continue
            inspected = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{.State.Status}}|{{.Image}}|{{index .Config.Labels "org.opencontainers.image.revision"}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}',
                    container_ids[0],
                ],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            parts = inspected.stdout.strip().split("|") if inspected.returncode == 0 else []
            if len(parts) != 4:
                services[service] = {"available": False}
                continue
            status, image_id, revision, health = parts
            image_ids[service] = image_id
            services[service] = {
                "available": True,
                "container_count": 1,
                "status": status,
                "health": health,
                "oci_revision": revision if GIT_SHA_RE.fullmatch(revision) else "UNVERIFIED",
            }
        except (OSError, subprocess.SubprocessError):
            services[service] = {"available": False}
    report["service_states"] = services
    report["backend_worker_same_image"] = bool(
        image_ids.get("backend")
        and image_ids.get("backend") == image_ids.get("worker")
    )
    report["baseline_revision_verified"] = bool(
        GIT_SHA_RE.fullmatch(baseline_revision)
        and all(
            services.get(service, {}).get("status") == "exited"
            and services.get(service, {}).get("oci_revision") == baseline_revision
            for service in ("backend", "worker", "bot")
        )
        and report["backend_worker_same_image"]
    )
    try:
        if GIT_SHA_RE.fullmatch(baseline_revision):
            release = APP_ROOT / "releases" / baseline_revision
            parsed = subprocess.run(
                ["docker", "compose", "config", "--quiet"],
                cwd=release,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
            report["compose_config_valid"] = parsed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        pass
    return report


def inspect() -> dict[str, object]:
    data, info = env_data()
    initial_error_line = bash_parse_error_line(data)
    line_30_error_line: int | None = None
    bounded_error_line: int | None = None
    bounded_preview_valid: bool | None = None
    key_98 = safe_key_at_line(data, 98)
    line_98_preview_valid: bool | None = None
    line_98_preview_error_line: int | None = None
    line_98_preview_safe = False
    key = safe_line_key(data)
    if key and not bash_valid(data):
        with suppress(RecoveryError, UnicodeError, IndexError):
            lines = data.decode("utf-8").splitlines(keepends=True)
            simple = _quote_simple_assignment(lines[29], key)
            if simple is not None:
                lines[29] = simple[0]
                line_30_error_line = bash_parse_error_line("".join(lines).encode("utf-8"))
            preview = candidate_fix(data, key, require_valid_bash=False)
            bounded_preview_valid = bash_valid(preview)
            bounded_error_line = bash_parse_error_line(preview)
    if key == "OPEN_FOOD_FACTS_USER_AGENT" and key_98 == "CLOUDFLARED_TOKEN":
        with suppress(RecoveryError, UnicodeError, IndexError):
            lines = data.decode("utf-8").splitlines(keepends=True)
            proposed_30 = quote_plain_assignment_for_preview(lines[29], key)
            proposed_98 = quote_plain_assignment_for_preview(lines[97], key_98)
            line_98_preview_safe = proposed_30 is not None and proposed_98 is not None
            if line_98_preview_safe:
                lines[29] = proposed_30
                lines[97] = proposed_98
                combined = "".join(lines).encode("utf-8")
                line_98_preview_valid = bash_valid(combined)
                line_98_preview_error_line = bash_parse_error_line(combined)
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
        "bash_parse_error_line": initial_error_line,
        "bash_parse_error_key": safe_key_at_line(data, initial_error_line),
        "line_30_key": safe_line_key(data),
        "line_30_preview_error_line": line_30_error_line,
        "line_30_preview_error_key": safe_key_at_line(data, line_30_error_line),
        "bounded_preview_bash_valid": bounded_preview_valid,
        "bounded_preview_error_line": bounded_error_line,
        "bounded_preview_error_key": safe_key_at_line(data, bounded_error_line),
        "line_98_key": key_98,
        "line_30_and_98_literal_preview_safe": line_98_preview_safe,
        "line_30_and_98_literal_preview_bash_valid": line_98_preview_valid,
        "line_30_and_98_literal_preview_error_line": line_98_preview_error_line,
        "line_30_and_98_literal_preview_error_key": safe_key_at_line(
            data, line_98_preview_error_line
        ),
        "baseline_revision": baseline if GIT_SHA_RE.fullmatch(baseline) else "INVALID",
        "current_release_relative": link_target,
        "baseline_release_exists": release_path.is_dir()
        if GIT_SHA_RE.fullmatch(baseline)
        else False,
        "baseline_deployment_marker_matches": bool(baseline and deployment_sha == baseline),
        "compose_service_states": container_summary(),
        "stopped_runtime_candidate": stopped_runtime_candidate_summary(baseline),
        "application_mutation": False,
    }


def _quote_simple_assignment(line: str, required_key: str | None = None) -> tuple[str, str] | None:
    suffix = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
    raw = line[: -len(suffix)] if suffix else line
    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", raw)
    if not match or (required_key is not None and match.group(1) != required_key):
        return None
    key, value = match.groups()
    if not value or not any(char in value for char in "()"):
        return None
    unsafe = (chr(92), chr(36), chr(96), chr(34), chr(39), ";", "&", "|", "<", ">", "#")
    if any(char in value for char in unsafe):
        if required_key is None:
            return None
        raise RecoveryError(f"complex shell syntax at assignment for {key}; manual review required")
    return f"{key}={shlex.quote(value)}{suffix}", key


def candidate_fix(data: bytes, expected_key: str, *, require_valid_bash: bool = True) -> bytes:
    if bash_valid(data):
        raise RecoveryError("environment already parses; refusing unnecessary mutation")
    try:
        source = data.decode("utf-8")
    except UnicodeError:
        raise RecoveryError("environment is not UTF-8") from None
    lines = source.splitlines(keepends=True)
    if len(lines) < 30:
        raise RecoveryError("environment has fewer than 30 lines")
    primary = _quote_simple_assignment(lines[29], expected_key)
    if primary is None:
        raise RecoveryError("line 30 key or simple parenthesis value does not match")
    lines[29] = primary[0]

    if not bash_valid("".join(lines).encode("utf-8")):
        # Only additional simple parenthesis assignments may be corrected.
        # Fail closed if more than three other lines require repair.
        changed = 0
        for idx, line in enumerate(lines):
            if idx == 29:
                continue
            result = _quote_simple_assignment(line)
            if result is not None:
                changed += 1
                if changed > 3:
                    raise RecoveryError("too many additional env fixes; manual review required")
                lines[idx] = result[0]
    proposed = "".join(lines).encode("utf-8")
    if require_valid_bash and not bash_valid(proposed):
        raise RecoveryError("bounded parenthesis correction did not produce valid Bash syntax")
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
    extra = candidate_fix(prefix + b"TEST_KEY=thing(hello)\nNEXT_KEY=other(value)\n", "TEST_KEY")
    assert bash_valid(extra)
    assert extra.splitlines()[30] == b"NEXT_KEY='other(value)'"
    try:
        candidate_fix(prefix + b"TEST_KEY=thing(hello)\n" + b"EXTRA=other(value)\n" * 4, "TEST_KEY")
    except RecoveryError:
        pass
    else:
        raise AssertionError("more than three additional corrections must be rejected")
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
