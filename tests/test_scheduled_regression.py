import io
import json
import shutil
import tarfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from scripts import (
    allure_bundle,
    allure_report,
    allure_report_origin,
    publish_allure_report,
    scheduled_regression,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_bundle(
    root: Path,
    *,
    suite: str,
    browser: str,
    status: str = "passed",
    attachment_text: str = "synthetic output",
) -> None:
    bundle = root / f"{suite}-{browser}"
    bundle.mkdir(parents=True)
    _write_json(
        bundle / "manifest.json",
        {
            "schema_version": 1,
            "suite": suite,
            "browser": browser,
            "file_count": 2,
            "source_bytes": 0,
        },
    )
    _write_json(
        bundle / f"{suite}-result.json",
        {
            "uuid": f"uuid-{suite}-{browser}",
            "name": suite,
            "fullName": f"{suite}::{browser}",
            "status": status,
            "attachments": [{"name": "stdout", "source": "stdout.txt"}],
        },
    )
    (bundle / "stdout.txt").write_text(attachment_text, encoding="utf-8")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["source_bytes"] = sum(
        path.stat().st_size for path in bundle.iterdir() if path.name != "manifest.json"
    )
    _write_json(bundle / "manifest.json", manifest)


def _aggregate_metadata(
    tmp_path: Path, *, attachment_text: str = "synthetic output"
) -> dict[str, object]:
    bundles = tmp_path / "bundles"
    for suite, browser in scheduled_regression.report_bundles("daily"):
        _write_bundle(
            bundles,
            suite=suite,
            browser=browser,
            attachment_text=attachment_text,
        )
    metadata_path = tmp_path / "metadata.json"
    return allure_report.aggregate_results(
        bundle_root=bundles,
        output_root=tmp_path / "merged",
        metadata_path=metadata_path,
        run_kind="daily",
        tier="daily-regression",
        run_id="12345",
        commit_sha="a" * 40,
        branch="master",
        run_url="https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/12345",
        operating_system="ubuntu-latest",
        python_version="3.14",
        node_version="24",
        playwright_version="1.62.1",
        duration_seconds=12.5,
        created_at=datetime(2026, 9, 7, 1, 0, tzinfo=UTC),
    )


def test_schedule_contract_resolves_daily_weekly_and_rejects_unknown_cron() -> None:
    assert (
        scheduled_regression.resolve_run_kind(
            "schedule", schedule_cron=scheduled_regression.DAILY_SCHEDULE_CRON
        )
        == "daily"
    )
    assert (
        scheduled_regression.resolve_run_kind(
            "schedule", schedule_cron=scheduled_regression.WEEKLY_SCHEDULE_CRON
        )
        == "weekly"
    )
    assert scheduled_regression.resolve_run_kind("workflow_dispatch", run_kind="weekly") == "weekly"
    with pytest.raises(scheduled_regression.ScheduledRegressionError):
        scheduled_regression.resolve_run_kind("schedule", schedule_cron="0 0 * * *")


def test_private_report_origin_uses_isolated_caddy_and_dedicated_tunnel() -> None:
    root = Path(__file__).parents[1]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    caddy = (root / "deploy" / "allure-report-origin" / "Caddyfile").read_text(encoding="utf-8")
    cross_browser = (root / "frontend" / "playwright.cross-browser.config.ts").read_text(
        encoding="utf-8"
    )
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    action = (root / ".github" / "actions" / "upload-allure-results" / "action.yml").read_text(
        encoding="utf-8"
    )
    public_caddy_block = compose.split("  caddy:\n", 1)[1].split("\n  cloudflared:\n", 1)[0]
    origin_block = compose.split("  allure-report-origin:\n", 1)[1].split("\n  worker:\n", 1)[0]

    assert 'profiles: ["allure-reports"]' in origin_block
    assert "allure_reports:" in origin_block
    assert "allure_egress:" in origin_block
    assert "\n    ports:" not in origin_block
    assert "allure_reports:\n    internal: true" in compose
    assert "TUNNEL_TOKEN: ${ALLURE_CLOUDFLARED_TUNNEL_TOKEN:-}" in compose
    assert "ALLURE_PUBLIC_HOSTNAME: ${ALLURE_PUBLIC_HOSTNAME:-}" in public_caddy_block
    assert "ALLURE_BASIC_AUTH_HASH: ${ALLURE_BASIC_AUTH_HASH:-}" in public_caddy_block
    assert "allure_reports:" in public_caddy_block
    assert "basic_auth argon2id {" in public_caddy_block
    assert "reverse_proxy allure-report-origin:8080" in public_caddy_block
    assert "file_server" in caddy
    assert "browse" not in caddy
    assert 'Cache-Control "private, no-store"' in caddy
    assert 'respond @private "Not Found" 404' in caddy
    assert "/.publish.lock" in caddy
    assert "@unsupported not method GET HEAD" in caddy
    assert "/healthz" in caddy
    assert "ALLURE_REPORT_SSH_PRIVATE_KEY" in workflow
    assert "ALLURE_REPORT_SSH_KNOWN_HOSTS" in workflow
    assert 'default: "3"' in action
    assert "ALLURE_R2" not in workflow
    assert "allure-report-worker" not in workflow
    assert not (root / "deploy" / "allure-report-worker").exists()
    assert "testIgnore: ['**/mobile-ui-regression.spec.ts']" in cross_browser
    assert '--run-id "${GITHUB_RUN_ID}-attempt-${GITHUB_RUN_ATTEMPT}"' in workflow


def test_origin_rejects_noncanonical_state_paths() -> None:
    base = {
        "kind": "daily",
        "period": "2026-09-07",
        "run_id": "12345",
        "path": "daily/2026-09-07/12345/",
        "url": "https://allure.your-fitness-coach.ru/daily/2026-09-07/12345/",
        "created_at": "2026-09-07T01:00:00Z",
        "commit_sha": "a" * 40,
        "workflow_url": "https://github.com/example/run/1",
        "duration_seconds": 1,
        "bytes": 1,
        "counts": {"total": 1},
        "status": "passed",
        "expires_at": "2026-09-21",
    }
    invalid_path = dict(base, path="daily/2026-09-07/../")
    with pytest.raises(allure_report_origin.ReportOriginError, match="immutable path"):
        allure_report_origin._state_from_payload(
            {"schema_version": 1, "reports": [invalid_path], "cleanup_pending": []}
        )
    invalid_url = dict(base, url="https://example.invalid/report/")
    with pytest.raises(allure_report_origin.ReportOriginError, match="canonical"):
        allure_report_origin._state_from_payload(
            {"schema_version": 1, "reports": [invalid_url], "cleanup_pending": []}
        )
    with pytest.raises(allure_report_origin.ReportOriginError, match="immutable path"):
        allure_report_origin._state_from_payload(
            {
                "schema_version": 1,
                "reports": [],
                "cleanup_pending": ["daily/2026-09-07/../"],
            }
        )

    noncanonical_daily = dict(base, path="daily/20260907/12345/", period="20260907")
    with pytest.raises(allure_report_origin.ReportOriginError, match="immutable path"):
        allure_report_origin._state_from_payload(
            {"schema_version": 1, "reports": [noncanonical_daily], "cleanup_pending": []}
        )

    mismatched_timestamp = dict(base, expires_at="2026-09-22")
    with pytest.raises(allure_report_origin.ReportOriginError, match="expiry"):
        allure_report_origin._state_from_payload(
            {"schema_version": 1, "reports": [mismatched_timestamp], "cleanup_pending": []}
        )


def _origin_header(
    *,
    kind: str = "daily",
    period: str = "2026-09-07",
    run_id: str = "12345",
    created_at: str = "2026-09-07T01:00:00Z",
    report_bytes: int = 0,
    status: str = "complete",
) -> dict[str, object]:
    path = f"{kind}/{period}/{run_id}/"
    return {
        "run_kind": kind,
        "period": period,
        "run_id": run_id,
        "immutable_path": path,
        "url": f"https://allure.your-fitness-coach.ru/{path}",
        "report_status": status,
        "report_bytes": report_bytes,
        "created_at": created_at,
        "commit_sha": "a" * 40,
        "workflow_url": "https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/12345",
        "duration_seconds": 12.5,
        "counts": {
            "passed": 1,
            "failed": 0,
            "broken": 0,
            "skipped": 0,
            "unknown": 0,
            "total": 1,
        },
    }


def _origin_payload(header: dict[str, object], *, symlink: bool = False) -> io.BytesIO:
    output = io.BytesIO()
    output.write(allure_report_origin.PROTOCOL_MAGIC)
    output.write((json.dumps(header, sort_keys=True) + "\n").encode("utf-8"))
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        index = b"<!doctype html><title>synthetic</title>\n"
        index_info = tarfile.TarInfo("index.html")
        index_info.size = len(index)
        index_info.mode = 0o644
        archive.addfile(index_info, io.BytesIO(index))
        attachment = b"trace-safe\n"
        attachment_info = tarfile.TarInfo("data/attachment.txt")
        attachment_info.size = len(attachment)
        attachment_info.mode = 0o644
        archive.addfile(attachment_info, io.BytesIO(attachment))
        if symlink:
            link_info = tarfile.TarInfo("data/link")
            link_info.type = tarfile.SYMTYPE
            link_info.linkname = "../index.html"
            archive.addfile(link_info)
    output.seek(0)
    return output


def test_origin_publishes_atomically_and_retries_cleanup_queue(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(allure_report_origin, "_available_bytes", lambda path: 10 * 1024**3)
    root = tmp_path / "reports"
    report_bytes = len(b"<!doctype html><title>synthetic</title>\n") + len(b"trace-safe\n")
    old_header = _origin_header(
        period="2026-08-23",
        run_id="old",
        created_at="2026-08-23T01:00:00Z",
        report_bytes=report_bytes,
    )
    allure_report_origin.handle_request(
        _origin_payload(old_header),
        io.BytesIO(),
        root=root,
        now=datetime(2026, 8, 23, 2, 0, tzinfo=UTC),
    )
    header = _origin_header(report_bytes=report_bytes)
    original_delete = allure_report_origin._delete_report

    def fail_once(root: Path, relative: str) -> None:
        raise allure_report_origin.ReportOriginError("transient cleanup failure")

    monkeypatch.setattr(allure_report_origin, "_delete_report", fail_once)

    response_stream = io.BytesIO()
    response = allure_report_origin.handle_request(
        _origin_payload(header),
        response_stream,
        root=root,
        now=datetime(2026, 9, 7, 2, 0, tzinfo=UTC),
    )

    assert response["status"] == "cleanup-failed"
    assert response["idempotent"] is False
    assert old_header["immutable_path"] in response["cleanup_pending"]
    report_index = root / "daily" / "2026-09-07" / "12345" / "index.html"
    assert report_index.is_file()
    assert (root / "daily" / "latest" / "index.html").is_file()
    assert (root / "metadata" / "index.json").is_file()
    assert "12345" in (root / "index.html").read_text(encoding="utf-8")
    assert "12345" in (root / "daily" / "latest" / "index.html").read_text(encoding="utf-8")
    assert not (root / "daily" / "latest").is_symlink()
    assert (root / ".publish.lock").is_file()

    monkeypatch.setattr(allure_report_origin, "_delete_report", original_delete)
    response_stream = io.BytesIO()
    duplicate = allure_report_origin.handle_request(
        _origin_payload(header),
        response_stream,
        root=root,
        now=datetime(2026, 9, 7, 2, 1, tzinfo=UTC),
    )
    assert duplicate["status"] == "published"
    assert duplicate["idempotent"] is True
    assert report_index.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert not (root / "daily" / "2026-08-23" / "old").exists()


def test_origin_free_space_guard_counts_only_incoming_report(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "reports"
    report_bytes = len(b"<!doctype html><title>synthetic</title>\n") + len(b"trace-safe\n")
    monkeypatch.setattr(allure_report_origin, "_available_bytes", lambda path: 10 * 1024**3)
    old_header = _origin_header(
        period="2026-09-06",
        run_id="old",
        created_at="2026-09-06T01:00:00Z",
        report_bytes=report_bytes,
    )
    first = allure_report_origin.handle_request(
        _origin_payload(old_header),
        io.BytesIO(),
        root=root,
        now=datetime(2026, 9, 6, 2, 0, tzinfo=UTC),
    )
    assert first["status"] == "published"

    monkeypatch.setattr(
        allure_report_origin,
        "_available_bytes",
        lambda path: allure_report_origin.MIN_FREE_BYTES + report_bytes + 1,
    )
    current_header = _origin_header(report_bytes=report_bytes)
    second = allure_report_origin.handle_request(
        _origin_payload(current_header),
        io.BytesIO(),
        root=root,
        now=datetime(2026, 9, 7, 2, 0, tzinfo=UTC),
    )
    assert second["status"] == "published"


def test_origin_rejects_symlink_archive_members_and_unsupported_ssh_command(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(allure_report_origin, "_available_bytes", lambda path: 10 * 1024**3)
    header = _origin_header()
    header["report_bytes"] = len(b"<!doctype html><title>synthetic</title>\n") + len(
        b"trace-safe\n"
    )
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "cat /etc/passwd")
    with pytest.raises(allure_report_origin.ReportOriginError, match="SSH command"):
        allure_report_origin.handle_request(
            _origin_payload(header, symlink=True),
            io.BytesIO(),
            root=tmp_path / "reports",
        )
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND")
    with pytest.raises(allure_report_origin.ReportOriginError, match="non-regular"):
        allure_report_origin.handle_request(
            _origin_payload(header, symlink=True),
            io.BytesIO(),
            root=tmp_path / "reports",
        )


def test_origin_rolls_back_installed_report_before_metadata_commit(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(allure_report_origin, "_available_bytes", lambda path: 10 * 1024**3)
    root = tmp_path / "reports"
    report_bytes = len(b"<!doctype html><title>synthetic</title>\n") + len(b"trace-safe\n")
    header = _origin_header(report_bytes=report_bytes)
    original_atomic_write = allure_report_origin._atomic_write

    def fail_metadata(path: Path, content: bytes) -> None:
        if path == root / "metadata" / "index.json":
            raise allure_report_origin.ReportOriginError("metadata write failed")
        original_atomic_write(path, content)

    monkeypatch.setattr(allure_report_origin, "_atomic_write", fail_metadata)
    with pytest.raises(allure_report_origin.ReportOriginError, match="metadata write failed"):
        allure_report_origin.handle_request(
            _origin_payload(header),
            io.BytesIO(),
            root=root,
            now=datetime(2026, 9, 7, 2, 0, tzinfo=UTC),
        )

    assert not (root / "daily" / "2026-09-07" / "12345").exists()
    assert list((root / ".staging").iterdir()) == []


def test_publisher_requires_pinned_ssh_and_uses_forced_command(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ALLURE_REPORT_SSH_HOST", "app.your-fitness-coach.ru")
    monkeypatch.setenv("ALLURE_REPORT_SSH_PORT", "22")
    monkeypatch.setenv("ALLURE_REPORT_SSH_USER", "yfc-allure-publisher")
    monkeypatch.setenv("ALLURE_REPORT_SSH_PRIVATE_KEY", "-----BEGIN OPENSSH PRIVATE KEY-----\nkey")
    monkeypatch.setenv(
        "ALLURE_REPORT_SSH_KNOWN_HOSTS",
        "app.your-fitness-coach.ru ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA",
    )
    config = publish_allure_report._ssh_config()
    args = publish_allure_report._ssh_arguments(
        host=config[0],
        port=config[1],
        user=config[2],
        private_key_path=tmp_path / "id_ed25519",
        known_hosts_path=tmp_path / "known_hosts",
    )
    assert "StrictHostKeyChecking=yes" in args
    assert "GlobalKnownHostsFile=none" in args
    assert "UserKnownHostsFile=" + str(tmp_path / "known_hosts") in args
    assert "IdentityAgent=none" in args
    assert args[-1] == "yfc-allure-publish-v1"
    assert "StrictHostKeyChecking=no" not in args


def test_publisher_streams_header_and_archive_over_ssh(monkeypatch, tmp_path: Path) -> None:
    report_root = tmp_path / "report"
    report_root.mkdir()
    report = b"<!doctype html>\n"
    (report_root / "index.html").write_bytes(report)
    header = _origin_header(report_bytes=len(report))
    captured: dict[str, object] = {}

    class CaptureStream(io.BytesIO):
        def close(self) -> None:
            captured["payload"] = self.getvalue()

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = CaptureStream()
            self.returncode = 0

        def communicate(self) -> tuple[bytes, bytes]:
            return (
                (
                    json.dumps(
                        {
                            "status": "published",
                            "report_path": header["immutable_path"],
                            "url": header["url"],
                        }
                    )
                    + "\n"
                ).encode("utf-8"),
                b"",
            )

        def kill(self) -> None:
            self.returncode = -9

    process = FakeProcess()

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setattr(publish_allure_report.subprocess, "Popen", fake_popen)
    response = publish_allure_report._publish_over_ssh(
        report_root=report_root,
        header=header,
        host="app.your-fitness-coach.ru",
        port=22,
        user="yfc-allure-publisher",
        private_key="private-key",
        known_hosts="app.your-fitness-coach.ru ssh-ed25519 AAAA",
    )

    payload = io.BytesIO(captured["payload"])
    assert (
        payload.read(len(allure_report_origin.PROTOCOL_MAGIC))
        == allure_report_origin.PROTOCOL_MAGIC
    )
    received_header = json.loads(payload.readline())
    assert received_header == header
    with tarfile.open(fileobj=payload, mode="r:gz") as archive:
        assert archive.getnames() == ["index.html"]
    assert response["status"] == "published"
    assert captured["kwargs"]["shell"] is False
    assert captured["args"][-1] == "yfc-allure-publish-v1"


def test_report_period_uses_moscow_calendar_boundary_and_safe_paths() -> None:
    moment = datetime(2026, 9, 6, 21, 30, tzinfo=UTC)
    assert scheduled_regression.report_period("daily", timestamp=moment) == "2026-09-07"
    assert scheduled_regression.report_period("weekly", timestamp=moment) == "2026-W37"
    path = scheduled_regression.immutable_report_path("daily", period="2026-09-07", run_id="12345")
    assert path == "daily/2026-09-07/12345/"
    assert scheduled_regression.report_url(path).startswith(
        "https://allure.your-fitness-coach.ru/daily/"
    )
    with pytest.raises(scheduled_regression.ScheduledRegressionError):
        scheduled_regression.immutable_report_path("daily", period="../secret", run_id="123")


def test_aggregate_results_merges_current_run_and_adds_allowlisted_metadata(tmp_path: Path) -> None:
    metadata = _aggregate_metadata(tmp_path)

    assert metadata["status"] == "complete"
    assert metadata["result_files"] == len(scheduled_regression.report_bundles("daily"))
    assert metadata["present_suites"] == sorted(scheduled_regression.report_suites("daily"))
    expected_bundles = sorted(
        f"{suite}/{browser}" for suite, browser in scheduled_regression.report_bundles("daily")
    )
    assert metadata["expected_bundles"] == expected_bundles
    assert metadata["present_bundles"] == expected_bundles
    assert metadata["counts"] == {
        "passed": 11,
        "failed": 0,
        "broken": 0,
        "skipped": 0,
        "unknown": 0,
        "total": 11,
    }
    environment = (tmp_path / "merged" / "environment.properties").read_text(encoding="utf-8")
    assert "allure.report.kind=daily" in environment
    assert "DATABASE_URL" not in environment
    result_path = next((tmp_path / "merged").glob("*-result.json"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert {label["name"] for label in result["labels"]} >= {
        "feature",
        "suite",
        "tier",
        "run_kind",
    }
    assert result["parameters"][-1]["name"] == "run_kind"
    assert result["attachments"][0]["source"].startswith("frontend-")


def test_container_attachments_are_rewritten_only_to_copied_files() -> None:
    payload: dict[str, object] = {
        "befores": [{"attachments": [{"name": "trace", "source": "trace.txt"}]}]
    }
    allure_report._rewrite_attachment_sources(
        payload,
        target_names={"trace.txt": "suite__browser__trace.txt"},
    )
    assert payload["befores"][0]["attachments"][0]["source"] == "suite__browser__trace.txt"

    with pytest.raises(allure_report.AllureReportError, match="missing from bundle"):
        allure_report._rewrite_attachment_sources(
            {"attachments": [{"source": "environment.properties"}]},
            target_names={},
        )


def test_aggregate_results_marks_missing_suite_incomplete_with_visible_failure(
    tmp_path: Path,
) -> None:
    bundles = tmp_path / "bundles"
    _write_bundle(bundles, suite="python-tests", browser="python-shard-1")
    metadata_path = tmp_path / "metadata.json"
    metadata = allure_report.aggregate_results(
        bundle_root=bundles,
        output_root=tmp_path / "merged",
        metadata_path=metadata_path,
        run_kind="daily",
        tier="daily-regression",
        run_id="12345",
        commit_sha="b" * 40,
        branch="master",
        run_url="https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/12345",
        operating_system="ubuntu-latest",
        python_version="3.14",
        node_version="24",
        playwright_version="1.62.1",
        duration_seconds=1,
        created_at=datetime(2026, 9, 7, tzinfo=UTC),
    )

    assert metadata["status"] == "incomplete"
    assert any("frontend-checks" in issue for issue in metadata["issues"])
    integrity = list((tmp_path / "merged").glob("integrity-*-result.json"))
    assert integrity
    assert json.loads(integrity[0].read_text(encoding="utf-8"))["status"] == "failed"
    report_root = tmp_path / "report"
    report_root.mkdir()
    (report_root / "index.html").write_text("<!doctype html>", encoding="utf-8")
    with pytest.raises(allure_report.AllureReportError, match="incomplete"):
        allure_report.validate_report(
            report_root,
            metadata_path=metadata_path,
        )
    publication = publish_allure_report.publish(
        report_root=report_root,
        metadata_path=metadata_path,
        publication_path=tmp_path / "publication.json",
        dry_run=True,
    )
    assert publication["status"] == "dry-run"
    with pytest.raises(allure_report.AllureReportError, match="incomplete"):
        allure_report.finalize(
            metadata_path=metadata_path,
            publication_path=tmp_path / "publication.json",
        )


def test_report_validation_rejects_symlink_root(tmp_path: Path) -> None:
    actual = tmp_path / "actual-report"
    actual.mkdir()
    (actual / "index.html").write_text("<!doctype html>", encoding="utf-8")
    report_root = tmp_path / "report"
    try:
        report_root.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this development host")

    with pytest.raises(allure_report.AllureReportError, match="root cannot be a symlink"):
        allure_report.validate_report(report_root, metadata_path=tmp_path / "metadata.json")


def test_summary_ignores_skipped_weekly_only_jobs_for_daily_runs(tmp_path: Path) -> None:
    metadata = _aggregate_metadata(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    publication_path = tmp_path / "publication.json"
    _write_json(
        publication_path,
        {
            "status": "published",
            "report_path": metadata["immutable_path"],
            "url": scheduled_regression.report_url(str(metadata["immutable_path"])),
        },
    )
    summary_path = tmp_path / "summary.md"
    test_results = {
        "frontend": "success",
        "frontend-smoke": "success",
        "frontend-mobile-regression": "success",
        "python-tests": "success",
        "migrated-stack": "success",
        "frontend-mobile-regression-extended": "skipped",
        "frontend-cross-browser": "skipped",
    }

    allure_report.write_summary(
        metadata_path=metadata_path,
        publication_path=publication_path,
        test_results=test_results,
        destination=summary_path,
    )
    assert "Статус тестов: `passed`" in summary_path.read_text(encoding="utf-8")

    test_results["python-tests"] = "skipped"
    allure_report.write_summary(
        metadata_path=metadata_path,
        publication_path=publication_path,
        test_results=test_results,
        destination=summary_path,
    )
    assert "Статус тестов: `failed`" in summary_path.read_text(encoding="utf-8")


def test_sensitive_attachment_makes_report_incomplete(tmp_path: Path) -> None:
    metadata = _aggregate_metadata(tmp_path, attachment_text="DATABASE_URL=postgresql://secret")
    assert metadata["status"] == "incomplete"
    assert metadata["issues"]


def test_bundle_round_trip_is_encrypted_and_traversal_safe(tmp_path: Path, monkeypatch) -> None:
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed on this development host")
    source = tmp_path / "source"
    source.mkdir()
    (source / "result.json").write_text('{"status":"passed"}\n', encoding="utf-8")
    encrypted = tmp_path / "bundle.enc"
    monkeypatch.setenv("ALLURE_REPORT_ENCRYPTION_KEY", "k" * 48)
    manifest = allure_bundle.encrypt_bundle(
        source=source,
        output=encrypted,
        suite="python-tests",
        browser="shard-1",
    )
    assert encrypted.is_file()
    assert manifest["encrypted_bytes"] == encrypted.stat().st_size
    extracted = tmp_path / "extracted"
    opened = allure_bundle.decrypt_bundle(source=encrypted, output=extracted)
    assert opened["suite"] == "python-tests"
    assert (extracted / "result.json").read_text(encoding="utf-8") == '{"status":"passed"}\n'


def test_retention_keeps_daily_calendar_window_and_four_weeklies() -> None:
    now = date(2026, 9, 7)

    def entry(kind: str, created: date, index: int) -> dict[str, object]:
        period = created.isoformat() if kind == "daily" else created.strftime("%G-W%V")
        return {
            "kind": kind,
            "path": f"{kind}/{period}/{index}/",
            "created_at": datetime.combine(created, datetime.min.time(), tzinfo=UTC).isoformat(),
        }

    reports = [
        entry("daily", now - timedelta(days=13), 1),
        entry("daily", now - timedelta(days=14), 2),
        *[entry("weekly", now - timedelta(days=offset), offset) for offset in (1, 8, 15, 22, 29)],
    ]
    current = entry("daily", now, 3)
    retained, removed = allure_report_origin._retained_reports(
        reports,
        current=current,
        now=now,
    )

    assert sum(report["kind"] == "daily" for report in retained) == 2
    assert sum(report["kind"] == "weekly" for report in retained) == 4
    assert any(path.endswith("/2/") for path in removed)
    assert any(path.endswith("/29/") for path in removed)


def test_dry_run_publication_produces_canonical_url_without_storage_access(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.json"
    _write_json(
        metadata_path,
        {
            "status": "complete",
            "run_kind": "daily",
            "tier": "daily-regression",
            "run_id": "12345",
            "period": "2026-09-07",
            "immutable_path": "daily/2026-09-07/12345/",
            "created_at": "2026-09-07T01:00:00Z",
            "commit_sha": "c" * 40,
            "workflow_url": "https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/12345",
            "duration_seconds": 12,
            "counts": {"passed": 1, "failed": 0, "broken": 0, "skipped": 0},
        },
    )
    report_root = tmp_path / "report"
    report_root.mkdir()
    (report_root / "index.html").write_text("<!doctype html>", encoding="utf-8")
    publication_path = tmp_path / "publication.json"

    publication = publish_allure_report.publish(
        report_root=report_root,
        metadata_path=metadata_path,
        publication_path=publication_path,
        dry_run=True,
    )

    assert publication["status"] == "dry-run"
    assert publication["url"] == ("https://allure.your-fitness-coach.ru/daily/2026-09-07/12345/")
