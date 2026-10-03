from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import (
    is_valid_timezone,
    local_naive_to_utc_naive,
    utc_naive_to_timezone_naive,
)
from fitminiapp_api.models.lifecycle_milestone import (
    LIFECYCLE_MILESTONE_TYPES,
    LifecycleMilestone,
)
from fitminiapp_api.models.user import User

LIFECYCLE_MILESTONE_SCHEMA_VERSION = 1
MEANINGFUL_MILESTONE_TYPES = frozenset(
    {
        "program_activated",
        "workout_started",
        "workout_completed",
        "nutrition_entry_confirmed",
        "weekly_review_completed",
        "recovery_action_confirmed",
        "progress_next_action_completed",
    }
)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_utc_naive(value: datetime | None) -> datetime:
    if value is None:
        return utcnow()
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _milestone_timezone_name(user: User) -> str:
    profile_timezone = getattr(getattr(user, "profile", None), "timezone", None)
    return profile_timezone if profile_timezone and is_valid_timezone(profile_timezone) else "UTC"


def _day_boundary_utc(value: datetime, user: User) -> datetime:
    timezone_name = _milestone_timezone_name(user)
    local_value = utc_naive_to_timezone_naive(value, timezone_name)
    return local_naive_to_utc_naive(
        datetime.combine(local_value.date(), time.min),
        timezone_name,
    )


def record_lifecycle_milestone(
    db: Session,
    user: User,
    milestone_type: str,
    *,
    occurred_at: datetime | None = None,
    day_scope: bool = False,
    account_scope: bool = False,
) -> bool:
    """Record one confirmed outcome without accepting client analytics payloads.

    ``occurred_at`` is stored as UTC-naive, matching the existing UTC timestamp
    conventions for durable operational records. Daily evidence is normalized to
    the user's local-day boundary so retries from Web and TMA share one row.
    """

    if milestone_type not in LIFECYCLE_MILESTONE_TYPES:
        raise ValueError("Unsupported lifecycle milestone")
    if getattr(user, "is_coach", False) or getattr(user, "is_admin", False):
        return False

    normalized_at = _as_utc_naive(occurred_at)
    if day_scope:
        normalized_at = _day_boundary_utc(normalized_at, user)

    query = db.query(LifecycleMilestone).filter(
        LifecycleMilestone.user_id == user.id,
        LifecycleMilestone.milestone_type == milestone_type,
    )
    if account_scope:
        if query.first() is not None:
            return False
    else:
        if query.filter(LifecycleMilestone.occurred_at == normalized_at).first() is not None:
            return False

    row = LifecycleMilestone(
        user_id=user.id,
        milestone_type=milestone_type,
        schema_version=LIFECYCLE_MILESTONE_SCHEMA_VERSION,
        occurred_at=normalized_at,
        surface="server",
        server_confirmed=True,
        authoritative_outcome_status="confirmed",
    )
    with db.begin_nested():
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            return False
    return True


def local_day_for_milestone(value: datetime, user: User) -> date:
    return utc_naive_to_timezone_naive(value, _milestone_timezone_name(user)).date()


def prune_lifecycle_milestones(
    db: Session,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> int:
    """Delete account-level evidence older than the configured 180-day window."""

    cutoff = _as_utc_naive(now) - timedelta(days=retention_days)
    deleted = (
        db.query(LifecycleMilestone)
        .filter(LifecycleMilestone.occurred_at < cutoff)
        .delete(synchronize_session=False)
    )
    return int(deleted or 0)
