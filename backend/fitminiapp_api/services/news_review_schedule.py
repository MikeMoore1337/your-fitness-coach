from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NEWS_REVIEW_TIMEZONE = ZoneInfo("Europe/Moscow")
NEWS_REVIEW_BATCH_SIZE = 5
NEWS_REVIEW_SLOT_WINDOW = timedelta(minutes=15)
NEWS_REVIEW_SLOT_STARTS = (time(hour=8), time(hour=13), time(hour=18))


@dataclass(frozen=True)
class NewsReviewSlot:
    key: str
    local_start: datetime
    local_end: datetime


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _local_slot_start(day: date, slot_time: time) -> datetime:
    return datetime.combine(day, slot_time, tzinfo=NEWS_REVIEW_TIMEZONE)


def current_news_review_slot(now: datetime) -> NewsReviewSlot | None:
    """Return the active 15-minute owner-review dispatch window, if any."""

    local_now = _as_utc_aware(now).astimezone(NEWS_REVIEW_TIMEZONE)
    for slot_time in NEWS_REVIEW_SLOT_STARTS:
        local_start = _local_slot_start(local_now.date(), slot_time)
        local_end = local_start + NEWS_REVIEW_SLOT_WINDOW
        if local_start <= local_now < local_end:
            return NewsReviewSlot(
                key=local_start.isoformat(),
                local_start=local_start,
                local_end=local_end,
            )
    return None
