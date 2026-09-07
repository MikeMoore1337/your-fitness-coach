#!/usr/bin/env python3
"""Receive and atomically publish private Allure reports on the VPS origin."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import shutil
import sys
import tarfile
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager, suppress
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Final
from zoneinfo import ZoneInfo

REPORT_ROOT: Final = Path("/srv/yfc-allure-reports")
REPORT_BASE_URL: Final = "https://allure.your-fitness-coach.ru"
REPORT_TIMEZONE: Final = "Europe/Moscow"
PROTOCOL_MAGIC: Final = b"YFC-ALLURE-PUBLISH-v1\n"
REMOTE_COMMAND: Final = "yfc-allure-publish-v1"
MAX_REPORT_BYTES: Final = 100 * 1024 * 1024
MAX_ACTIVE_REPORT_BYTES: Final = 18 * MAX_REPORT_BYTES
MIN_FREE_BYTES: Final = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS: Final = 100_000
MAX_DURATION_SECONDS: Final = 7 * 24 * 60 * 60
DAILY_RETENTION_DAYS: Final = 14
WEEKLY_RETENTION_COUNT: Final = 4
WEEKLY_RETENTION_DAYS: Final = 35
_ALLOWED_ROOT_NAMES = frozenset(
    {".publish.lock", ".staging", "metadata", "index.html", "daily", "weekly"}
)
_ALLOWED_METADATA_NAMES = frozenset({"index.json"})
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CONTROL_CHARACTERS = re.compile(r"[\u0000-\u001f\u007f]")


class ReportOriginError(RuntimeError):
    """The isolated report origin rejected an unsafe or inconsistent request."""


_ORIGIN_ERRORS: Final = (ReportOriginError, OSError)
_MAIN_ERRORS: Final = (ReportOriginError, OSError, ValueError)
# The publisher runs with the VPS system Python 3.10, where datetime.UTC is unavailable.
_UTC: Final = timezone.utc  # noqa: UP017


def _safe_segment(value: object, *, field: str) -> str:
    if not isinstance(value, str) or len(value) > 256 or not _SAFE_SEGMENT.fullmatch(value):
        raise ReportOriginError(f"unsafe {field}")
    return value


def _safe_period(kind: str, value: object) -> str:
    period = _safe_segment(value, field="period")
    try:
        if kind == "daily":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
                raise ValueError
            parsed = date.fromisoformat(period)
            if parsed.isoformat() != period:
                raise ValueError
        elif not re.fullmatch(r"\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])", period):
            raise ValueError
        else:
            datetime.strptime(f"{period}-1", "%G-W%V-%u")
    except ValueError as error:
        raise ReportOriginError("report period is invalid") from error
    return period


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or len(value) > 16 * 1024:
        raise ReportOriginError("unsafe report member path")
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or not pure.parts
        or ".." in pure.parts
        or "\\" in value
        or any(
            not part or part in {".", ".."} or _CONTROL_CHARACTERS.search(part)
            for part in pure.parts
        )
    ):
        raise ReportOriginError("unsafe report member path")
    return pure.as_posix()


def _path_for(kind: object, period: object, run_id: object) -> str:
    normalized_kind = _safe_segment(kind, field="run kind")
    if normalized_kind not in {"daily", "weekly"}:
        raise ReportOriginError("unsupported run kind")
    normalized_period = _safe_period(normalized_kind, period)
    normalized_run_id = _safe_segment(run_id, field="run id")
    return f"{normalized_kind}/{normalized_period}/{normalized_run_id}/"


def _url_for(path: str) -> str:
    normalized = path.strip("/")
    if (
        not normalized
        or "\\" in normalized
        or any(part in {".", ".."} for part in normalized.split("/"))
    ):
        raise ReportOriginError("invalid report URL path")
    return f"{REPORT_BASE_URL}/{normalized}/"


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ReportOriginError("report timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReportOriginError("report timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ReportOriginError("report timestamp must include a timezone")
    return parsed.astimezone(_UTC)


def _local_date(value: object) -> date:
    return _parse_timestamp(value).astimezone(ZoneInfo(REPORT_TIMEZONE)).date()


def _safe_metadata_text(value: object, *, field: str, required: bool = False) -> str:
    if not isinstance(value, str) or (required and not value):
        raise ReportOriginError(f"report metadata field {field} is invalid")
    if _CONTROL_CHARACTERS.search(value) or len(value) > 4096:
        raise ReportOriginError(f"report metadata field {field} is invalid")
    return value


def _nonnegative_int(value: object, *, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > maximum:
        raise ReportOriginError(f"report metadata field {field} is invalid")
    return value


def _duration(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReportOriginError("report duration is invalid")
    result = float(value)
    if not math.isfinite(result) or result < 0 or result > MAX_DURATION_SECONDS:
        raise ReportOriginError("report duration is invalid")
    return result


def _counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ReportOriginError("report counts are invalid")
    allowed = {"passed", "failed", "broken", "skipped", "unknown", "total"}
    result: dict[str, int] = {}
    for key, item in value.items():
        if key not in allowed:
            continue
        result[key] = _nonnegative_int(item, field=f"counts.{key}", maximum=MAX_ARCHIVE_MEMBERS)
    return result


def _entry_from_header(header: Mapping[str, object]) -> dict[str, object]:
    kind = _safe_segment(header.get("run_kind"), field="run kind")
    if kind not in {"daily", "weekly"}:
        raise ReportOriginError("unsupported run kind")
    period = _safe_period(kind, header.get("period"))
    run_id = _safe_segment(header.get("run_id"), field="run id")
    path = _path_for(kind, period, run_id)
    if header.get("immutable_path") != path:
        raise ReportOriginError("report path is inconsistent")
    if header.get("url") != _url_for(path):
        raise ReportOriginError("report URL is not canonical")
    report_status = header.get("report_status")
    if report_status not in {"complete", "incomplete"}:
        raise ReportOriginError("report status is invalid")
    report_bytes = _nonnegative_int(
        header.get("report_bytes"), field="report_bytes", maximum=MAX_REPORT_BYTES
    )
    if report_bytes == 0:
        raise ReportOriginError("empty report is not publishable")
    counts = _counts(header.get("counts"))
    created_at = _parse_timestamp(header.get("created_at"))
    expected_period = (
        created_at.astimezone(ZoneInfo(REPORT_TIMEZONE)).strftime("%Y-%m-%d")
        if kind == "daily"
        else created_at.astimezone(ZoneInfo(REPORT_TIMEZONE)).strftime("%G-W%V")
    )
    if period != expected_period:
        raise ReportOriginError("report period does not match report timestamp")
    commit_sha = _safe_metadata_text(header.get("commit_sha"), field="commit_sha", required=True)
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ReportOriginError("commit SHA is invalid")
    workflow_url = _safe_metadata_text(
        header.get("workflow_url"), field="workflow_url", required=True
    )
    if not workflow_url.startswith("https://"):
        raise ReportOriginError("workflow URL must use HTTPS")
    status = (
        "incomplete"
        if report_status == "incomplete"
        else "passed"
        if counts.get("failed", 0) == 0 and counts.get("broken", 0) == 0
        else "failed"
    )
    created_date = created_at.astimezone(ZoneInfo(REPORT_TIMEZONE)).date()
    retention_days = DAILY_RETENTION_DAYS if kind == "daily" else WEEKLY_RETENTION_DAYS
    return {
        "kind": kind,
        "period": period,
        "run_id": run_id,
        "path": path,
        "url": _url_for(path),
        "created_at": created_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expires_at": (created_date + timedelta(days=retention_days)).isoformat(),
        "commit_sha": commit_sha,
        "workflow_url": workflow_url,
        "duration_seconds": _duration(header.get("duration_seconds", 0.0)),
        "counts": counts,
        "bytes": report_bytes,
        "status": status,
    }


def _validate_immutable_path(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("/"):
        raise ReportOriginError("report index contains an invalid immutable path")
    parts = value.rstrip("/").split("/")
    if len(parts) != 3:
        raise ReportOriginError("report index contains an invalid immutable path")
    try:
        expected = _path_for(*parts)
    except ReportOriginError as error:
        raise ReportOriginError("report index contains an invalid immutable path") from error
    if value != expected:
        raise ReportOriginError("report index contains an invalid immutable path")
    return value


def _entry_key(entry: Mapping[str, object]) -> str:
    return _validate_immutable_path(entry.get("path"))


def _state_from_payload(payload: Mapping[str, object]) -> tuple[list[dict[str, object]], list[str]]:
    if payload.get("schema_version") != 1:
        raise ReportOriginError("remote report index has an unsupported schema")
    reports = payload.get("reports")
    pending = payload.get("cleanup_pending")
    if not isinstance(reports, list) or not isinstance(pending, list):
        raise ReportOriginError("remote report index has invalid shape")
    normalized: list[dict[str, object]] = []
    paths: set[str] = set()
    for item in reports:
        if not isinstance(item, dict):
            raise ReportOriginError("remote report index contains an invalid report")
        path = _validate_immutable_path(item.get("path"))
        parts = path.rstrip("/").split("/")
        if (
            item.get("kind") != parts[0]
            or item.get("period") != parts[1]
            or item.get("run_id") != parts[2]
        ):
            raise ReportOriginError("remote report index identity does not match its path")
        if item.get("url") != _url_for(path):
            raise ReportOriginError("remote report index URL is not canonical")
        if path in paths:
            raise ReportOriginError("remote report index contains duplicate report paths")
        paths.add(path)
        _safe_metadata_text(item.get("commit_sha"), field="commit_sha", required=True)
        if not re.fullmatch(r"[0-9a-f]{40}", str(item.get("commit_sha"))):
            raise ReportOriginError("remote report index contains an invalid commit SHA")
        workflow_url = _safe_metadata_text(
            item.get("workflow_url"), field="workflow_url", required=True
        )
        if not workflow_url.startswith("https://"):
            raise ReportOriginError("remote report index contains an invalid workflow URL")
        created_at = _parse_timestamp(item.get("created_at"))
        expected_period = (
            created_at.astimezone(ZoneInfo(REPORT_TIMEZONE)).strftime("%Y-%m-%d")
            if parts[0] == "daily"
            else created_at.astimezone(ZoneInfo(REPORT_TIMEZONE)).strftime("%G-W%V")
        )
        if item.get("period") != expected_period:
            raise ReportOriginError("remote report index period does not match timestamp")
        retention_days = DAILY_RETENTION_DAYS if parts[0] == "daily" else WEEKLY_RETENTION_DAYS
        expected_expires_at = (
            created_at.astimezone(ZoneInfo(REPORT_TIMEZONE)).date() + timedelta(days=retention_days)
        ).isoformat()
        if item.get("expires_at") != expected_expires_at:
            raise ReportOriginError("remote report index expiry is invalid")
        _duration(item.get("duration_seconds", 0.0))
        bytes_count = _nonnegative_int(item.get("bytes"), field="bytes", maximum=MAX_REPORT_BYTES)
        if bytes_count == 0:
            raise ReportOriginError("remote report index contains an empty report")
        if item.get("status") not in {"passed", "failed", "incomplete"}:
            raise ReportOriginError("remote report index contains an invalid status")
        _counts(item.get("counts"))
        normalized.append(dict(item))
    normalized_pending: list[str] = []
    for item in pending:
        path = _validate_immutable_path(item)
        if path not in normalized_pending:
            normalized_pending.append(path)
    return normalized, normalized_pending


def _load_state(root: Path) -> tuple[list[dict[str, object]], list[str]]:
    state_path = root / "metadata" / "index.json"
    if not state_path.is_file():
        if root.exists():
            children = list(root.iterdir())
            if any(child.name not in {".publish.lock", ".staging"} for child in children):
                raise ReportOriginError("report index is missing while storage is not empty")
            staging = root / ".staging"
            if staging.is_dir() and any(staging.iterdir()):
                raise ReportOriginError("stale report staging data requires operator cleanup")
        return [], []
    if state_path.is_symlink():
        raise ReportOriginError("report index cannot be a symlink")
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReportOriginError("report index is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ReportOriginError("report index must be a JSON object")
    return _state_from_payload(payload)


def _resolved_target(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    candidate = root.joinpath(*parts)
    storage_root = root.resolve()
    for part in parts:
        root = root / part
        if root.is_symlink():
            raise ReportOriginError("report path contains a symlink")
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise ReportOriginError("report path cannot be resolved") from error
    if not resolved.is_relative_to(storage_root):
        raise ReportOriginError("report path escapes storage root")
    return candidate


def _report_bytes(root: Path, relative: str) -> int:
    report_root = _resolved_target(root, relative)
    if not report_root.is_dir() or report_root.is_symlink():
        raise ReportOriginError("indexed report directory is missing")
    total = 0
    for path in report_root.rglob("*"):
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise ReportOriginError("unsupported entry in report storage")
        if path.is_file():
            total += path.stat().st_size
            if total > MAX_REPORT_BYTES:
                raise ReportOriginError("stored report exceeds size limit")
    index = report_root / "index.html"
    if index.is_symlink() or not index.is_file():
        raise ReportOriginError("stored report has no index.html")
    return total


def _assert_layout(
    root: Path, reports: Sequence[Mapping[str, object]], pending: Sequence[str]
) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ReportOriginError("report storage root is invalid")
    for child in root.iterdir():
        if child.name not in _ALLOWED_ROOT_NAMES:
            raise ReportOriginError("unexpected entry in report storage root")
        if child.is_symlink():
            raise ReportOriginError("report storage contains a symlink")
        if child.name == ".publish.lock":
            if not child.is_file():
                raise ReportOriginError("publication lock is invalid")
            continue
        if child.name == "index.html" and not child.is_file():
            raise ReportOriginError("root index is invalid")
        if child.name != "index.html" and not child.is_dir():
            raise ReportOriginError("report storage directory is invalid")
    metadata = root / "metadata"
    if metadata.exists():
        for child in metadata.iterdir():
            if (
                child.name not in _ALLOWED_METADATA_NAMES
                or child.is_symlink()
                or not child.is_file()
            ):
                raise ReportOriginError("report metadata layout is invalid")
    known = {_entry_key(item) for item in reports}
    known.update(_validate_immutable_path(item) for item in pending)
    for kind in ("daily", "weekly"):
        kind_root = root / kind
        if not kind_root.exists():
            continue
        if kind_root.is_symlink() or not kind_root.is_dir():
            raise ReportOriginError("report storage layout is invalid")
        for period_root in kind_root.iterdir():
            if period_root.name == "latest":
                if period_root.is_symlink() or not period_root.is_dir():
                    raise ReportOriginError("latest report directory is invalid")
                children = list(period_root.iterdir())
                if len(children) > 1 or any(
                    child.name != "index.html" or child.is_symlink() or not child.is_file()
                    for child in children
                ):
                    raise ReportOriginError("latest report directory contains unexpected data")
                continue
            _safe_period(kind, period_root.name)
            if period_root.is_symlink() or not period_root.is_dir():
                raise ReportOriginError("report period directory is invalid")
            for run_root in period_root.iterdir():
                _safe_segment(run_root.name, field="run id")
                if run_root.is_symlink() or not run_root.is_dir():
                    raise ReportOriginError("report run directory is invalid")
                relative = f"{kind}/{period_root.name}/{run_root.name}/"
                if relative not in known:
                    raise ReportOriginError("unindexed report directory exists")
    for report in reports:
        relative = _entry_key(report)
        actual_bytes = _report_bytes(root, relative)
        if actual_bytes != report.get("bytes"):
            raise ReportOriginError("stored report size differs from report index")


def _retained_reports(
    reports: Sequence[Mapping[str, object]],
    *,
    current: Mapping[str, object],
    now: date,
) -> tuple[list[dict[str, object]], list[str]]:
    grouped: dict[str, list[dict[str, object]]] = {"daily": [], "weekly": []}
    for report in reports:
        kind = report.get("kind")
        if kind not in grouped:
            raise ReportOriginError("report index contains an unsupported kind")
        grouped[str(kind)].append(dict(report))
    current_kind = str(current["kind"])
    current_path = _entry_key(current)
    grouped[current_kind] = [
        report for report in grouped[current_kind] if _entry_key(report) != current_path
    ] + [dict(current)]
    retained: list[dict[str, object]] = []
    removed: list[str] = []
    for kind, items in grouped.items():
        items.sort(key=lambda item: _parse_timestamp(item.get("created_at")), reverse=True)
        if kind == "daily":
            cutoff = now - timedelta(days=DAILY_RETENTION_DAYS - 1)
            keep = [item for item in items if _local_date(item.get("created_at")) >= cutoff]
        else:
            cutoff = now - timedelta(days=WEEKLY_RETENTION_DAYS - 1)
            keep = [item for item in items if _local_date(item.get("created_at")) >= cutoff][
                :WEEKLY_RETENTION_COUNT
            ]
        if current_kind == kind and not any(_entry_key(item) == current_path for item in keep):
            keep.append(dict(current))
        keep_paths = {_entry_key(item) for item in keep}
        removed.extend(_entry_key(item) for item in items if _entry_key(item) not in keep_paths)
        retained.extend(keep)
    retained.sort(key=lambda item: _parse_timestamp(item.get("created_at")), reverse=True)
    return retained, list(dict.fromkeys(removed))


def _render_latest(entry: Mapping[str, object]) -> str:
    url = entry.get("url")
    if not isinstance(url, str):
        raise ReportOriginError("latest report has no URL")
    escaped = html.escape(url, quote=True)
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="robots" content="noindex,nofollow">'
        f'<meta http-equiv="refresh" content="0;url={escaped}">'
        "<title>Allure latest</title></head>"
        f'<body><p><a href="{escaped}">Открыть отчёт</a></p></body></html>\n'
    )


def _render_index(reports: Sequence[Mapping[str, object]]) -> str:
    sections: list[str] = []
    for kind, label in (("daily", "Daily"), ("weekly", "Weekly")):
        entries = [report for report in reports if report.get("kind") == kind]
        if entries:
            latest_url = _url_for(f"{kind}/latest/")
            action = (
                f'<a class="primary" target="_blank" rel="noopener noreferrer" '
                f'href="{html.escape(latest_url, quote=True)}">Открыть последний {label}-отчёт</a>'
            )
        else:
            action = '<span class="empty">Нет отчёта</span>'
        rows: list[str] = []
        for report in entries:
            url = report.get("url")
            if not isinstance(url, str):
                raise ReportOriginError("report index entry has no URL")
            counts = html.escape(
                json.dumps(report.get("counts", {}), ensure_ascii=False, sort_keys=True)
            )
            rows.append(
                "<tr>"
                f'<td><a target="_blank" rel="noopener noreferrer" href="{html.escape(url, quote=True)}">'
                f"{html.escape(str(report.get('period')))} · {html.escape(str(report.get('run_id')))}</a></td>"
                f"<td>{html.escape(str(report.get('status')))}</td>"
                f"<td>{html.escape(str(report.get('commit_sha', 'unknown')))}</td>"
                f"<td>{html.escape(str(report.get('duration_seconds', 0)))} s</td>"
                f"<td>{counts}</td>"
                f"<td>{html.escape(str(report.get('expires_at', 'unknown')))}</td>"
                "</tr>"
            )
        table = (
            "<p>История отсутствует.</p>"
            if not rows
            else "<table><thead><tr><th>Отчёт</th><th>Статус</th><th>SHA</th>"
            "<th>Длительность</th><th>Counts</th><th>Истекает</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
        sections.append(f"<section><h2>{label}</h2>{action}{table}</section>")
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="robots" content="noindex,nofollow">'
        '<meta http-equiv="Cache-Control" content="no-store">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'\">"
        "<title>YFC Allure reports</title><style>"
        "body{font:16px system-ui,sans-serif;max-width:1200px;margin:0 auto;padding:32px;"
        "color:#17202a;background:#f7f8fa}section{background:#fff;border:1px solid #dfe3e8;"
        "border-radius:12px;padding:24px;margin:20px 0}h1{margin-top:0}.primary{display:inline-block;"
        "padding:12px 18px;background:#1459d9;color:#fff;border-radius:8px;text-decoration:none;"
        "font-weight:700}.empty{color:#667085}table{border-collapse:collapse;width:100%;margin-top:18px;}"
        "th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #eaecf0;font-size:14px;}"
        "</style></head><body><h1>YFC · закрытые Allure-отчёты</h1>"
        "<p>Доступ разрешён только через Cloudflare Access.</p>"
        f"{''.join(sections)}</body></html>\n"
    )


def _atomic_write(path: Path, content: bytes) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ReportOriginError("cannot atomically write through a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o750)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _update_latest(root: Path, retained: Sequence[Mapping[str, object]], kind: str) -> None:
    entries = [report for report in retained if report.get("kind") == kind]
    latest_root = root / kind / "latest"
    latest_index = latest_root / "index.html"
    if latest_root.is_symlink():
        raise ReportOriginError("latest report directory cannot be a symlink")
    if entries:
        latest_root.mkdir(parents=True, exist_ok=True)
        os.chmod(latest_root, 0o750)
        _atomic_write(latest_index, _render_latest(entries[0]).encode("utf-8"))
        return
    if latest_index.is_symlink():
        raise ReportOriginError("latest report index cannot be a symlink")
    latest_index.unlink(missing_ok=True)
    if latest_root.is_dir() and not any(latest_root.iterdir()):
        latest_root.rmdir()


def _delete_report(root: Path, relative: str) -> None:
    target = _resolved_target(root, relative)
    if target.is_symlink():
        raise ReportOriginError("report cleanup encountered a symlink")
    if target.exists():
        if not target.is_dir():
            raise ReportOriginError("report cleanup encountered a non-directory")
        shutil.rmtree(target)


def _available_bytes(path: Path) -> int:
    stats = os.statvfs(path)
    return stats.f_bavail * stats.f_frsize


def _extract_archive(source: BinaryIO, destination: Path, expected_bytes: int) -> int:
    destination.mkdir(parents=True, exist_ok=False)
    os.chmod(destination, 0o750)
    total = 0
    members_seen: set[str] = set()
    try:
        with tarfile.open(fileobj=source, mode="r|gz") as archive:
            for count, member in enumerate(archive, start=1):
                if count > MAX_ARCHIVE_MEMBERS:
                    raise ReportOriginError("report archive contains too many members")
                relative = _safe_relative_path(member.name)
                if relative in members_seen:
                    raise ReportOriginError("report archive contains duplicate members")
                members_seen.add(relative)
                target = _resolved_target(destination, relative)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    for parent in target.parents:
                        if parent == destination:
                            break
                        os.chmod(parent, 0o750)
                    os.chmod(target, 0o750)
                    continue
                if not member.isfile() or member.issym() or member.islnk() or member.isdev():
                    raise ReportOriginError("report archive contains a non-regular member")
                if member.size < 0 or member.size > MAX_REPORT_BYTES - total:
                    raise ReportOriginError("report archive exceeds size limit")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ReportOriginError("report archive member cannot be read")
                target.parent.mkdir(parents=True, exist_ok=True)
                for parent in target.parents:
                    if parent == destination:
                        break
                    os.chmod(parent, 0o750)
                with target.open("xb") as output:
                    remaining = member.size
                    while remaining:
                        chunk = stream.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ReportOriginError("report archive member is truncated")
                        output.write(chunk)
                        remaining -= len(chunk)
                        total += len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                os.chmod(target, 0o640)
    except (OSError, tarfile.TarError) as error:
        raise ReportOriginError("report archive is invalid") from error
    if total != expected_bytes:
        raise ReportOriginError("report archive size differs from metadata")
    index = destination / "index.html"
    if index.is_symlink() or not index.is_file():
        raise ReportOriginError("report archive has no index.html")
    return total


def _handle_request_unlocked(
    source: BinaryIO,
    destination: BinaryIO,
    *,
    root: Path = REPORT_ROOT,
    now: datetime | None = None,
) -> dict[str, object]:
    original_command = os.environ.get("SSH_ORIGINAL_COMMAND", "")
    if original_command not in {"", REMOTE_COMMAND}:
        raise ReportOriginError("unsupported SSH command")
    if root.is_symlink():
        raise ReportOriginError("report storage root cannot be a symlink")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o750)
    moment = now or datetime.now(_UTC)
    if moment.tzinfo is None:
        raise ReportOriginError("publication timestamp must include a timezone")
    moment = moment.astimezone(_UTC)
    magic = source.read(len(PROTOCOL_MAGIC))
    if magic != PROTOCOL_MAGIC:
        raise ReportOriginError("unsupported publication protocol")
    header_line = source.readline(64 * 1024)
    if not header_line.endswith(b"\n"):
        raise ReportOriginError("publication metadata header is missing")
    try:
        header = json.loads(header_line)
    except json.JSONDecodeError as error:
        raise ReportOriginError("publication metadata is not valid JSON") from error
    if not isinstance(header, dict):
        raise ReportOriginError("publication metadata must be an object")
    current = _entry_from_header(header)
    reports, pending = _load_state(root)
    _assert_layout(root, reports, pending)
    existing = next((item for item in reports if _entry_key(item) == current["path"]), None)
    final_root = _resolved_target(root, str(current["path"]))
    if existing is None and final_root.exists():
        raise ReportOriginError("immutable report path exists outside the report index")
    if existing is not None and not final_root.exists():
        raise ReportOriginError("report index references a missing immutable report")
    if existing is not None:
        for field in (
            "kind",
            "period",
            "run_id",
            "url",
            "created_at",
            "commit_sha",
            "workflow_url",
            "duration_seconds",
            "status",
            "bytes",
            "counts",
        ):
            if existing.get(field) != current.get(field):
                raise ReportOriginError("immutable report path contains different metadata")
    if _available_bytes(root) < int(current["bytes"]) + MIN_FREE_BYTES:
        raise ReportOriginError("VPS free-space safety reserve is not available")
    report_now = moment.astimezone(ZoneInfo(REPORT_TIMEZONE)).date()
    retained, removed = _retained_reports(reports, current=current, now=report_now)
    removed = list(dict.fromkeys([*pending, *removed]))
    retained_paths = {_entry_key(report) for report in retained}
    removed = [path for path in removed if path not in retained_paths]
    if sum(int(item["bytes"]) for item in retained) > MAX_ACTIVE_REPORT_BYTES:
        raise ReportOriginError("retained report storage exceeds configured budget")
    staging_root = root / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    os.chmod(staging_root, 0o750)
    staging = staging_root / (
        f"{current['kind']}-{current['period']}-{current['run_id']}-{uuid.uuid4().hex}"
    )
    installed = False
    metadata_committed = False
    try:
        _extract_archive(source, staging, int(current["bytes"]))
        if existing is None:
            final_root.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(final_root.parent, 0o750)
            os.replace(staging, final_root)
            installed = True
        else:
            shutil.rmtree(staging)
        state = {
            "schema_version": 1,
            "updated_at": moment.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "reports": retained,
            "cleanup_pending": removed,
        }
        _atomic_write(
            root / "metadata" / "index.json",
            (json.dumps(state, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
        )
        metadata_committed = True
        _atomic_write(root / "index.html", _render_index(retained).encode("utf-8"))
        for kind in ("daily", "weekly"):
            _update_latest(root, retained, kind)
        cleanup_failed: list[str] = []
        for relative in removed:
            try:
                _delete_report(root, relative)
            except ReportOriginError:
                cleanup_failed.append(relative)
        if cleanup_failed:
            state["cleanup_pending"] = cleanup_failed
            _atomic_write(
                root / "metadata" / "index.json",
                (json.dumps(state, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
            )
        response = {
            "status": "cleanup-failed" if cleanup_failed else "published",
            "url": current["url"],
            "report_path": current["path"],
            "report_bytes": current["bytes"],
            "retained_reports": len(retained),
            "cleanup_pending": cleanup_failed,
            "idempotent": not installed,
            "expires_at": current["expires_at"],
        }
        destination.write(
            (json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n").encode()
        )
        destination.flush()
        return response
    except _ORIGIN_ERRORS:
        if installed and not metadata_committed:
            shutil.rmtree(final_root, ignore_errors=True)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


@contextmanager
def _publication_lock(root: Path):
    lock_path = root / ".publish.lock"
    if lock_path.is_symlink() or (lock_path.exists() and not lock_path.is_file()):
        raise ReportOriginError("publication lock is invalid")
    try:
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o640)
    except OSError as error:
        raise ReportOriginError("publication lock cannot be opened") from error
    try:
        os.chmod(lock_path, 0o640)
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except OSError as error:
        raise ReportOriginError("publication lock cannot be acquired") from error
    finally:
        if os.name == "nt":
            import msvcrt

            with suppress(OSError):
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            with suppress(OSError):
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def handle_request(
    source: BinaryIO,
    destination: BinaryIO,
    *,
    root: Path = REPORT_ROOT,
    now: datetime | None = None,
) -> dict[str, object]:
    if root.is_symlink():
        raise ReportOriginError("report storage root cannot be a symlink")
    try:
        resolved_root = root.resolve()
    except OSError as error:
        raise ReportOriginError("report storage root cannot be resolved") from error
    if resolved_root.exists() and not resolved_root.is_dir():
        raise ReportOriginError("report storage root is not a directory")
    resolved_root.mkdir(parents=True, exist_ok=True)
    os.chmod(resolved_root, 0o750)
    with _publication_lock(resolved_root):
        return _handle_request_unlocked(source, destination, root=resolved_root, now=now)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPORT_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        handle_request(sys.stdin.buffer, sys.stdout.buffer, root=args.root)
        return 0
    except _MAIN_ERRORS:
        try:
            sys.stdout.write(
                json.dumps({"status": "error", "error": "publication rejected"}) + "\n"
            )
            sys.stdout.flush()
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
