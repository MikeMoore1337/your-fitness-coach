"""Publish a generated Allure report to the private Cloudflare R2-backed origin."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

if __package__:
    from scripts.allure_report import validate_report
    from scripts.scheduled_regression import (
        DAILY_RETENTION_DAYS,
        WEEKLY_RETENTION_COUNT,
        WEEKLY_RETENTION_DAYS,
        immutable_report_path,
        latest_report_path,
        report_url,
    )
else:
    from allure_report import validate_report
    from scheduled_regression import (
        DAILY_RETENTION_DAYS,
        WEEKLY_RETENTION_COUNT,
        WEEKLY_RETENTION_DAYS,
        immutable_report_path,
        latest_report_path,
        report_url,
    )

STATE_KEY = "metadata/index.json"
R2_ENDPOINT_ENV = "ALLURE_R2_ENDPOINT"
R2_BUCKET_ENV = "ALLURE_R2_BUCKET"
R2_ACCESS_KEY_ENV = "ALLURE_R2_ACCESS_KEY_ID"
R2_SECRET_KEY_ENV = "ALLURE_R2_SECRET_ACCESS_KEY"
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


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


def _validate_storage_config() -> tuple[str, str, str, str]:
    endpoint = os.environ.get(R2_ENDPOINT_ENV, "").strip()
    bucket = os.environ.get(R2_BUCKET_ENV, "").strip()
    access_key = os.environ.get(R2_ACCESS_KEY_ENV, "")
    secret_key = os.environ.get(R2_SECRET_KEY_ENV, "")
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".r2.cloudflarestorage.com")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise PublicationError("R2 endpoint must be an HTTPS Cloudflare R2 S3 endpoint")
    if not _BUCKET_RE.fullmatch(bucket):
        raise PublicationError("R2 bucket name is invalid")
    if not access_key or not secret_key:
        raise PublicationError("R2 publication credentials are not configured")
    return endpoint, bucket, access_key, secret_key


def _aws_env(access_key: str, secret_key: str) -> dict[str, str]:
    return {
        **os.environ,
        "AWS_ACCESS_KEY_ID": access_key,
        "AWS_SECRET_ACCESS_KEY": secret_key,
        "AWS_DEFAULT_REGION": "auto",
        "AWS_EC2_METADATA_DISABLED": "true",
    }


def _run_aws(
    args: Sequence[str], *, env: Mapping[str, str], capture_output: bool = True
) -> subprocess.CompletedProcess[str]:
    command = ["aws", *args]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=capture_output,
        text=True,
        env=dict(env),
    )
    if completed.returncode != 0:
        raise PublicationError("Cloudflare R2 operation failed")
    return completed


def _validate_immutable_prefix(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("/"):
        raise PublicationError("report index contains an invalid immutable path")
    parts = value.rstrip("/").split("/")
    if len(parts) != 3:
        raise PublicationError("report index contains an invalid immutable path")
    try:
        expected = immutable_report_path(parts[0], period=parts[1], run_id=parts[2])
    except ValueError as error:
        raise PublicationError("report index contains an invalid immutable path") from error
    if value != expected:
        raise PublicationError("report index contains an invalid immutable path")
    return value


def _state_from_payload(payload: Mapping[str, object]) -> tuple[list[dict[str, object]], list[str]]:
    if payload.get("schema_version") != 1:
        raise PublicationError("remote report index has an unsupported schema")
    if "reports" not in payload or "cleanup_pending" not in payload:
        raise PublicationError("remote report index is missing required fields")
    reports = payload.get("reports", [])
    pending = payload.get("cleanup_pending", [])
    if not isinstance(reports, list) or not isinstance(pending, list):
        raise PublicationError("remote report index has invalid shape")
    normalized_reports: list[dict[str, object]] = []
    paths: set[str] = set()
    for report in reports:
        if not isinstance(report, dict):
            raise PublicationError("remote report index contains an invalid report")
        path = report.get("path")
        kind = report.get("kind")
        if not isinstance(path, str) or not isinstance(kind, str):
            raise PublicationError("remote report index contains incomplete report metadata")
        validated_path = _validate_immutable_prefix(path)
        path_parts = validated_path.rstrip("/").split("/")
        if (
            kind != path_parts[0]
            or report.get("period") != path_parts[1]
            or report.get("run_id") != path_parts[2]
        ):
            raise PublicationError("remote report index identity does not match its path")
        if report.get("url") != report_url(validated_path):
            raise PublicationError("remote report index URL is not canonical")
        if path in paths:
            raise PublicationError("remote report index contains duplicate report paths")
        paths.add(path)
        _parse_timestamp(report.get("created_at"))
        normalized_reports.append(dict(report))
    normalized_pending: list[str] = []
    for item in pending:
        try:
            _validate_immutable_prefix(item)
        except PublicationError as error:
            raise PublicationError("remote cleanup queue contains an invalid path") from error
        if item not in normalized_pending:
            normalized_pending.append(item)
    return normalized_reports, normalized_pending


def _read_remote_state(
    *, endpoint: str, bucket: str, env: Mapping[str, str]
) -> tuple[list[dict[str, object]], list[str]]:
    target = f"s3://{bucket}/{STATE_KEY}"
    command = [
        "s3api",
        "head-object",
        "--bucket",
        bucket,
        "--key",
        STATE_KEY,
        "--endpoint-url",
        endpoint,
        "--output",
        "json",
    ]
    completed = subprocess.run(
        ["aws", *command],
        check=False,
        capture_output=True,
        text=True,
        env=dict(env),
    )
    if completed.returncode != 0:
        stderr = completed.stderr.lower()
        if "404" not in stderr and "not found" not in stderr and "nosuchkey" not in stderr:
            raise PublicationError("cannot inspect the remote report index")
        if _remote_prefix_exists(bucket=bucket, prefix="", endpoint=endpoint, env=env):
            raise PublicationError("remote report index is missing while storage is not empty")
        return [], []
    completed = _run_aws(
        [
            "s3",
            "cp",
            target,
            "-",
            "--endpoint-url",
            endpoint,
            "--only-show-errors",
        ],
        env=env,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise PublicationError("remote report index is not valid JSON") from error
    if not isinstance(payload, dict):
        raise PublicationError("remote report index must be a JSON object")
    return _state_from_payload(payload)


def _remote_prefix_exists(
    *, bucket: str, prefix: str, endpoint: str, env: Mapping[str, str]
) -> bool:
    completed = _run_aws(
        [
            "s3api",
            "list-objects-v2",
            "--bucket",
            bucket,
            "--prefix",
            prefix,
            "--max-keys",
            "1",
            "--endpoint-url",
            endpoint,
            "--output",
            "json",
        ],
        env=env,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise PublicationError("remote report prefix response is not valid JSON") from error
    if not isinstance(payload, dict):
        raise PublicationError("remote report prefix response has invalid shape")
    objects = payload.get("Contents", [])
    if not isinstance(objects, list):
        raise PublicationError("remote report prefix response has invalid object list")
    return bool(objects)


def _entry_from_metadata(metadata: Mapping[str, object], *, report_bytes: int) -> dict[str, object]:
    kind = metadata.get("run_kind")
    period = metadata.get("period")
    run_id = metadata.get("run_id")
    if not all(isinstance(value, str) for value in (kind, period, run_id)):
        raise PublicationError("report metadata has no path identity")
    path = immutable_report_path(str(kind), period=str(period), run_id=str(run_id))
    if metadata.get("immutable_path") != path:
        raise PublicationError("report metadata path is inconsistent")
    created_at = _parse_timestamp(metadata.get("created_at"))
    today = created_at.date()
    if kind == "daily":
        expires = today + timedelta(days=DAILY_RETENTION_DAYS)
    elif kind == "weekly":
        expires = today + timedelta(days=WEEKLY_RETENTION_DAYS)
    else:
        raise PublicationError("unsupported report kind")
    counts = metadata.get("counts")
    if not isinstance(counts, dict):
        raise PublicationError("report counts are missing")
    report_status = metadata.get("status")
    if report_status not in {"complete", "incomplete"}:
        raise PublicationError("report metadata status is unsupported")
    if report_status == "incomplete":
        status = "incomplete"
    else:
        status = (
            "passed" if counts.get("failed", 0) == 0 and counts.get("broken", 0) == 0 else "failed"
        )
    return {
        "kind": kind,
        "period": period,
        "run_id": run_id,
        "path": path,
        "url": report_url(path),
        "created_at": created_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expires_at": expires.isoformat(),
        "commit_sha": metadata.get("commit_sha", ""),
        "workflow_url": metadata.get("workflow_url", ""),
        "duration_seconds": metadata.get("duration_seconds", 0),
        "counts": counts,
        "bytes": report_bytes,
        "status": status,
    }


def _entry_key(entry: Mapping[str, object]) -> str:
    value = entry.get("path")
    return _validate_immutable_prefix(value)


def _retained_reports(
    reports: Sequence[Mapping[str, object]], *, current: Mapping[str, object], now: date
) -> tuple[list[dict[str, object]], list[str]]:
    by_kind: dict[str, list[dict[str, object]]] = {"daily": [], "weekly": []}
    for report in reports:
        kind = report.get("kind")
        if kind not in by_kind:
            raise PublicationError("report index contains an unsupported kind")
        by_kind[str(kind)].append(dict(report))
    for item in (dict(current),):
        kind = item.get("kind")
        if kind not in by_kind:
            raise PublicationError("current report kind is unsupported")
        current_path = _entry_key(item)
        by_kind[str(kind)] = [
            report for report in by_kind[str(kind)] if _entry_key(report) != current_path
        ] + [item]

    retained: list[dict[str, object]] = []
    removed: list[str] = []
    for kind, items in by_kind.items():
        items.sort(key=lambda item: _parse_timestamp(item.get("created_at")), reverse=True)
        if kind == "daily":
            limit = now - timedelta(days=DAILY_RETENTION_DAYS - 1)
            keep = [
                item for item in items if _parse_timestamp(item.get("created_at")).date() >= limit
            ]
        else:
            keep = [
                item
                for item in items
                if _parse_timestamp(item.get("created_at")).date()
                >= now - timedelta(days=WEEKLY_RETENTION_DAYS - 1)
            ][:WEEKLY_RETENTION_COUNT]
        if current.get("kind") == kind:
            current_path = _entry_key(current)
            if not any(_entry_key(item) == current_path for item in keep):
                keep.append(dict(current))
        keep_paths = {_entry_key(item) for item in keep}
        removed.extend(_entry_key(item) for item in items if _entry_key(item) not in keep_paths)
        retained.extend(keep)
    retained.sort(key=lambda item: _parse_timestamp(item.get("created_at")), reverse=True)
    return retained, removed


def _render_latest(entry: Mapping[str, object]) -> str:
    url = entry.get("url")
    if not isinstance(url, str):
        raise PublicationError("latest report entry has no URL")
    escaped_url = html.escape(url, quote=True)
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="robots" content="noindex,nofollow">'
        f'<meta http-equiv="refresh" content="0;url={escaped_url}">'
        f"<title>Allure {html.escape(str(entry.get('kind', 'scheduled')))}</title></head>"
        f'<body><p><a href="{escaped_url}">Открыть отчёт</a></p></body></html>\n'
    )


def _render_index(reports: Sequence[Mapping[str, object]]) -> str:
    grouped = {"daily": [], "weekly": []}
    for report in reports:
        kind = report.get("kind")
        if kind in grouped:
            grouped[str(kind)].append(report)

    def link(report: Mapping[str, object]) -> str:
        url = report.get("url")
        if not isinstance(url, str):
            raise PublicationError("report index entry has no URL")
        label = f"{report.get('period', 'unknown')} · {report.get('run_id', 'unknown')}"
        return (
            f'<a target="_blank" rel="noopener noreferrer" href="{html.escape(url, quote=True)}">'
            f"{html.escape(label)}</a>"
        )

    sections: list[str] = []
    for kind, label in (("daily", "Daily"), ("weekly", "Weekly")):
        latest = grouped[kind][0] if grouped[kind] else None
        if latest is None:
            action = '<span class="empty">Нет отчёта</span>'
        else:
            latest_url = report_url(latest_report_path(kind))
            action = (
                f'<a class="primary" target="_blank" rel="noopener noreferrer" '
                f'href="{html.escape(latest_url, quote=True)}">Открыть последний {label}-отчёт</a>'
            )
        rows: list[str] = []
        for report in grouped[kind]:
            counts = report.get("counts", {})
            counts_text = html.escape(json.dumps(counts, ensure_ascii=False, sort_keys=True))
            rows.append(
                "<tr>"
                f"<td>{link(report)}</td>"
                f"<td>{html.escape(str(report.get('status', 'unknown')))}</td>"
                f"<td>{html.escape(str(report.get('commit_sha', 'unknown')))}</td>"
                f"<td>{html.escape(str(report.get('duration_seconds', 0)))} s</td>"
                f"<td>{counts_text}</td>"
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


def _upload_file(
    path: Path,
    *,
    bucket: str,
    key: str,
    endpoint: str,
    env: Mapping[str, str],
    content_type: str,
) -> None:
    _run_aws(
        [
            "s3",
            "cp",
            str(path),
            f"s3://{bucket}/{key}",
            "--endpoint-url",
            endpoint,
            "--only-show-errors",
            "--cache-control",
            "private, no-store",
            "--content-type",
            content_type,
        ],
        env=env,
    )


def _upload_report(
    root: Path, *, bucket: str, prefix: str, endpoint: str, env: Mapping[str, str]
) -> None:
    _run_aws(
        [
            "s3",
            "sync",
            str(root),
            f"s3://{bucket}/{prefix}",
            "--endpoint-url",
            endpoint,
            "--only-show-errors",
            "--delete",
            "--cache-control",
            "private, no-store",
        ],
        env=env,
    )


def _delete_prefix(*, bucket: str, prefix: str, endpoint: str, env: Mapping[str, str]) -> None:
    _run_aws(
        [
            "s3",
            "rm",
            f"s3://{bucket}/{prefix}",
            "--recursive",
            "--endpoint-url",
            endpoint,
            "--only-show-errors",
        ],
        env=env,
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
    if metadata.get("status") not in {"complete", "incomplete"}:
        raise PublicationError("refusing to publish a report with unsupported status")
    validation = validate_report(
        report_root,
        metadata_path=metadata_path,
        require_complete=False,
    )
    report_bytes = int(validation["bytes"])
    endpoint, bucket, access_key, secret_key = (
        _validate_storage_config()
        if not dry_run
        else (
            "https://dry-run.r2.cloudflarestorage.com",
            "dry-run-bucket",
            "dry-run-access-key",
            "dry-run-secret-key",
        )
    )
    current = _entry_from_metadata(metadata, report_bytes=report_bytes)
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        raise PublicationError("publication timestamp must include a timezone")
    moment = moment.astimezone(UTC)
    old_reports: list[dict[str, object]] = []
    pending: list[str] = []
    if not dry_run:
        env = _aws_env(access_key, secret_key)
        old_reports, pending = _read_remote_state(endpoint=endpoint, bucket=bucket, env=env)
    retained, removed = _retained_reports(old_reports, current=current, now=moment.date())
    removed = list(dict.fromkeys([*pending, *removed]))
    retained_paths = {_entry_key(report) for report in retained}
    removed = [path for path in removed if path not in retained_paths]
    started = time.monotonic()
    if dry_run:
        publication = {
            "status": "dry-run",
            "url": current["url"],
            "report_path": current["path"],
            "report_bytes": report_bytes,
            "retained_reports": len(retained),
            "cleanup_candidates": removed,
        }
        publication_path.parent.mkdir(parents=True, exist_ok=True)
        publication_path.write_text(
            json.dumps(publication, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return publication

    env = _aws_env(access_key, secret_key)
    prefix = str(current["path"])
    existing = next(
        (report for report in old_reports if _entry_key(report) == prefix),
        None,
    )
    report_already_published = existing is not None
    if existing is not None:
        for field in ("commit_sha", "status", "bytes", "counts"):
            if existing.get(field) != current.get(field):
                raise PublicationError(
                    "immutable report path already contains different report metadata"
                )
        if not _remote_prefix_exists(
            bucket=bucket,
            prefix=prefix,
            endpoint=endpoint,
            env=env,
        ):
            raise PublicationError("remote report index references a missing immutable report")
    elif _remote_prefix_exists(bucket=bucket, prefix=prefix, endpoint=endpoint, env=env):
        raise PublicationError("immutable report path already exists outside the report index")

    report_uploaded = report_already_published
    try:
        if not report_already_published:
            _upload_report(report_root, bucket=bucket, prefix=prefix, endpoint=endpoint, env=env)
            report_uploaded = True
        with tempfile.TemporaryDirectory(
            prefix="allure-publication-", dir=metadata_path.parent
        ) as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(
                _render_index(retained), encoding="utf-8", newline="\n"
            )
            state = {
                "schema_version": 1,
                "updated_at": moment.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "reports": retained,
                "cleanup_pending": removed,
            }
            (root / "state.json").write_text(
                json.dumps(state, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            _upload_file(
                root / "state.json",
                bucket=bucket,
                key=STATE_KEY,
                endpoint=endpoint,
                env=env,
                content_type="application/json; charset=utf-8",
            )
            _upload_file(
                root / "index.html",
                bucket=bucket,
                key="index.html",
                endpoint=endpoint,
                env=env,
                content_type="text/html; charset=utf-8",
            )
            for kind in ("daily", "weekly"):
                kind_reports = [report for report in retained if report.get("kind") == kind]
                if not kind_reports:
                    continue
                latest = max(
                    kind_reports, key=lambda report: _parse_timestamp(report.get("created_at"))
                )
                latest_html = root / f"{kind}-latest.html"
                latest_html.write_text(_render_latest(latest), encoding="utf-8", newline="\n")
                _upload_file(
                    latest_html,
                    bucket=bucket,
                    key=f"{latest_report_path(kind)}index.html",
                    endpoint=endpoint,
                    env=env,
                    content_type="text/html; charset=utf-8",
                )
        cleanup_started = time.monotonic()
        cleanup_failed: list[str] = []
        for stale_path in removed:
            try:
                _delete_prefix(bucket=bucket, prefix=stale_path, endpoint=endpoint, env=env)
            except PublicationError:
                cleanup_failed.append(stale_path)
        cleanup_seconds = round(time.monotonic() - cleanup_started, 3)
        if cleanup_failed:
            state = {
                "schema_version": 1,
                "updated_at": moment.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "reports": retained,
                "cleanup_pending": cleanup_failed,
            }
            with tempfile.NamedTemporaryFile(
                prefix="allure-state-",
                suffix=".json",
                mode="w",
                encoding="utf-8",
                dir=metadata_path.parent,
                delete=False,
            ) as stream:
                state_path = Path(stream.name)
                json.dump(state, stream, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
            try:
                _upload_file(
                    state_path,
                    bucket=bucket,
                    key=STATE_KEY,
                    endpoint=endpoint,
                    env=env,
                    content_type="application/json; charset=utf-8",
                )
            finally:
                state_path.unlink(missing_ok=True)
            publication = {
                "status": "cleanup-failed",
                "url": current["url"],
                "report_path": current["path"],
                "report_bytes": report_bytes,
                "cleanup_seconds": cleanup_seconds,
                "cleanup_pending": cleanup_failed,
            }
        else:
            publication = {
                "status": "published",
                "url": current["url"],
                "report_path": current["path"],
                "report_bytes": report_bytes,
                "retained_reports": len(retained),
                "cleanup_seconds": cleanup_seconds,
                "published_seconds": round(time.monotonic() - started, 3),
                "expires_at": current["expires_at"],
            }
    except PublicationError:
        if not report_uploaded:
            with suppress(PublicationError):
                _delete_prefix(bucket=bucket, prefix=prefix, endpoint=endpoint, env=env)
        raise
    publication_path.parent.mkdir(parents=True, exist_ok=True)
    publication_path.write_text(
        json.dumps(publication, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
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
