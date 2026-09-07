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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
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


class PublicationError(RuntimeError):
    """The private report publication contract cannot be completed safely."""


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
    if not value or "\x00" in value:
        raise PublicationError(f"{name} is not configured")
    return value


def _ssh_config() -> tuple[str, int, str, str, str]:
    host = _read_required_env(SSH_HOST_ENV).strip()
    user = _read_required_env(SSH_USER_ENV).strip()
    port_text = _read_required_env(SSH_PORT_ENV).strip()
    private_key = _read_required_env(SSH_PRIVATE_KEY_ENV)
    known_hosts = _read_required_env(SSH_KNOWN_HOSTS_ENV)
    if not _HOST_RE.fullmatch(host):
        raise PublicationError(f"{SSH_HOST_ENV} is invalid")
    if not _USER_RE.fullmatch(user):
        raise PublicationError(f"{SSH_USER_ENV} is invalid")
    if not port_text.isdigit() or not 1 <= int(port_text) <= 65_535:
        raise PublicationError(f"{SSH_PORT_ENV} is invalid")
    if len(private_key) > 128 * 1024 or len(known_hosts) > 128 * 1024:
        raise PublicationError("SSH credential is too large")
    if not private_key.strip() or not known_hosts.strip():
        raise PublicationError("SSH credential is empty")
    matched_host = False
    for line in known_hosts.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) < 3 or fields[0].startswith("@"):
            raise PublicationError("SSH known-hosts file must contain pinned host keys")
        host_patterns = fields[0].split(",")
        if any("*" in pattern or "?" in pattern or "!" in pattern for pattern in host_patterns):
            raise PublicationError("SSH known-hosts file cannot contain wildcard hosts")
        if host in host_patterns or f"[{host}]:{port_text}" in host_patterns:
            matched_host = True
        if any(pattern.startswith("|") for pattern in host_patterns):
            matched_host = True
    if not matched_host:
        raise PublicationError("SSH known-hosts file does not pin the configured host")
    return host, int(port_text), user, private_key, known_hosts


def _ssh_arguments(
    *,
    host: str,
    port: int,
    user: str,
    private_key_path: Path,
    known_hosts_path: Path,
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
        REMOTE_COMMAND,
    ]


def _write_secret_file(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
        stream.write(content)
    os.chmod(path, 0o600)


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
        private_key_path = temporary_root / "id_ed25519"
        known_hosts_path = temporary_root / "known_hosts"
        _write_secret_file(private_key_path, private_key)
        _write_secret_file(known_hosts_path, known_hosts)
        process = subprocess.Popen(
            _ssh_arguments(
                host=host,
                port=port,
                user=user,
                private_key_path=private_key_path,
                known_hosts_path=known_hosts_path,
            ),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
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
            _write_archive(report_root, process.stdin)
            process.stdin.close()
        except (BrokenPipeError, OSError, PublicationError) as error:
            with suppress(OSError):
                process.stdin.close() if process.stdin is not None else None
            with suppress(OSError):
                process.kill()
            process.communicate()
            raise PublicationError("SSH publication stream failed") from error
        stdout, _stderr = process.communicate()
        if process.returncode != 0:
            raise PublicationError("remote report publisher rejected the report")
        try:
            response = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PublicationError("remote report publisher returned invalid JSON") from error
        if not isinstance(response, dict) or response.get("status") not in {
            "published",
            "cleanup-failed",
        }:
            raise PublicationError("remote report publisher returned an invalid status")
        return response


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
    publish_parser = parser.add_subparsers(dest="command", required=True).add_parser("publish")
    publish_parser.add_argument("--report-root", type=Path, required=True)
    publish_parser.add_argument("--metadata", type=Path, required=True)
    publish_parser.add_argument("--publication", type=Path, required=True)
    publish_parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
