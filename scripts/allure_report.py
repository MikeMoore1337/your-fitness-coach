"""Aggregate, enrich and validate private Allure report inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import uuid
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Final

if __package__:
    from scripts.scheduled_regression import (
        MAX_REPORT_BYTES,
        REPORT_BASE_URL,
        REPORT_TIMEZONE,
        immutable_report_path,
        report_bundles,
        report_jobs,
        report_period,
        report_suites,
        report_url,
    )
else:
    from scheduled_regression import (
        MAX_REPORT_BYTES,
        REPORT_BASE_URL,
        REPORT_TIMEZONE,
        immutable_report_path,
        report_bundles,
        report_jobs,
        report_period,
        report_suites,
        report_url,
    )

RESULT_SUFFIXES: Final = ("-result.json", "-container.json")
METADATA_FILES: Final = frozenset(
    {
        "categories.json",
        "environment.properties",
        "executor.json",
        "history",
    }
)
MAX_RESULT_FILES: Final = 100_000
MAX_ZIP_SCAN_BYTES: Final = 16 * 1024 * 1024
GITHUB_TOKEN_PATTERN: Final = re.compile(r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{20,}\b")
JWT_PATTERN: Final = re.compile(
    r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)
DATABASE_URL_ASSIGNMENT_PATTERN: Final = re.compile(
    r"(?ix)\bdatabase_url\s*[:=]\s*(?P<quote>[\"']?)(?P<value>[^\s,}\"']+)(?P=quote)"
)
SENSITIVE_LITERAL_ASSIGNMENT_PATTERN: Final = re.compile(
    r"(?ix)\b(?:"
    r"telegram[_ -]?initdata|"
    r"bot[_ -]?internal[_ -]?token|"
    r"telegram[_ -]?bot[_ -]?token|"
    r"secret_key|access_token|refresh_token"
    r")\s*[:=]\s*(?P<quote>[\"'])(?P<value>[^\"'\r\n]*)(?P=quote)"
)
SENSITIVE_JSON_ASSIGNMENT_PATTERN: Final = re.compile(
    r"(?ix)[\"'](?:"
    r"telegram[_ -]?initdata|"
    r"bot[_ -]?internal[_ -]?token|"
    r"telegram[_ -]?bot[_ -]?token|"
    r"secret_key|access_token|refresh_token"
    r")[\"']\s*:\s*[\"'](?P<value>[^\"'\r\n]*)[\"']"
)
SENSITIVE_UNQUOTED_ASSIGNMENT_PATTERN: Final = re.compile(
    r"(?ix)\b(?:"
    r"telegram[_ -]?initdata|"
    r"bot[_ -]?internal[_ -]?token|"
    r"telegram[_ -]?bot[_ -]?token|"
    r"secret_key|access_token|refresh_token"
    r")\s*=\s*(?P<value>[A-Za-z0-9~+/=:_-]{12,})"
)
AUTHORIZATION_LITERAL_PATTERN: Final = re.compile(
    r"(?ix)\b(?:authorization|proxy-authorization)\s*[:=]\s*"
    r"(?P<quote>[\"'])(?:bearer\s+)?(?P<value>[^\"'\r\n]*)(?P=quote)"
)
AUTHORIZATION_JSON_PATTERN: Final = re.compile(
    r"(?ix)[\"'](?:authorization|proxy-authorization)[\"']\s*:\s*"
    r"[\"'](?:bearer\s+)?(?P<value>[^\"'\r\n]*)[\"']"
)
AUTHORIZATION_BEARER_PATTERN: Final = re.compile(
    r"(?ix)\b(?:authorization|proxy-authorization)\s*[:=]\s*"
    r"bearer\s+(?P<value>[A-Za-z0-9._~+/=-]{8,})"
)
COOKIE_LITERAL_PATTERN: Final = re.compile(
    r"(?ix)\b(?:cookie|set-cookie)\s*[:=]\s*"
    r"(?P<quote>[\"'])(?P<value>[^\"'\r\n]*=[^\"'\r\n]*)(?P=quote)"
)
SYNTHETIC_VALUE_PATTERN: Final = re.compile(
    r"(?ix)^(?:"
    r"(?:test|local|dev|e2e|mock|fake|dummy|fixture|synthetic)(?:[-_:].*)?"
    r"|task[-_:][a-z0-9-]+"
    r"|[a-z0-9]+(?:-[a-z0-9]+)*-(?:token|key|secret|password)(?:-[a-z0-9]+)*"
    r")$"
)
SAFE_NON_SECRET_VALUE_PATTERN: Final = re.compile(
    r"(?ix)^(?:undefined|null|none|empty|value|token|header|true|false)$"
)


class AllureReportError(RuntimeError):
    """The report input or generated report violates the publication contract."""


def _safe_segment(value: str, *, field: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise AllureReportError(f"unsafe {field}: {value!r}")
    return value


def _load_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AllureReportError(f"invalid JSON object: {path}") from error
    if not isinstance(payload, dict):
        raise AllureReportError(f"JSON object expected: {path}")
    return payload


def _is_synthetic_value(value: str) -> bool:
    normalized = value.strip()
    return not normalized or bool(SYNTHETIC_VALUE_PATTERN.fullmatch(normalized))


def _is_sensitive_literal(value: str) -> bool:
    normalized = value.strip()
    return (
        len(normalized) >= 8
        and not SAFE_NON_SECRET_VALUE_PATTERN.fullmatch(normalized)
        and not _is_synthetic_value(normalized)
    )


def _sensitive_text(text: str) -> bool:
    if GITHUB_TOKEN_PATTERN.search(text) or JWT_PATTERN.search(text):
        return True
    for match in DATABASE_URL_ASSIGNMENT_PATTERN.finditer(text):
        value = match.group("value")
        if (
            "://" in value
            and not value.lower().startswith("sqlite://")
            and _is_sensitive_literal(value)
        ):
            return True
    for pattern in (
        SENSITIVE_LITERAL_ASSIGNMENT_PATTERN,
        SENSITIVE_JSON_ASSIGNMENT_PATTERN,
        SENSITIVE_UNQUOTED_ASSIGNMENT_PATTERN,
        AUTHORIZATION_LITERAL_PATTERN,
        AUTHORIZATION_JSON_PATTERN,
        AUTHORIZATION_BEARER_PATTERN,
    ):
        for match in pattern.finditer(text):
            value = match.group("value")
            if _is_sensitive_literal(value):
                return True
    for match in COOKIE_LITERAL_PATTERN.finditer(text):
        _, value = match.group("value").split("=", 1)
        if _is_sensitive_literal(value.split(";", 1)[0]):
            return True
    return False


def _sensitive_bytes(data: bytes) -> bool:
    return _sensitive_text(data.decode("latin-1"))


def _scan_stream(stream: BinaryIO, *, source: Path, limit: int | None = None) -> None:
    tail = b""
    total = 0
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            return
        if not isinstance(chunk, bytes):
            raise AllureReportError(f"attachment cannot be scanned: {source}")
        total += len(chunk)
        if limit is not None and total > limit:
            raise AllureReportError(f"attachment is too large to scan safely: {source}")
        if _sensitive_bytes(tail + chunk):
            raise AllureReportError(f"sensitive content detected in Allure attachment: {source}")
        tail = (tail + chunk)[-512:]


def _scan_file(source: Path) -> None:
    try:
        with source.open("rb") as stream:
            _scan_stream(stream, source=source)
        is_zip = zipfile.is_zipfile(source)
        if source.suffix.lower() == ".zip" and not is_zip:
            raise AllureReportError(f"compressed attachment is invalid: {source}")
        if is_zip:
            scanned_bytes = 0
            with zipfile.ZipFile(source) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    if member.file_size > MAX_ZIP_SCAN_BYTES - scanned_bytes:
                        raise AllureReportError(
                            f"compressed attachment is too large to scan safely: {source}"
                        )
                    with archive.open(member) as member_stream:
                        _scan_stream(member_stream, source=source, limit=MAX_ZIP_SCAN_BYTES)
                    scanned_bytes += member.file_size
    except zipfile.BadZipFile as error:
        if source.suffix.lower() == ".zip":
            raise AllureReportError(f"compressed attachment is invalid: {source}") from error


def _validate_relative_name(name: str) -> str:
    pure = PurePosixPath(name)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise AllureReportError(f"unsafe result member: {name!r}")
    return pure.as_posix()


def _bundle_manifest(bundle: Path) -> dict[str, object]:
    manifest_path = bundle / "manifest.json"
    payload = _load_object(manifest_path)
    if payload.get("schema_version") != 1:
        raise AllureReportError(f"bundle manifest has unsupported schema: {manifest_path}")
    for field in ("file_count", "source_bytes"):
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AllureReportError(f"bundle manifest field {field!r} is invalid")
        if value > MAX_REPORT_BYTES:
            raise AllureReportError(f"bundle manifest field {field!r} exceeds report limit")
    suite = payload.get("suite")
    browser = payload.get("browser")
    if not isinstance(suite, str) or not isinstance(browser, str):
        raise AllureReportError(f"bundle manifest has invalid suite metadata: {manifest_path}")
    _safe_segment(suite, field="suite")
    _safe_segment(browser, field="browser")
    return payload


def _rewrite_attachment_sources(
    payload: dict[str, object], *, target_names: Mapping[str, str]
) -> None:
    def visit(value: object) -> None:
        if isinstance(value, dict):
            attachments = value.get("attachments")
            if attachments is not None:
                if not isinstance(attachments, list):
                    raise AllureReportError("Allure attachments must be a JSON list")
                for item in attachments:
                    if not isinstance(item, dict):
                        raise AllureReportError("Allure attachment entry must be a JSON object")
                    source = item.get("source")
                    if not isinstance(source, str):
                        raise AllureReportError("Allure attachment source is missing")
                    normalized_source = _validate_relative_name(source)
                    if normalized_source not in target_names:
                        raise AllureReportError(
                            f"Allure attachment is missing from bundle: {normalized_source}"
                        )
                    item["source"] = target_names[normalized_source]
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)


def _append_label(payload: dict[str, object], name: str, value: str) -> None:
    labels = payload.setdefault("labels", [])
    if not isinstance(labels, list):
        raise AllureReportError("Allure labels must be a JSON list")
    if any(isinstance(label, dict) and label.get("name") == name for label in labels):
        return
    labels.append({"name": name, "value": value})


def _append_parameter(payload: dict[str, object], name: str, value: str) -> None:
    parameters = payload.setdefault("parameters", [])
    if not isinstance(parameters, list):
        raise AllureReportError("Allure parameters must be a JSON list")
    if any(
        isinstance(parameter, dict) and parameter.get("name") == name for parameter in parameters
    ):
        return
    parameters.append({"name": name, "value": value})


def _enrich_result(
    payload: dict[str, object], *, suite: str, browser: str, run_kind: str, tier: str
) -> dict[str, object]:
    _append_label(payload, "feature", "scheduled-regression")
    _append_label(payload, "suite", suite)
    _append_label(payload, "tier", tier)
    _append_label(payload, "run_kind", run_kind)
    _append_parameter(payload, "browser", browser)
    _append_parameter(payload, "data_set", "synthetic-local")
    _append_parameter(payload, "tier", tier)
    _append_parameter(payload, "run_kind", run_kind)
    return payload


def _result_payload(path: Path) -> dict[str, object]:
    _scan_file(path)
    payload = _load_object(path)
    status = payload.get("status")
    if path.name.endswith("-result.json") and status not in {
        "passed",
        "failed",
        "broken",
        "skipped",
        "unknown",
    }:
        raise AllureReportError(f"Allure result has unsupported status: {path}")
    return payload


def _copy_text_checked(source: Path, destination: Path) -> None:
    _scan_file(source)
    shutil.copy2(source, destination)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_environment(
    results_root: Path,
    *,
    run_kind: str,
    tier: str,
    commit_sha: str,
    branch: str,
    run_url: str,
    operating_system: str,
    python_version: str,
    node_version: str,
    playwright_version: str,
) -> None:
    values = {
        "allure.report.kind": run_kind,
        "allure.report.tier": tier,
        "allure.report.commit": commit_sha,
        "allure.report.branch": branch,
        "allure.report.workflow": run_url,
        "allure.report.timezone": REPORT_TIMEZONE,
        "allure.report.os": operating_system,
        "allure.report.python": python_version,
        "allure.report.node": node_version,
        "allure.report.playwright": playwright_version,
    }
    if any("\n" in value or "\r" in value for value in values.values()):
        raise AllureReportError("report metadata contains a newline")
    text = "".join(f"{key}={value}\n" for key, value in values.items())
    (results_root / "environment.properties").write_text(text, encoding="utf-8", newline="\n")
    _write_json(
        results_root / "executor.json",
        {
            "name": "GitHub Actions",
            "type": "github-actions",
            "url": run_url,
            "buildName": f"YFC scheduled {run_kind} #{commit_sha[:12]}",
            "buildUrl": run_url,
        },
    )


def _synthetic_failure(
    *, issue: str, run_id: str, run_kind: str, tier: str, now: datetime
) -> dict[str, object]:
    identifier = uuid.uuid5(uuid.NAMESPACE_URL, f"yfc-allure-incomplete:{run_id}:{issue}")
    timestamp = int(now.timestamp() * 1000)
    return {
        "uuid": str(identifier),
        "historyId": hashlib.md5(str(identifier).encode("utf-8")).hexdigest(),
        "fullName": f"scheduled report integrity: {issue}",
        "name": "Scheduled report integrity",
        "status": "failed",
        "stage": "finished",
        "start": timestamp,
        "stop": timestamp,
        "statusDetails": {"message": issue},
        "labels": [
            {"name": "feature", "value": "scheduled-regression"},
            {"name": "suite", "value": "report-integrity"},
            {"name": "tier", "value": tier},
            {"name": "run_kind", "value": run_kind},
        ],
        "parameters": [
            {"name": "browser", "value": "none"},
            {"name": "data_set", "value": "synthetic-local"},
            {"name": "tier", "value": tier},
            {"name": "run_kind", "value": run_kind},
        ],
    }


def _merge_bundle(
    bundle: Path,
    *,
    output: Path,
    run_kind: str,
    tier: str,
    seen_suites: set[str],
    expected_bundle_keys: set[str],
    seen_bundle_keys: set[str],
) -> tuple[int, list[str]]:
    issues: list[str] = []
    try:
        manifest = _bundle_manifest(bundle)
    except AllureReportError as error:
        return 0, [str(error)]
    suite = str(manifest["suite"])
    browser = str(manifest["browser"])
    bundle_key = f"{suite}/{browser}"
    if bundle_key not in expected_bundle_keys:
        return 0, [f"unexpected result bundle: {bundle_key}"]
    files: dict[str, Path] = {}
    for path in bundle.rglob("*"):
        if path.is_symlink():
            return 0, [f"symlink is not allowed in result bundle: {path}"]
        if path.is_file():
            name = _validate_relative_name(path.relative_to(bundle).as_posix())
            files[name] = path
    if len(files) > MAX_RESULT_FILES:
        return 0, [f"suite {suite} ({browser}) contains too many result members"]
    result_files = {name: path for name, path in files.items() if name != "manifest.json"}
    actual_source_bytes = sum(path.stat().st_size for path in result_files.values())
    if (
        manifest["file_count"] != len(result_files)
        or manifest["source_bytes"] != actual_source_bytes
    ):
        return 0, [f"suite {suite} ({browser}) manifest does not match result members"]
    result_paths = [path for name, path in sorted(files.items()) if name.endswith(RESULT_SUFFIXES)]
    if not result_paths:
        return 0, [f"suite {suite} ({browser}) produced no Allure result files"]
    prefix = f"{_safe_segment(suite, field='suite')}__{_safe_segment(browser, field='browser')}"
    target_names = {
        name: f"{prefix}__{name.replace('/', '__')}"
        for name in files
        if name != "manifest.json" and name not in METADATA_FILES
    }
    if any((output / target_name).exists() for target_name in target_names.values()):
        return 0, [f"suite {suite} ({browser}) duplicates an existing result bundle"]
    for name, source in files.items():
        if name == "manifest.json" or name in METADATA_FILES:
            continue
        destination = output / target_names[name]
        try:
            if name.endswith(RESULT_SUFFIXES):
                payload = _result_payload(source)
                if name.endswith("-result.json"):
                    payload = _enrich_result(
                        payload,
                        suite=suite,
                        browser=browser,
                        run_kind=run_kind,
                        tier=tier,
                    )
                _rewrite_attachment_sources(payload, target_names=target_names)
                _write_json(destination, payload)
            else:
                _copy_text_checked(source, destination)
        except (AllureReportError, OSError) as error:
            issues.append(str(error))
    if not issues:
        seen_suites.add(suite)
        seen_bundle_keys.add(bundle_key)
    return len(result_paths) if not issues else 0, issues


def _count_results(results_root: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for path in results_root.glob("*-result.json"):
        payload = _result_payload(path)
        status = payload.get("status")
        if isinstance(status, str):
            counts[status] += 1
    return {
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0),
        "broken": counts.get("broken", 0),
        "skipped": counts.get("skipped", 0),
        "unknown": counts.get("unknown", 0),
        "total": sum(counts.values()),
    }


def aggregate_results(
    *,
    bundle_root: Path,
    output_root: Path,
    metadata_path: Path,
    run_kind: str,
    tier: str,
    run_id: str,
    commit_sha: str,
    branch: str,
    run_url: str,
    operating_system: str,
    python_version: str,
    node_version: str,
    playwright_version: str,
    duration_seconds: float,
    created_at: datetime | None = None,
) -> dict[str, object]:
    _safe_segment(run_id, field="run id")
    _safe_segment(commit_sha, field="commit SHA")
    output_root = output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise AllureReportError(f"refusing to mix into non-empty results directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    now = created_at or datetime.now(UTC)
    expected_suites = report_suites(run_kind)
    expected_bundle_keys = {f"{suite}/{browser}" for suite, browser in report_bundles(run_kind)}
    seen_suites: set[str] = set()
    seen_bundle_keys: set[str] = set()
    issues: list[str] = []
    result_count = 0
    bundles = (
        sorted(
            path
            for path in bundle_root.iterdir()
            if path.is_dir() and (path / "manifest.json").is_file()
        )
        if bundle_root.is_dir()
        else []
    )
    for bundle in bundles:
        count, bundle_issues = _merge_bundle(
            bundle,
            output=output_root,
            run_kind=run_kind,
            tier=tier,
            seen_suites=seen_suites,
            expected_bundle_keys=expected_bundle_keys,
            seen_bundle_keys=seen_bundle_keys,
        )
        result_count += count
        issues.extend(bundle_issues)
    missing_bundles = sorted(expected_bundle_keys - seen_bundle_keys)
    issues.extend(
        f"required result bundle produced no valid results: {bundle_key}"
        for bundle_key in missing_bundles
    )
    if issues:
        for index, issue in enumerate(dict.fromkeys(issues)):
            synthetic = _synthetic_failure(
                issue=issue,
                run_id=f"{run_id}-{index}",
                run_kind=run_kind,
                tier=tier,
                now=now,
            )
            _write_json(output_root / f"integrity-{index}-result.json", synthetic)
    _write_environment(
        output_root,
        run_kind=run_kind,
        tier=tier,
        commit_sha=commit_sha,
        branch=branch,
        run_url=run_url,
        operating_system=operating_system,
        python_version=python_version,
        node_version=node_version,
        playwright_version=playwright_version,
    )
    counts = _count_results(output_root)
    metadata: dict[str, object] = {
        "schema_version": 1,
        "status": "complete" if not issues else "incomplete",
        "run_kind": run_kind,
        "tier": tier,
        "run_id": run_id,
        "commit_sha": commit_sha,
        "branch": branch,
        "workflow_url": run_url,
        "timezone": REPORT_TIMEZONE,
        "created_at": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "period": report_period(run_kind, timestamp=now),
        "immutable_path": immutable_report_path(
            run_kind,
            period=report_period(run_kind, timestamp=now),
            run_id=run_id,
        ),
        "expected_suites": list(expected_suites),
        "present_suites": sorted(seen_suites),
        "expected_bundles": sorted(expected_bundle_keys),
        "present_bundles": sorted(seen_bundle_keys),
        "issues": list(dict.fromkeys(issues)),
        "result_files": result_count,
        "duration_seconds": round(max(0.0, duration_seconds), 3),
        "counts": counts,
        "limits": {"report_bytes": MAX_REPORT_BYTES},
        "report_base_url": REPORT_BASE_URL,
    }
    _write_json(metadata_path, metadata)
    return metadata


def validate_report(
    report_root: Path, *, metadata_path: Path, require_complete: bool = True
) -> dict[str, object]:
    if report_root.is_symlink():
        raise AllureReportError("generated Allure report root cannot be a symlink")
    report_root = report_root.resolve()
    if not report_root.is_dir() or not (report_root / "index.html").is_file():
        raise AllureReportError("generated Allure report has no index.html")
    total_bytes = 0
    for path in report_root.rglob("*"):
        if path.is_symlink():
            raise AllureReportError(f"symlink is not allowed in generated report: {path}")
        if path.is_file():
            _scan_file(path)
            total_bytes += path.stat().st_size
    if total_bytes > MAX_REPORT_BYTES:
        raise AllureReportError(f"generated report exceeds {MAX_REPORT_BYTES} bytes")
    metadata = _load_object(metadata_path)
    if metadata.get("status") not in {"complete", "incomplete"}:
        raise AllureReportError("generated report metadata has an unsupported status")
    if require_complete and metadata.get("status") != "complete":
        raise AllureReportError("generated report is explicitly incomplete")
    return {"status": "valid", "bytes": total_bytes, "metadata": metadata}


def write_summary(
    *,
    metadata_path: Path,
    publication_path: Path,
    test_results: Mapping[str, str],
    destination: Path,
) -> None:
    metadata = _load_object(metadata_path)
    publication = _load_object(publication_path) if publication_path.is_file() else {}
    kind = str(metadata.get("run_kind", "scheduled"))
    label = "Daily" if kind == "daily" else "Weekly"
    try:
        expected_jobs = report_jobs(kind)
    except ValueError as error:
        raise AllureReportError("report metadata has an unsupported run kind") from error
    status = (
        "passed" if all(test_results.get(job) == "success" for job in expected_jobs) else "failed"
    )
    publication_status = publication.get("status")
    lines: list[str] = []
    if publication_status == "published" and isinstance(publication.get("url"), str):
        lines.append(f"## Allure-отчёт: [Открыть {label} отчёт ↗]({publication['url']})")
    else:
        lines.append(f"## Allure-отчёт: {label} — публикация недоступна")
    lines.extend(
        [
            "",
            f"- Вид запуска: `{kind}`",
            f"- Tier: `{metadata.get('tier', 'unknown')}`",
            f"- Статус тестов: `{status}`",
            f"- Статус публикации: `{publication_status or 'not-published'}`",
            f"- Commit: `{metadata.get('commit_sha', 'unknown')}`",
            f"- Время запуска: `{metadata.get('created_at', 'unknown')}` ({REPORT_TIMEZONE})",
            f"- Длительность тестов: `{metadata.get('duration_seconds', 0)} s`",
            f"- Counts: `{json.dumps(metadata.get('counts', {}), ensure_ascii=False, sort_keys=True)}`",
            f"- Истекает по политике: `{publication.get('expires_at', 'not-published')}`",
        ]
    )
    if metadata.get("issues"):
        lines.extend(["", "### Целостность отчёта", ""])
        lines.extend(f"- {issue}" for issue in metadata["issues"] if isinstance(issue, str))
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def finalize(*, metadata_path: Path, publication_path: Path) -> None:
    metadata = _load_object(metadata_path)
    publication = _load_object(publication_path)
    if metadata.get("status") != "complete":
        raise AllureReportError("scheduled report is incomplete")
    if publication.get("status") != "published":
        raise AllureReportError("scheduled report publication did not succeed")
    immutable_path = metadata.get("immutable_path")
    if not isinstance(immutable_path, str):
        raise AllureReportError("report metadata has no immutable path")
    try:
        expected_url = report_url(immutable_path)
    except ValueError as error:
        raise AllureReportError("report metadata has an invalid immutable path") from error
    if publication.get("report_path") != immutable_path or publication.get("url") != expected_url:
        raise AllureReportError("publication URL is not canonical")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("--bundle-root", type=Path, required=True)
    aggregate.add_argument("--output-root", type=Path, required=True)
    aggregate.add_argument("--metadata", type=Path, required=True)
    aggregate.add_argument("--run-kind", choices=("daily", "weekly"), required=True)
    aggregate.add_argument("--tier", required=True)
    aggregate.add_argument("--run-id", required=True)
    aggregate.add_argument("--commit-sha", required=True)
    aggregate.add_argument("--branch", required=True)
    aggregate.add_argument("--run-url", required=True)
    aggregate.add_argument("--operating-system", default="ubuntu-latest")
    aggregate.add_argument("--python-version", default="3.14")
    aggregate.add_argument("--node-version", default="24")
    aggregate.add_argument("--playwright-version", required=True)
    aggregate.add_argument("--duration-seconds", type=float, default=0.0)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--report-root", type=Path, required=True)
    validate.add_argument("--metadata", type=Path, required=True)
    summary = subparsers.add_parser("summary")
    summary.add_argument("--metadata", type=Path, required=True)
    summary.add_argument("--publication", type=Path, required=True)
    summary.add_argument("--test-results", required=True)
    summary.add_argument("--output", type=Path, required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--metadata", type=Path, required=True)
    finalize_parser.add_argument("--publication", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "aggregate":
            payload = aggregate_results(
                bundle_root=args.bundle_root,
                output_root=args.output_root,
                metadata_path=args.metadata,
                run_kind=args.run_kind,
                tier=args.tier,
                run_id=args.run_id,
                commit_sha=args.commit_sha,
                branch=args.branch,
                run_url=args.run_url,
                operating_system=args.operating_system,
                python_version=args.python_version,
                node_version=args.node_version,
                playwright_version=args.playwright_version,
                duration_seconds=args.duration_seconds,
            )
        elif args.command == "validate":
            payload = validate_report(args.report_root, metadata_path=args.metadata)
        elif args.command == "summary":
            test_results = json.loads(args.test_results)
            if not isinstance(test_results, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in test_results.items()
            ):
                raise AllureReportError("test results must be a JSON string map")
            write_summary(
                metadata_path=args.metadata,
                publication_path=args.publication,
                test_results=test_results,
                destination=args.output,
            )
            payload = {"status": "summary-written", "output": args.output.as_posix()}
        elif args.command == "finalize":
            finalize(metadata_path=args.metadata, publication_path=args.publication)
            payload = {"status": "published"}
        else:
            raise AssertionError(f"Unhandled command: {args.command}")
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except (AllureReportError, OSError, json.JSONDecodeError) as error:
        print(f"allure report error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
