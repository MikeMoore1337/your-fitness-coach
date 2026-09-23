from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).parents[1]
DISCOVERY_ROOT = WORKSPACE / "deploy" / "hermes-discovery"
sys.path.insert(0, str(DISCOVERY_ROOT))

import hermes_health  # noqa: E402


def test_health_records_bounded_counters_and_recomputes_backlog_alert(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    outbox_dir = state_dir / "outbox"
    outbox_dir.mkdir(parents=True)
    for index in range(100):
        (outbox_dir / f"{index:064x}.json").write_text("{}\n", encoding="utf-8")

    health = hermes_health.record_health(
        state_dir,
        outbox_dir,
        stage="drain",
        status="failed",
        counters={"provider_rate_limited": 5, "not_a_counter": 999},
    )

    assert health["pending_jobs"] == 100
    assert health["outbox_pending_count"] == 100
    assert health["counters"]["provider_rate_limited"] == 5
    assert health["provider_rate_limit_count"] == 5
    assert health["accepted_count"] == 0
    assert health["counters"]["accepted_count"] == 0
    assert "not_a_counter" not in health["counters"]
    assert set(health["active_alerts"]) == {"outbox_backlog", "provider_rate_limited"}
    snapshot = hermes_health.snapshot(state_dir, outbox_dir)
    assert snapshot["status"] == "attention"
    assert "outbox_backlog" in snapshot["health"]["active_alerts"]

    recovered = hermes_health.record_health(
        state_dir,
        outbox_dir,
        stage="drain",
        status="completed",
        counters={},
    )
    assert recovered["counters"]["provider_rate_limited"] == 5
    assert recovered["last_drain_error_counts"]["provider_rate_limited"] == 0
    assert "provider_rate_limited" not in recovered["active_alerts"]
    assert "outbox_backlog" in recovered["active_alerts"]