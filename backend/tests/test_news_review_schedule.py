from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fitminiapp_api.services.news_review_schedule import (
    NEWS_REVIEW_BATCH_SIZE,
    current_news_review_slot,
)


def test_review_schedule_exposes_three_moscow_windows_and_batch_size() -> None:
    assert NEWS_REVIEW_BATCH_SIZE == 5

    first = current_news_review_slot(datetime(2026, 9, 8, 5, 0, 0, tzinfo=UTC))
    second = current_news_review_slot(datetime(2026, 9, 8, 10, 14, 59, tzinfo=UTC))
    third = current_news_review_slot(datetime(2026, 9, 8, 15, 0, 0, tzinfo=UTC))

    assert first is not None
    assert first.key == "2026-09-08T08:00:00+03:00"
    assert second is not None
    assert second.key == "2026-09-08T13:00:00+03:00"
    assert third is not None
    assert third.key == "2026-09-08T18:00:00+03:00"


def test_review_schedule_has_a_bounded_grace_window() -> None:
    start = datetime(2026, 9, 8, 5, 0, 0, tzinfo=UTC)

    assert current_news_review_slot(start) is not None
    assert current_news_review_slot(start + timedelta(minutes=14, seconds=59)) is not None
    assert current_news_review_slot(start + timedelta(minutes=15)) is None
    assert current_news_review_slot(start - timedelta(seconds=1)) is None


def test_review_schedule_treats_naive_datetimes_as_utc_storage_values() -> None:
    slot = current_news_review_slot(datetime(2026, 9, 8, 5, 5, 0))

    assert slot is not None
    assert slot.local_start.isoformat() == "2026-09-08T08:00:00+03:00"
