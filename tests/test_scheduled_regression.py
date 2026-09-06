import json
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from scripts import allure_bundle, allure_report, publish_allure_report, scheduled_regression


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
    for suite in scheduled_regression.report_suites("daily"):
        _write_bundle(
            bundles,
            suite=suite,
            browser="synthetic",
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


def test_private_report_origin_uses_worker_and_private_r2_binding() -> None:
    root = Path(__file__).parents[1]
    config = (root / "deploy" / "allure-report-worker" / "wrangler.toml").read_text(
        encoding="utf-8"
    )
    source = (root / "deploy" / "allure-report-worker" / "src" / "index.js").read_text(
        encoding="utf-8"
    )

    assert "workers_dev = false" in config
    assert 'binding = "REPORTS"' in config
    assert "custom_domain = true" in config
    assert "allure.your-fitness-coach.ru" in config
    assert "r2.dev" not in source
    assert '"cache-control", "private, no-store"' in source
    assert "index.html" in source


def test_remote_report_state_rejects_noncanonical_paths_and_urls() -> None:
    with pytest.raises(publish_allure_report.PublicationError, match="immutable path"):
        publish_allure_report._state_from_payload(
            {
                "schema_version": 1,
                "reports": [
                    {
                        "kind": "daily",
                        "period": "2026-09-07",
                        "run_id": "12345",
                        "path": "daily/2026-09-07/../",
                        "url": "https://allure.your-fitness-coach.ru/daily/2026-09-07/../",
                        "created_at": "2026-09-07T01:00:00Z",
                    }
                ],
                "cleanup_pending": [],
            }
        )
    with pytest.raises(publish_allure_report.PublicationError, match="canonical"):
        publish_allure_report._state_from_payload(
            {
                "schema_version": 1,
                "reports": [
                    {
                        "kind": "daily",
                        "period": "2026-09-07",
                        "run_id": "12345",
                        "path": "daily/2026-09-07/12345/",
                        "url": "https://example.invalid/report/",
                        "created_at": "2026-09-07T01:00:00Z",
                    }
                ],
                "cleanup_pending": [],
            }
        )
    with pytest.raises(publish_allure_report.PublicationError, match="cleanup queue"):
        publish_allure_report._state_from_payload(
            {
                "schema_version": 1,
                "reports": [],
                "cleanup_pending": ["daily/2026-09-07/../"],
            }
        )


def test_missing_remote_report_index_fails_closed_for_nonempty_storage(monkeypatch) -> None:
    monkeypatch.setattr(
        publish_allure_report.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Completed",
            (),
            {"returncode": 1, "stderr": "404 Not Found", "stdout": ""},
        )(),
    )
    monkeypatch.setattr(
        publish_allure_report,
        "_remote_prefix_exists",
        lambda **kwargs: True,
    )

    with pytest.raises(publish_allure_report.PublicationError, match="storage is not empty"):
        publish_allure_report._read_remote_state(
            endpoint="https://example.r2.cloudflarestorage.com",
            bucket="reports",
            env={},
        )


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
    assert metadata["result_files"] == len(scheduled_regression.report_suites("daily"))
    assert metadata["present_suites"] == sorted(scheduled_regression.report_suites("daily"))
    assert metadata["counts"] == {
        "passed": 5,
        "failed": 0,
        "broken": 0,
        "skipped": 0,
        "unknown": 0,
        "total": 5,
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
    _write_bundle(bundles, suite="python-tests", browser="shard-1")
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
        return {
            "kind": kind,
            "path": f"{kind}/{created.isoformat()}/{index}/",
            "created_at": datetime.combine(created, datetime.min.time(), tzinfo=UTC).isoformat(),
        }

    reports = [
        entry("daily", now - timedelta(days=13), 1),
        entry("daily", now - timedelta(days=14), 2),
        *[entry("weekly", now - timedelta(days=offset), offset) for offset in (1, 8, 15, 22, 29)],
    ]
    current = entry("daily", now, 3)
    retained, removed = publish_allure_report._retained_reports(
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


def test_publication_does_not_rewrite_an_existing_immutable_report(
    tmp_path: Path, monkeypatch
) -> None:
    metadata = _aggregate_metadata(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    report_root = tmp_path / "report"
    report_root.mkdir()
    (report_root / "index.html").write_text("<!doctype html>", encoding="utf-8")
    report_bytes = (report_root / "index.html").stat().st_size
    existing = publish_allure_report._entry_from_metadata(metadata, report_bytes=report_bytes)
    upload_calls: list[Path] = []

    monkeypatch.setattr(
        publish_allure_report,
        "_validate_storage_config",
        lambda: ("https://example.r2.cloudflarestorage.com", "reports", "key", "secret"),
    )
    monkeypatch.setattr(
        publish_allure_report,
        "_read_remote_state",
        lambda **kwargs: ([existing], []),
    )
    monkeypatch.setattr(
        publish_allure_report,
        "_remote_prefix_exists",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        publish_allure_report,
        "_upload_report",
        lambda root, **kwargs: upload_calls.append(root),
    )
    monkeypatch.setattr(publish_allure_report, "_upload_file", lambda *args, **kwargs: None)
    monkeypatch.setattr(publish_allure_report, "_delete_prefix", lambda *args, **kwargs: None)

    publication = publish_allure_report.publish(
        report_root=report_root,
        metadata_path=metadata_path,
        publication_path=tmp_path / "publication.json",
        now=datetime(2026, 9, 7, 1, 1, tzinfo=UTC),
    )

    assert publication["status"] == "published"
    assert upload_calls == []
