"""Bounded, source-free Hermes pipeline health and alert evidence."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from discovery_runner import (
    DiscoveryError,
    _atomic_write_json,
    _exclusive_lock,
    _load_state,
)

HEALTH_SCHEMA_VERSION = "hermes-pipeline-health-v1"
ALERT_THRESHOLDS = {
    "consecutive_discovery_failures": 3,
    "consecutive_drain_failures": 3,
    "pending_jobs": 100,
    "oldest_pending_age_seconds": 172_800,
    "provider_rate_limited": 5,
    "image_unavailable": 3,
    "intake_schema_failures": 3,
    "terminal": 3,
    "transient": 3,
    "source_errors": 3,
}
HEALTH_COUNTERS = (
    "relevance_rejected",
    "accepted",
    "duplicate",
    "terminal",
    "transient",
    "image_unavailable",
    "intake_schema_failures",
    "provider_rate_limited",
    "quarantined",
    "source_errors",
)
DRAIN_ALERT_COUNTERS = (
    "provider_rate_limited",
    "image_unavailable",
    "intake_schema_failures",
    "terminal",
    "transient",
)
PUBLIC_COUNTER_ALIASES = {
    "accepted": "accepted_count",
    "duplicate": "duplicate_count",
    "terminal": "terminal_failure_count",
    "transient": "transient_failure_count",
    "image_unavailable": "image_failure_count",
    "intake_schema_failures": "intake_schema_failure_count",
    "provider_rate_limited": "provider_rate_limit_count",
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _pending_snapshot(outbox_dir: Path) -> tuple[int, int]:
    files = [path for path in outbox_dir.glob("*.json") if path.is_file()]
    if not files:
        return 0, 0
    oldest = min(path.stat().st_mtime for path in files)
    return len(files), max(0, round(time.time() - oldest))


def ensure_health(state: dict[str, Any]) -> dict[str, Any]:
    health = state.setdefault("health", {})
    if not isinstance(health, dict):
        health = {}
        state["health"] = health
    health.setdefault("schema_version", HEALTH_SCHEMA_VERSION)
    health.setdefault("last_successful_discovery_at", None)
    health.setdefault("last_successful_drain_at", None)
    health.setdefault("last_discovery_attempt_at", None)
    health.setdefault("last_drain_attempt_at", None)
    health.setdefault("consecutive_discovery_failures", 0)
    health.setdefault("consecutive_drain_failures", 0)
    health.setdefault("pending_jobs", 0)
    health.setdefault("oldest_pending_age_seconds", 0)
    health.setdefault("last_source_error_count", 0)
    last_drain_error_counts = health.setdefault("last_drain_error_counts", {})
    if not isinstance(last_drain_error_counts, dict):
        last_drain_error_counts = {}
        health["last_drain_error_counts"] = last_drain_error_counts
    for name in DRAIN_ALERT_COUNTERS:
        value = last_drain_error_counts.get(name, 0)
        last_drain_error_counts[name] = value if isinstance(value, int) and value >= 0 else 0
    counters = health.setdefault("counters", {})
    if not isinstance(counters, dict):
        counters = {}
        health["counters"] = counters
    for name in HEALTH_COUNTERS:
        value = counters.get(name, 0)
        counters[name] = value if isinstance(value, int) and value >= 0 else 0
    health["alert_thresholds"] = dict(ALERT_THRESHOLDS)
    _sync_public_fields(health)
    return health


def _sync_public_fields(health: dict[str, Any]) -> None:
    counters = health["counters"]
    health["outbox_pending_count"] = int(health.get("pending_jobs", 0))
    for internal, public in PUBLIC_COUNTER_ALIASES.items():
        value = int(counters.get(internal, 0))
        health[public] = value
        counters[public] = value


def _active_alerts(health: Mapping[str, Any]) -> list[str]:
    alerts: list[str] = []
    if (
        health.get("consecutive_discovery_failures", 0)
        >= ALERT_THRESHOLDS["consecutive_discovery_failures"]
    ):
        alerts.append("discovery_failures")
    if (
        health.get("consecutive_drain_failures", 0)
        >= ALERT_THRESHOLDS["consecutive_drain_failures"]
    ):
        alerts.append("drain_failures")
    if health.get("pending_jobs", 0) >= ALERT_THRESHOLDS["pending_jobs"]:
        alerts.append("outbox_backlog")
    if (
        health.get("oldest_pending_age_seconds", 0)
        >= ALERT_THRESHOLDS["oldest_pending_age_seconds"]
    ):
        alerts.append("oldest_pending_job")
    last_drain_error_counts = health.get("last_drain_error_counts", {})
    if (
        isinstance(last_drain_error_counts, Mapping)
        and last_drain_error_counts.get("provider_rate_limited", 0)
        >= ALERT_THRESHOLDS["provider_rate_limited"]
    ):
        alerts.append("provider_rate_limited")
    if isinstance(last_drain_error_counts, Mapping):
        for counter, alert in (
            ("image_unavailable", "image_failures"),
            ("intake_schema_failures", "intake_schema_failures"),
            ("terminal", "terminal_failures"),
            ("transient", "transient_failures"),
        ):
            if last_drain_error_counts.get(counter, 0) >= ALERT_THRESHOLDS[counter]:
                alerts.append(alert)
    if health.get("last_source_error_count", 0) >= ALERT_THRESHOLDS["source_errors"]:
        alerts.append("source_errors")
    return alerts


def update_health(
    state: dict[str, Any],
    *,
    stage: str,
    status: str,
    counters: Mapping[str, int] | None = None,
    pending_jobs: int = 0,
    oldest_pending_age_seconds: int = 0,
) -> dict[str, Any]:
    if stage not in {"discovery", "drain"}:
        raise DiscoveryError("health_stage_invalid")
    health = ensure_health(state)
    now = _now()
    attempt_key = f"last_{stage}_attempt_at"
    success_key = f"last_successful_{'discovery' if stage == 'discovery' else 'drain'}_at"
    failure_key = f"consecutive_{stage}_failures"
    health[attempt_key] = now
    if status == "completed":
        health[success_key] = now
        health[failure_key] = 0
    else:
        health[failure_key] = int(health.get(failure_key, 0)) + 1
    health["pending_jobs"] = max(0, int(pending_jobs))
    health["oldest_pending_age_seconds"] = max(0, int(oldest_pending_age_seconds))
    if stage == "discovery":
        current_source_errors = (counters or {}).get("source_errors", 0)
        health["last_source_error_count"] = (
            current_source_errors
            if isinstance(current_source_errors, int) and current_source_errors >= 0
            else 0
        )
    else:
        last_drain_error_counts = health["last_drain_error_counts"]
        for name in DRAIN_ALERT_COUNTERS:
            amount = (counters or {}).get(name, 0)
            last_drain_error_counts[name] = amount if isinstance(amount, int) and amount >= 0 else 0
    totals = health["counters"]
    for name, amount in (counters or {}).items():
        if name in HEALTH_COUNTERS and isinstance(amount, int) and amount >= 0:
            totals[name] = int(totals.get(name, 0)) + amount
    _sync_public_fields(health)
    health["active_alerts"] = _active_alerts(health)
    health["updated_at"] = now
    return health


def record_health(
    state_dir: Path,
    outbox_dir: Path,
    *,
    stage: str,
    status: str,
    counters: Mapping[str, int] | None = None,
    stale_seconds: float = 900,
) -> dict[str, Any]:
    state_dir.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(state_dir / ".state.lock", stale_seconds=stale_seconds):
        state_path = state_dir / "state.json"
        state = _load_state(state_path)
        pending, oldest = _pending_snapshot(outbox_dir)
        health = update_health(
            state,
            stage=stage,
            status=status,
            counters=counters,
            pending_jobs=pending,
            oldest_pending_age_seconds=oldest,
        )
        _atomic_write_json(state_path, state)
        _atomic_write_json(
            state_dir / "health-alerts.json",
            {
                "schema_version": HEALTH_SCHEMA_VERSION,
                "updated_at": health["updated_at"],
                "active_alerts": health["active_alerts"],
                "thresholds": health["alert_thresholds"],
                "secrets_logged": False,
            },
        )
        return dict(health)


def snapshot(state_dir: Path, outbox_dir: Path) -> dict[str, Any]:
    state = _load_state(state_dir / "state.json")
    health = dict(ensure_health(state))
    pending, oldest = _pending_snapshot(outbox_dir)
    health["pending_jobs"] = pending
    health["oldest_pending_age_seconds"] = oldest
    _sync_public_fields(health)
    health["active_alerts"] = _active_alerts(health)
    return {
        "status": "attention" if health.get("active_alerts") else "healthy",
        "health": health,
        "pending_jobs": pending,
        "oldest_pending_age_seconds": oldest,
        "secrets_logged": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("health", "alert"))
    parser.add_argument("--state-dir", type=Path, default=Path("/var/lib/hermes"))
    parser.add_argument("--outbox-dir", type=Path, default=Path("/var/lib/hermes/outbox"))
    args = parser.parse_args(argv)
    try:
        document = snapshot(args.state_dir.resolve(), args.outbox_dir.resolve())
    except (DiscoveryError, OSError, ValueError):
        print(json.dumps({"error": "hermes_health_unavailable", "secrets_logged": False}))
        return 1
    print(json.dumps(document, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
