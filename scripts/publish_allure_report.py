"""Validate and stream a generated Allure report to the isolated VPS origin."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, cast
from urllib.parse import urlsplit

if __package__:
    from scripts.allure_report import AllureReportError, validate_report
    from scripts.allure_report_origin import MAX_REPORT_BYTES, REMOTE_COMMAND
    from scripts.scheduled_regression import (
        DAILY_RETENTION_DAYS,
        WEEKLY_RETENTION_DAYS,
        immutable_report_path,
        report_url,
    )
else:
    from allure_report import AllureReportError, validate_report
    from allure_report_origin import MAX_REPORT_BYTES, REMOTE_COMMAND
    from scheduled_regression import (
        DAILY_RETENTION_DAYS,
        WEEKLY_RETENTION_DAYS,
        immutable_report_path,
        report_url,
    )

SSH_HOST_ENV = "ALLURE_REPORT_SSH_HOST"
SSH_PORT_ENV = "ALLURE_REPORT_SSH_PORT"
SSH_USER_ENV = "ALLURE_REPORT_SSH_USER"
SSH_PRIVATE_KEY_ENV = "ALLURE_REPORT_SSH_PRIVATE_KEY"
SSH_KNOWN_HOSTS_ENV = "ALLURE_REPORT_SSH_KNOWN_HOSTS"
_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,31}$")
_MAX_DURATION_SECONDS = 7 * 24 * 60 * 60
_SSH_KEYGEN_TIMEOUT_SECONDS = 10
_SSH_PROCESS_TIMEOUT_SECONDS = 10
_SSH_KILL_TIMEOUT_SECONDS = 2
_FINGERPRINT_RE = re.compile(r"SHA256:[A-Za-z0-9+/=]+")
PREFLIGHT_COMMAND = "yfc-allure-preflight-v1"
_SSH_FAILURE_CLASSES = frozenset(
    {
        "private_key_invalid",
        "known_hosts_invalid",
        "host_key_entry_missing",
        "host_key_mismatch",
        "publickey_auth_failed",
        "connection_refused",
        "connection_timeout",
        "connection_unreachable",
        "remote_command_failed",
        "publication_stream_failed",
        "unknown_ssh_failure",
    }
)


class PublicationError(RuntimeError):
    """The private report publication contract cannot be completed safely."""


class SSHFailure(PublicationError):
    """A bounded, secret-free SSH failure classification."""

    def __init__(self, failure_class: str) -> None:
        self.failure_class = (
            failure_class if failure_class in _SSH_FAILURE_CLASSES else "unknown_ssh_failure"
        )
        super().__init__(f"SSH publication failed: {self.failure_class}")


@dataclass(frozen=True)
class _PreparedSSHCredentials:
    host: str
    port: int
    user: str
    private_key_path: Path
    known_hosts_path: Path
    private_key_fingerprint: str
    host_key_fingerprint: str


def _load_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublicationError(f"invalid JSON file: {path}") from error
    if not isinstance(payload, dict):
        raise PublicationError(f"JSON object expected: {path}")
    return payload


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise PublicationError("report timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PublicationError("report timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise PublicationError("report timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _duration(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PublicationError("report duration is invalid")
    result = float(value)
    if not math.isfinite(result) or result < 0 or result > _MAX_DURATION_SECONDS:
        raise PublicationError("report duration is invalid")
    return result


def _safe_text(value: object, *, field: str, required: bool = False) -> str:
    if not isinstance(value, str) or (required and not value):
        raise PublicationError(f"report metadata field {field} is invalid")
    if "\x00" in value or "\n" in value or "\r" in value or len(value) > 4096:
        raise PublicationError(f"report metadata field {field} is invalid")
    return value


def _counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise PublicationError("report counts are missing")
    allowed = {"passed", "failed", "broken", "skipped", "unknown", "total"}
    result: dict[str, int] = {}
    for key, item in value.items():
        if key not in allowed:
            continue
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise PublicationError("report counts are invalid")
        result[key] = item
    return result


def _entry_from_metadata(metadata: Mapping[str, object], *, report_bytes: int) -> dict[str, object]:
    kind = metadata.get("run_kind")
    period = metadata.get("period")
    run_id = metadata.get("run_id")
    if not all(isinstance(value, str) for value in (kind, period, run_id)):
        raise PublicationError("report metadata has no path identity")
    try:
        path = immutable_report_path(str(kind), period=str(period), run_id=str(run_id))
        expected_url = report_url(path)
    except ValueError as error:
        raise PublicationError("report metadata has an invalid immutable path") from error
    if metadata.get("immutable_path") != path:
        raise PublicationError("report metadata path is inconsistent")
    if metadata.get("status") not in {"complete", "incomplete"}:
        raise PublicationError("report metadata status is unsupported")
    if not isinstance(report_bytes, int) or report_bytes <= 0 or report_bytes > MAX_REPORT_BYTES:
        raise PublicationError("generated report size is invalid")
    created_at = _parse_timestamp(metadata.get("created_at"))
    commit_sha = _safe_text(metadata.get("commit_sha"), field="commit_sha", required=True)
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise PublicationError("report commit SHA is invalid")
    workflow_url = _safe_text(metadata.get("workflow_url"), field="workflow_url", required=True)
    parsed_workflow_url = urlsplit(workflow_url)
    if parsed_workflow_url.scheme != "https" or not parsed_workflow_url.hostname:
        raise PublicationError("report workflow URL must use HTTPS")
    counts = _counts(metadata.get("counts"))
    duration_seconds = _duration(metadata.get("duration_seconds", 0.0))
    report_status = str(metadata["status"])
    status = (
        "incomplete"
        if report_status == "incomplete"
        else "passed"
        if counts.get("failed", 0) == 0 and counts.get("broken", 0) == 0
        else "failed"
    )
    retention_days = DAILY_RETENTION_DAYS if kind == "daily" else WEEKLY_RETENTION_DAYS
    return {
        "kind": str(kind),
        "period": str(period),
        "run_id": str(run_id),
        "path": path,
        "url": expected_url,
        "created_at": created_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expires_at": (created_at.date() + timedelta(days=retention_days)).isoformat(),
        "commit_sha": commit_sha,
        "workflow_url": workflow_url,
        "duration_seconds": duration_seconds,
        "counts": counts,
        "bytes": report_bytes,
        "status": status,
    }


def _read_required_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise PublicationError(f"{name} is not configured")
    return value


def _read_ssh_env(name: str, failure_class: str) -> str:
    try:
        return _read_required_env(name)
    except PublicationError:
        raise SSHFailure(failure_class) from None


def _ssh_config() -> tuple[str, int, str, str, str]:
    try:
        host = _read_required_env(SSH_HOST_ENV).strip()
        user = _read_required_env(SSH_USER_ENV).strip()
        port_text = _read_required_env(SSH_PORT_ENV).strip()
    except PublicationError:
        raise SSHFailure("unknown_ssh_failure") from None
    private_key = _read_ssh_env(SSH_PRIVATE_KEY_ENV, "private_key_invalid")
    known_hosts = _read_ssh_env(SSH_KNOWN_HOSTS_ENV, "known_hosts_invalid")
    if not _HOST_RE.fullmatch(host):
        raise SSHFailure("unknown_ssh_failure")
    if not _USER_RE.fullmatch(user):
        raise SSHFailure("unknown_ssh_failure")
    if not port_text.isdigit() or not 1 <= int(port_text) <= 65_535:
        raise SSHFailure("unknown_ssh_failure")
    if len(private_key) > 128 * 1024 or not private_key.strip():
        raise SSHFailure("private_key_invalid")
    if len(known_hosts) > 128 * 1024 or not known_hosts.strip():
        raise SSHFailure("known_hosts_invalid")
    return host, int(port_text), user, private_key, known_hosts


def _ssh_arguments(
    *,
    host: str,
    port: int,
    user: str,
    private_key_path: Path,
    known_hosts_path: Path,
    remote_command: str = REMOTE_COMMAND,
) -> list[str]:
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "IdentityAgent=none",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "GlobalKnownHostsFile=none",
        "-o",
        f"UserKnownHostsFile={known_hosts_path}",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "ConnectTimeout=15",
        "-p",
        str(port),
        "-i",
        str(private_key_path),
        f"{user}@{host}",
        remote_command,
    ]


def _write_secret_file(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(content.encode("utf-8"))
    finally:
        if descriptor != -1:
            with suppress(OSError):
                os.close(descriptor)
    os.chmod(path, 0o600)


def _normalize_ssh_material(content: str, *, failure_class: str) -> str:
    try:
        encoded = content.encode("utf-8")
    except UnicodeEncodeError:
        raise SSHFailure(failure_class) from None
    if "\x00" in content or b"\x00" in encoded:
        raise SSHFailure(failure_class)
    if any(marker in content for marker in ("\ufeff", "\ufffe")) or any(
        encoded.startswith(marker)
        for marker in (
            b"\xef\xbb\xbf",
            b"\xff\xfe",
            b"\xfe\xff",
            b"\xff\xfe\x00\x00",
            b"\x00\x00\xfe\xff",
        )
    ):
        raise SSHFailure(failure_class)
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return normalized if normalized.endswith("\n") else normalized + "\n"


def _run_ssh_keygen(
    arguments: Sequence[str], *, input_text: str | None = None
) -> subprocess.CompletedProcess[str] | None:
    try:
        if input_text is None:
            return subprocess.run(
                ["ssh-keygen", *arguments],
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                shell=False,
                stdin=subprocess.DEVNULL,
                timeout=_SSH_KEYGEN_TIMEOUT_SECONDS,
            )
        return subprocess.run(
            ["ssh-keygen", *arguments],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            input=input_text,
            shell=False,
            timeout=_SSH_KEYGEN_TIMEOUT_SECONDS,
        )
    except OSError, subprocess.TimeoutExpired:
        return None


def _fingerprint_from_output(output: str) -> str | None:
    match = _FINGERPRINT_RE.search(output)
    return match.group(0) if match else None


def _prepare_private_key(private_key: str, path: Path) -> str:
    normalized = _normalize_ssh_material(private_key, failure_class="private_key_invalid")
    try:
        _write_secret_file(path, normalized)
    except OSError, UnicodeEncodeError:
        raise SSHFailure("private_key_invalid") from None
    public_key = _run_ssh_keygen(["-y", "-f", str(path)])
    if public_key is None or public_key.returncode != 0 or not public_key.stdout.strip():
        raise SSHFailure("private_key_invalid")
    fingerprint = _run_ssh_keygen(["-lf", "-"], input_text=public_key.stdout)
    if fingerprint is None or fingerprint.returncode != 0:
        raise SSHFailure("private_key_invalid")
    value = _fingerprint_from_output(fingerprint.stdout)
    if value is None:
        raise SSHFailure("private_key_invalid")
    return value


def _known_hosts_target_tokens(host: str, port: int) -> set[str]:
    target = f"[{host}]:{port}"
    return {target, host} if port == 22 else {target}


def _prepare_known_hosts(known_hosts: str, *, host: str, port: int, path: Path) -> str:
    normalized = _normalize_ssh_material(known_hosts, failure_class="known_hosts_invalid")
    try:
        _write_secret_file(path, normalized)
    except OSError, UnicodeEncodeError:
        raise SSHFailure("known_hosts_invalid") from None

    selected: list[str] = []
    target_tokens = _known_hosts_target_tokens(host, port)
    for line in normalized.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) < 3 or fields[0].startswith("@"):
            raise SSHFailure("known_hosts_invalid")
        host_patterns = fields[0].split(",")
        if any(
            not pattern
            or pattern.startswith("|")
            or any(marker in pattern for marker in ("*", "?", "!"))
            for pattern in host_patterns
        ):
            raise SSHFailure("known_hosts_invalid")
        if target_tokens.intersection(host_patterns):
            selected.append(" ".join(fields[:3]) + "\n")

    full_file = _run_ssh_keygen(["-lf", str(path)])
    if full_file is None:
        raise SSHFailure("unknown_ssh_failure")
    if full_file.returncode != 0:
        raise SSHFailure("known_hosts_invalid")
    if not selected:
        raise SSHFailure("host_key_entry_missing")
    if len(selected) != 1:
        raise SSHFailure("known_hosts_invalid")

    selected_path = path.with_name("known_hosts.selected")
    try:
        _write_secret_file(selected_path, selected[0])
    except OSError, UnicodeEncodeError:
        raise SSHFailure("known_hosts_invalid") from None
    fingerprint = _run_ssh_keygen(["-lf", str(selected_path)])
    if fingerprint is None:
        raise SSHFailure("unknown_ssh_failure")
    if fingerprint.returncode != 0:
        raise SSHFailure("known_hosts_invalid")
    value = _fingerprint_from_output(fingerprint.stdout)
    if value is None:
        raise SSHFailure("known_hosts_invalid")
    return value


def _prepare_ssh_credentials(
    *,
    host: str,
    port: int,
    user: str,
    private_key: str,
    known_hosts: str,
    temporary_root: Path,
) -> _PreparedSSHCredentials:
    private_key_path = temporary_root / "id_ed25519"
    known_hosts_path = temporary_root / "known_hosts"
    private_key_fingerprint = _prepare_private_key(private_key, private_key_path)
    host_key_fingerprint = _prepare_known_hosts(
        known_hosts, host=host, port=port, path=known_hosts_path
    )
    return _PreparedSSHCredentials(
        host=host,
        port=port,
        user=user,
        private_key_path=private_key_path,
        known_hosts_path=known_hosts_path,
        private_key_fingerprint=private_key_fingerprint,
        host_key_fingerprint=host_key_fingerprint,
    )


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    if info.issym() or info.islnk() or not (info.isfile() or info.isdir()):
        raise PublicationError("generated report contains a non-regular archive member")
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o755 if info.isdir() else 0o644
    return info


def _write_archive(report_root: Path, output: BinaryIO) -> None:
    if report_root.is_symlink():
        raise PublicationError("generated report root cannot be a symlink")
    report_root = report_root.resolve()
    with tarfile.open(fileobj=output, mode="w|gz") as archive:
        for child in sorted(report_root.iterdir(), key=lambda path: path.name):
            archive.add(child, arcname=child.name, recursive=True, filter=_tar_filter)


def _decode_process_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _communicate_bounded(process: subprocess.Popen[bytes]) -> tuple[bytes, bytes, bool]:
    try:
        stdout, stderr = process.communicate(timeout=_SSH_PROCESS_TIMEOUT_SECONDS)
        return stdout or b"", stderr or b"", False
    except OSError:
        with suppress(OSError, subprocess.TimeoutExpired):
            process.wait(timeout=_SSH_KILL_TIMEOUT_SECONDS)
        if process.returncode is None:
            with suppress(OSError):
                process.kill()
        return b"", b"", False
    except subprocess.TimeoutExpired:
        with suppress(OSError):
            process.kill()
        try:
            stdout, stderr = process.communicate(timeout=_SSH_KILL_TIMEOUT_SECONDS)
            return stdout or b"", stderr or b"", True
        except subprocess.TimeoutExpired:
            with suppress(OSError):
                process.kill()
            with suppress(OSError, subprocess.TimeoutExpired):
                process.wait(timeout=_SSH_KILL_TIMEOUT_SECONDS)
            return b"", b"", True


def _close_process_stdin(process: subprocess.Popen[bytes]) -> OSError | None:
    if process.stdin is None:
        return None
    try:
        process.stdin.close()
    except OSError as error:
        return error
    return None


def _is_remote_error_response(stdout: bytes | str | None) -> bool:
    try:
        payload = json.loads(_decode_process_output(stdout))
    except TypeError, json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and payload.get("status") == "error"


def _is_preflight_rejection(stdout: bytes | str | None) -> bool:
    try:
        payload = json.loads(_decode_process_output(stdout))
    except TypeError, json.JSONDecodeError:
        return False
    return payload == {"status": "error", "error": "publication rejected"}


def _classify_ssh_failure(
    *,
    stderr: bytes | str | None,
    stdout: bytes | str | None = None,
    returncode: int | None = None,
    stream_error: bool = False,
    timed_out: bool = False,
) -> str:
    diagnostic = _decode_process_output(stderr).casefold()
    if "load key" in diagnostic or "error in libcrypto" in diagnostic:
        return "private_key_invalid"
    if "invalid format" in diagnostic and "key" in diagnostic:
        return "private_key_invalid"
    if (
        "host key verification failed" in diagnostic
        or "remote host identification has changed" in diagnostic
    ):
        return "host_key_mismatch"
    if "no host key is known" in diagnostic or "no hostkey alg" in diagnostic:
        return "host_key_entry_missing"
    if ("known_hosts" in diagnostic or "known hosts" in diagnostic) and (
        "not a public key file" in diagnostic or "invalid" in diagnostic
    ):
        return "known_hosts_invalid"
    if (
        "permission denied (publickey" in diagnostic
        or "no more authentication methods" in diagnostic
    ):
        return "publickey_auth_failed"
    if "connection refused" in diagnostic:
        return "connection_refused"
    if timed_out or "connection timed out" in diagnostic or "operation timed out" in diagnostic:
        return "connection_timeout"
    if (
        "no route to host" in diagnostic
        or "network is unreachable" in diagnostic
        or "could not resolve hostname" in diagnostic
        or "name or service not known" in diagnostic
    ):
        return "connection_unreachable"
    if _is_remote_error_response(stdout):
        return "remote_command_failed"
    if stream_error:
        return "publication_stream_failed"
    if returncode not in (None, 0) and not diagnostic:
        return "unknown_ssh_failure"
    return "unknown_ssh_failure"


def _publish_over_ssh(
    *,
    report_root: Path,
    header: Mapping[str, object],
    host: str,
    port: int,
    user: str,
    private_key: str,
    known_hosts: str,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="yfc-allure-ssh-") as temporary:
        temporary_root = Path(temporary)
        prepared = _prepare_ssh_credentials(
            host=host,
            port=port,
            user=user,
            private_key=private_key,
            known_hosts=known_hosts,
            temporary_root=temporary_root,
        )
        try:
            process = subprocess.Popen(
                _ssh_arguments(
                    host=prepared.host,
                    port=prepared.port,
                    user=prepared.user,
                    private_key_path=prepared.private_key_path,
                    known_hosts_path=prepared.known_hosts_path,
                ),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
        except OSError:
            raise SSHFailure("unknown_ssh_failure") from None
        try:
            if process.stdin is None:
                raise PublicationError("SSH publisher stdin is unavailable")
            process.stdin.write(b"YFC-ALLURE-PUBLISH-v1\n")
            process.stdin.write(
                (json.dumps(dict(header), ensure_ascii=False, sort_keys=True) + "\n").encode(
                    "utf-8"
                )
            )
            process.stdin.flush()
            _write_archive(report_root, cast(BinaryIO, process.stdin))
            close_error = _close_process_stdin(process)
            if close_error is not None:
                raise close_error
        except BrokenPipeError, OSError:
            _close_process_stdin(process)
            stdout, stderr, timed_out = _communicate_bounded(process)
            failure_class = _classify_ssh_failure(
                stderr=stderr,
                stdout=stdout,
                returncode=process.returncode,
                stream_error=True,
                timed_out=timed_out,
            )
            raise SSHFailure(failure_class) from None
        except PublicationError:
            _close_process_stdin(process)
            _communicate_bounded(process)
            raise
        stdout, stderr, timed_out = _communicate_bounded(process)
        if process.returncode != 0:
            failure_class = _classify_ssh_failure(
                stderr=stderr,
                stdout=stdout,
                returncode=process.returncode,
                timed_out=timed_out,
            )
            raise SSHFailure(failure_class) from None
        try:
            response = json.loads(_decode_process_output(stdout))
        except TypeError, json.JSONDecodeError:
            raise SSHFailure("unknown_ssh_failure") from None
        if not isinstance(response, dict) or response.get("status") not in {
            "published",
            "cleanup-failed",
        }:
            raise SSHFailure("remote_command_failed")
        return response


def _preflight_defaults() -> dict[str, str]:
    return {
        "ALLURE_SSH_PRIVATE_KEY_PARSE_OK": "no",
        "ALLURE_SSH_PRIVATE_KEY_FINGERPRINT": "unavailable",
        "ALLURE_SSH_KNOWN_HOSTS_MATCH": "no",
        "ALLURE_SSH_HOST_KEY_FINGERPRINT": "unavailable",
        "ALLURE_SSH_AUTH_ACCEPTED": "no",
        "ALLURE_SSH_FORCED_COMMAND_REACHED": "no",
        "ALLURE_SSH_PREFLIGHT": "fail",
        "ALLURE_SSH_FAILURE_CLASS": "unknown_ssh_failure",
    }


def _run_preflight_probe(prepared: _PreparedSSHCredentials) -> None:
    try:
        process = subprocess.Popen(
            _ssh_arguments(
                host=prepared.host,
                port=prepared.port,
                user=prepared.user,
                private_key_path=prepared.private_key_path,
                known_hosts_path=prepared.known_hosts_path,
                remote_command=PREFLIGHT_COMMAND,
            ),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except OSError:
        raise SSHFailure("unknown_ssh_failure") from None
    if process.stdin is None:
        _communicate_bounded(process)
        raise SSHFailure("unknown_ssh_failure")
    close_error = _close_process_stdin(process)
    stdout, stderr, timed_out = _communicate_bounded(process)
    if (
        process.returncode == 1
        and _is_preflight_rejection(stdout)
        and not _decode_process_output(stderr).strip()
    ):
        return
    failure_class = _classify_ssh_failure(
        stderr=stderr,
        stdout=stdout,
        returncode=process.returncode,
        stream_error=close_error is not None,
        timed_out=timed_out,
    )
    raise SSHFailure(failure_class) from None


def ssh_preflight() -> dict[str, str]:
    result = _preflight_defaults()
    try:
        host, port, user, private_key, known_hosts = _ssh_config()
        with tempfile.TemporaryDirectory(prefix="yfc-allure-ssh-preflight-") as temporary:
            temporary_root = Path(temporary)
            private_key_path = temporary_root / "id_ed25519"
            known_hosts_path = temporary_root / "known_hosts"
            private_key_fingerprint = _prepare_private_key(private_key, private_key_path)
            result["ALLURE_SSH_PRIVATE_KEY_PARSE_OK"] = "yes"
            result["ALLURE_SSH_PRIVATE_KEY_FINGERPRINT"] = private_key_fingerprint
            host_key_fingerprint = _prepare_known_hosts(
                known_hosts, host=host, port=port, path=known_hosts_path
            )
            result["ALLURE_SSH_KNOWN_HOSTS_MATCH"] = "yes"
            result["ALLURE_SSH_HOST_KEY_FINGERPRINT"] = host_key_fingerprint
            prepared = _PreparedSSHCredentials(
                host=host,
                port=port,
                user=user,
                private_key_path=private_key_path,
                known_hosts_path=known_hosts_path,
                private_key_fingerprint=private_key_fingerprint,
                host_key_fingerprint=host_key_fingerprint,
            )
            _run_preflight_probe(prepared)
            result["ALLURE_SSH_AUTH_ACCEPTED"] = "yes"
            result["ALLURE_SSH_FORCED_COMMAND_REACHED"] = "yes"
            result["ALLURE_SSH_PREFLIGHT"] = "pass"
            result["ALLURE_SSH_FAILURE_CLASS"] = "none"
    except SSHFailure as error:
        result["ALLURE_SSH_FAILURE_CLASS"] = error.failure_class
    except OSError, PublicationError:
        result["ALLURE_SSH_FAILURE_CLASS"] = "unknown_ssh_failure"
    return result


def _write_publication(path: Path, publication: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(publication), ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def publish(
    *,
    report_root: Path,
    metadata_path: Path,
    publication_path: Path,
    now: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    metadata = _load_object(metadata_path)
    try:
        validation = validate_report(
            report_root,
            metadata_path=metadata_path,
            require_complete=False,
        )
    except AllureReportError as error:
        raise PublicationError("generated report failed validation") from error
    report_bytes = int(validation["bytes"])
    current = _entry_from_metadata(metadata, report_bytes=report_bytes)
    if dry_run:
        publication = {
            "status": "dry-run",
            "url": current["url"],
            "report_path": current["path"],
            "report_bytes": report_bytes,
            "remote_state": "not-inspected",
        }
        _write_publication(publication_path, publication)
        return publication
    host, port, user, private_key, known_hosts = _ssh_config()
    started = time.monotonic()
    header = {
        "run_kind": current["kind"],
        "period": current["period"],
        "run_id": current["run_id"],
        "immutable_path": current["path"],
        "url": current["url"],
        "report_status": metadata["status"],
        "report_bytes": report_bytes,
        "created_at": current["created_at"],
        "commit_sha": current["commit_sha"],
        "workflow_url": current["workflow_url"],
        "duration_seconds": current["duration_seconds"],
        "counts": current["counts"],
    }
    response = _publish_over_ssh(
        report_root=report_root,
        header=header,
        host=host,
        port=port,
        user=user,
        private_key=private_key,
        known_hosts=known_hosts,
    )
    if response.get("url") != current["url"] or response.get("report_path") != current["path"]:
        raise PublicationError("remote report publisher returned a noncanonical report path")
    publication = {
        **response,
        "published_seconds": round(time.monotonic() - started, 3),
    }
    _write_publication(publication_path, publication)
    return publication


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("--report-root", type=Path, required=True)
    publish_parser.add_argument("--metadata", type=Path, required=True)
    publish_parser.add_argument("--publication", type=Path, required=True)
    publish_parser.add_argument("--dry-run", action="store_true")
    subparsers.add_parser("ssh-preflight")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "ssh-preflight":
        result = ssh_preflight()
        for key in (
            "ALLURE_SSH_PRIVATE_KEY_PARSE_OK",
            "ALLURE_SSH_PRIVATE_KEY_FINGERPRINT",
            "ALLURE_SSH_KNOWN_HOSTS_MATCH",
            "ALLURE_SSH_HOST_KEY_FINGERPRINT",
            "ALLURE_SSH_AUTH_ACCEPTED",
            "ALLURE_SSH_FORCED_COMMAND_REACHED",
            "ALLURE_SSH_PREFLIGHT",
            "ALLURE_SSH_FAILURE_CLASS",
        ):
            print(f"{key}={result[key]}")
        return 0 if result["ALLURE_SSH_PREFLIGHT"] == "pass" else 1
    try:
        payload = publish(
            report_root=args.report_root,
            metadata_path=args.metadata,
            publication_path=args.publication,
            dry_run=args.dry_run,
        )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except (PublicationError, OSError, ValueError) as error:
        print(f"allure publication error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
