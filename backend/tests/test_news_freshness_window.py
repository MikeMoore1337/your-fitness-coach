from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fitminiapp_api.services.news_freshness import (
    FRESHNESS_WINDOW_DAYS,
    is_fresh_publication,
)


def test_freshness_window_accepts_exactly_60_days() -> None:
    now = datetime(2026, 8, 30, 12, 0, 0)
    lower_bound = now - timedelta(days=FRESHNESS_WINDOW_DAYS)

    assert is_fresh_publication(lower_bound, now=now)
    assert is_fresh_publication(datetime(2026, 7, 31, 23, 59, 59), now=now)
    assert is_fresh_publication(datetime(2026, 8, 1, 0, 0, 0), now=now)
    assert is_fresh_publication(now, now=now)
    assert not is_fresh_publication(lower_bound - timedelta(microseconds=1), now=now)


def test_freshness_window_rejects_older_missing_and_future_dates() -> None:
    now = datetime(2026, 8, 30, 12, 0, 0)

    assert not is_fresh_publication(now - timedelta(days=61), now=now)
    assert not is_fresh_publication(None, now=now)
    assert not is_fresh_publication(datetime(2026, 8, 30, 12, 0, 1), now=now)


def test_freshness_window_handles_year_boundary_and_timezone() -> None:
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    lower_bound = now - timedelta(days=FRESHNESS_WINDOW_DAYS)

    assert is_fresh_publication(lower_bound, now=now)
    assert is_fresh_publication(datetime(2025, 12, 1, 0, 0, 0, tzinfo=UTC), now=now)
    assert not is_fresh_publication(lower_bound - timedelta(seconds=1), now=now)
