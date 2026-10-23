"""No-network evidence checks for the read-only YFC polling observer."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from bot.fitminiapp_bot.polling_health import write_polling_health


def test_polling_success_is_bounded_atomic_and_contains_no_ids(tmp_path: Path) -> None:
    stamp = datetime(2026, 10, 23, 18, 20, tzinfo=UTC)
    path = tmp_path / "polling.json"
    assert write_polling_health(str(path), "healthy", "getupdates_success", now=stamp)
    value = json.loads(path.read_text())
    assert value == {
        "schema": 1,
        "source_host": "yfc",
        "component": "telegram_polling",
        "state": "healthy",
        "evidence": "getupdates_success",
        "observed_at": "2026-10-23T18:20:00Z",
    }
    assert path.stat().st_mode & 0o777 == 0o640
    assert len(path.read_bytes()) < 512
    assert list(tmp_path.iterdir()) == [path]


def test_polling_error_and_exit_override_prior_success(tmp_path: Path) -> None:
    path = tmp_path / "polling.json"
    time = datetime.now(UTC)
    assert write_polling_health(str(path), "healthy", "getupdates_success", now=time)
    assert write_polling_health(str(path), "unhealthy", "getupdates_error", now=time)
    assert json.loads(path.read_text())["state"] == "unhealthy"
    assert write_polling_health(str(path), "unknown", "polling_stopped", now=time)
    assert json.loads(path.read_text())["state"] == "unknown"


def test_disabled_or_denied_does_not_affect_bot(tmp_path: Path) -> None:
    assert not write_polling_health("", "healthy", "getupdates_success")
    assert not write_polling_health(
        str(tmp_path / "missing" / "polling.json"), "healthy", "getupdates_success"
    )
    target = tmp_path / "polling.json"
    target.symlink_to(tmp_path / "outside")
    assert not write_polling_health(str(target), "healthy", "getupdates_success")


@pytest.mark.parametrize(
    "state,evidence",
    [
        ("yes", "getupdates_success"),
        ("healthy", "fake_event"),
    ],
)
def test_nonallowlisted_state_rejected(tmp_path: Path, state: str, evidence: str) -> None:
    with pytest.raises(ValueError):
        write_polling_health(str(tmp_path / "polling.json"), state, evidence)


def test_naive_timestamp_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timezone_required"):
        write_polling_health(
            str(tmp_path / "polling.json"),
            "healthy",
            "getupdates_success",
            now=datetime(2026, 10, 23),
        )


def test_health_writer_never_leaks_telegram_secret(tmp_path: Path) -> None:
    path = tmp_path / "polling.json"
    secret = "123456:private-bot-token"
    assert write_polling_health(str(path), "healthy", "getupdates_success")
    assert secret not in path.read_text()
