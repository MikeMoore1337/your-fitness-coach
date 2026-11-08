"""Per-user upload budget and PostgreSQL-wide parser concurrency bound."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from fitminiapp_api.models.nutrition_import import NutritionImportUploadAttempt
from fitminiapp_api.models.user import User
from fitminiapp_api.services.nutrition_import_drafts import NutritionDraftError, _lock_user

MAX_UPLOADS_PER_HOUR = 10
MAX_CONCURRENT_PARSERS = 2
_PARSER_LOCK_NAMESPACE = 1497776954
_USER_PARSER_LOCK_NAMESPACE = 1497776955


def reserve_upload_attempt(db: Session, user: User) -> None:
    if db.get_bind().dialect.name != "postgresql":
        raise NutritionDraftError("storage_unavailable", 503)
    _lock_user(db, user)
    now = datetime.now(UTC).replace(tzinfo=None)
    count = (
        db.query(NutritionImportUploadAttempt.id)
        .filter(
            NutritionImportUploadAttempt.owner_user_id == user.id,
            NutritionImportUploadAttempt.created_at > now - timedelta(hours=1),
        )
        .count()
    )
    if count >= MAX_UPLOADS_PER_HOUR:
        raise NutritionDraftError("rate_limited", 429)
    db.add(NutritionImportUploadAttempt(owner_user_id=user.id, created_at=now))
    db.commit()


def acquire_parser_slot(db: Session, user: User) -> None:
    if db.get_bind().dialect.name != "postgresql":
        raise NutritionDraftError("storage_unavailable", 503)
    user_acquired = db.execute(
        text("SELECT pg_try_advisory_xact_lock(:namespace, :user_id)"),
        {"namespace": _USER_PARSER_LOCK_NAMESPACE, "user_id": user.id},
    ).scalar_one()
    if not user_acquired:
        raise NutritionDraftError("parser_busy", 429)
    acquired = any(
        db.execute(
            text("SELECT pg_try_advisory_xact_lock(:namespace, :slot)"),
            {
                "namespace": _PARSER_LOCK_NAMESPACE,
                "slot": slot,
            },
        ).scalar_one()
        for slot in range(MAX_CONCURRENT_PARSERS)
    )
    if not acquired:
        raise NutritionDraftError("parser_busy", 429)
    _lock_user(db, user)


def expire_upload_attempts(db: Session, *, now: datetime | None = None, limit: int = 1000) -> int:
    cutoff = (now or datetime.now(UTC).replace(tzinfo=None)) - timedelta(hours=1)
    attempts = (
        db.query(NutritionImportUploadAttempt)
        .filter(NutritionImportUploadAttempt.created_at <= cutoff)
        .order_by(NutritionImportUploadAttempt.created_at, NutritionImportUploadAttempt.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    for attempt in attempts:
        db.delete(attempt)
    return len(attempts)
