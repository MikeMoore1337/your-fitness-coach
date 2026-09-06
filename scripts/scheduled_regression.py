"""Shared contract for scheduled regression runs and private reports."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Final
from zoneinfo import ZoneInfo

DAILY_SCHEDULE_CRON: Final = "17 2 * * *"
WEEKLY_SCHEDULE_CRON: Final = "43 3 * * 0"
REPORT_BASE_URL: Final = "https://allure.your-fitness-coach.ru"
REPORT_TIMEZONE: Final = "Europe/Moscow"
DAILY_RETENTION_DAYS: Final = 14
WEEKLY_RETENTION_COUNT: Final = 4
WEEKLY_RETENTION_DAYS: Final = 35
RAW_RESULTS_RETENTION_DAYS: Final = 3
MAX_BUNDLE_BYTES: Final = 50 * 1024 * 1024
MAX_REPORT_BYTES: Final = 100 * 1024 * 1024

RUN_KINDS: tuple[str, ...] = ("daily", "weekly")
PROFILE_BY_RUN_KIND: Mapping[str, str] = {
    "daily": "daily-regression",
    "weekly": "weekly-exhaustive",
}
REPORT_SUITES_BY_RUN_KIND: Mapping[str, tuple[str, ...]] = {
    "daily": (
        "frontend-checks",
        "frontend-e2e",
        "frontend-mobile-regression",
        "python-tests",
        "migrated-stack",
    ),
    "weekly": (
        "frontend-checks",
        "frontend-e2e",
        "frontend-mobile-regression",
        "frontend-mobile-regression-extended",
        "frontend-cross-browser",
        "python-tests",
        "migrated-stack",
    ),
}
REPORT_JOB_BY_SUITE: Mapping[str, str] = {
    "frontend-checks": "frontend",
    "frontend-e2e": "frontend-smoke",
    "frontend-mobile-regression": "frontend-mobile-regression",
    "frontend-mobile-regression-extended": "frontend-mobile-regression-extended",
    "frontend-cross-browser": "frontend-cross-browser",
    "python-tests": "python-tests",
    "migrated-stack": "migrated-stack",
}
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ScheduledRegressionError(ValueError):
    """The scheduled regression contract cannot be resolved safely."""


def normalize_run_kind(value: str) -> str:
    candidate = value.strip().lower()
    if candidate not in RUN_KINDS:
        raise ScheduledRegressionError(
            f"Unsupported run kind {value!r}; expected one of {', '.join(RUN_KINDS)}"
        )
    return candidate


def resolve_run_kind(
    event: str,
    *,
    run_kind: str | None = None,
    schedule_cron: str | None = None,
) -> str:
    """Resolve one explicit Daily/Weekly lane for a GitHub event."""

    if event == "schedule":
        if run_kind:
            raise ScheduledRegressionError("schedule events must derive run kind from their cron")
        if schedule_cron == DAILY_SCHEDULE_CRON:
            return "daily"
        if schedule_cron == WEEKLY_SCHEDULE_CRON:
            return "weekly"
        raise ScheduledRegressionError(
            "Unknown schedule cron; refusing to run an unclassified regression"
        )
    if event == "workflow_dispatch":
        if not run_kind:
            raise ScheduledRegressionError("workflow_dispatch requires run_kind=daily|weekly")
        return normalize_run_kind(run_kind)
    raise ScheduledRegressionError(f"Run kind is not defined for event {event!r}")


def profile_for_run_kind(run_kind: str) -> str:
    normalized = normalize_run_kind(run_kind)
    return PROFILE_BY_RUN_KIND[normalized]


def report_suites(run_kind: str) -> tuple[str, ...]:
    normalized = normalize_run_kind(run_kind)
    return REPORT_SUITES_BY_RUN_KIND[normalized]


def report_jobs(run_kind: str) -> tuple[str, ...]:
    return tuple(REPORT_JOB_BY_SUITE[suite] for suite in report_suites(run_kind))


def _safe_segment(value: str, *, field: str) -> str:
    if not _SAFE_SEGMENT.fullmatch(value):
        raise ScheduledRegressionError(f"Unsafe {field}: {value!r}")
    return value


def report_period(run_kind: str, *, timestamp: datetime | None = None) -> str:
    """Return the Europe/Moscow calendar period used by immutable report paths."""

    normalized = normalize_run_kind(run_kind)
    moment = timestamp or datetime.now(UTC)
    if moment.tzinfo is None:
        raise ScheduledRegressionError("timestamp must be timezone-aware")
    local = moment.astimezone(ZoneInfo(REPORT_TIMEZONE))
    if normalized == "daily":
        return local.strftime("%Y-%m-%d")
    return local.strftime("%G-W%V")


def immutable_report_path(run_kind: str, *, period: str, run_id: str) -> str:
    normalized = normalize_run_kind(run_kind)
    safe_period = _safe_segment(period, field="period")
    safe_run_id = _safe_segment(run_id, field="run id")
    return str(PurePosixPath(normalized, safe_period, safe_run_id)) + "/"


def latest_report_path(run_kind: str) -> str:
    return str(PurePosixPath(normalize_run_kind(run_kind), "latest")) + "/"


def report_url(path: str, *, base_url: str = REPORT_BASE_URL) -> str:
    """Join a validated relative report path to the canonical host."""

    normalized_base = base_url.rstrip("/")
    normalized_path = path.strip("/")
    if not normalized_path or any(part in {".", ".."} for part in normalized_path.split("/")):
        raise ScheduledRegressionError("Report URL path must be a non-empty relative path")
    return f"{normalized_base}/{normalized_path}/"


def contract_payload() -> dict[str, object]:
    return {
        "daily_schedule_cron": DAILY_SCHEDULE_CRON,
        "weekly_schedule_cron": WEEKLY_SCHEDULE_CRON,
        "timezone": REPORT_TIMEZONE,
        "profiles": dict(PROFILE_BY_RUN_KIND),
        "report_suites": {kind: list(report_suites(kind)) for kind in RUN_KINDS},
        "retention": {
            "daily_html_days": DAILY_RETENTION_DAYS,
            "weekly_report_count": WEEKLY_RETENTION_COUNT,
            "weekly_html_days": WEEKLY_RETENTION_DAYS,
            "raw_results_days": RAW_RESULTS_RETENTION_DAYS,
        },
        "limits": {
            "encrypted_bundle_bytes": MAX_BUNDLE_BYTES,
            "report_bytes": MAX_REPORT_BYTES,
        },
        "report_base_url": REPORT_BASE_URL,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("contract")
    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--event", required=True)
    resolve.add_argument("--run-kind")
    resolve.add_argument("--schedule-cron")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "contract":
            print(json.dumps(contract_payload(), ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "resolve":
            print(
                json.dumps(
                    {
                        "run_kind": resolve_run_kind(
                            args.event,
                            run_kind=args.run_kind,
                            schedule_cron=args.schedule_cron,
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        raise AssertionError(f"Unhandled command: {args.command}")
    except ScheduledRegressionError as error:
        print(f"scheduled regression contract error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
