from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

FRESHNESS_WINDOW_DAYS = 60
FRESHNESS_WINDOW = timedelta(days=FRESHNESS_WINDOW_DAYS)


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def parse_source_published_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc_naive(parsed)


def is_fresh_publication(
    published_at: datetime | None,
    *,
    now: datetime,
) -> bool:
    """Return whether a source date is inside the inclusive 60-day freshness window.

    Naive datetimes are the existing UTC-naive storage format. Future-dated and missing
    source dates fail closed.
    """
    if published_at is None:
        return False
    current = _as_utc_naive(now)
    published = _as_utc_naive(published_at)
    return current - FRESHNESS_WINDOW <= published <= current


def source_metadata_is_fresh(
    metadata: Mapping[str, object],
    *,
    now: datetime,
) -> bool:
    return is_fresh_publication(
        parse_source_published_at(metadata.get("source_published_at")),
        now=now,
    )


def is_current_month_publication(
    published_at: datetime | None,
    *,
    now: datetime,
) -> bool:
    """Backward-compatible name for the 60-day freshness check."""

    return is_fresh_publication(published_at, now=now)


def source_metadata_is_current_month(
    metadata: Mapping[str, object],
    *,
    now: datetime,
) -> bool:
    """Backward-compatible name for :func:`source_metadata_is_fresh`."""

    return source_metadata_is_fresh(metadata, now=now)
