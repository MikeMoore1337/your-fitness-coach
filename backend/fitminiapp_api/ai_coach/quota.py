"""Durable, concurrency-safe AI Coach quota reservations."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.contracts import (
    AiCoachQuotaSnapshot,
    AiCoachRateLimitScope,
)
from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import MSK_TZ, now_msk_naive
from fitminiapp_api.models.ai_coach import AiCoachQuotaReservation, AiCoachQuotaWindow

USER_QUOTA_KIND = "user"
SERVICE_QUOTA_KIND = "service"
SERVICE_SUBJECT_KEY = "ai_coach"
RESERVED_STATUS = "reserved"
CONSUMED_STATUS = "consumed"
RELEASED_STATUS = "released"
EXPIRED_STATUS = "expired"

logger = logging.getLogger("app.ai_coach")


@dataclass(frozen=True)
class QuotaDecision:
    """Outcome of one durable reservation attempt."""

    granted: bool
    request_key: str
    user_snapshot: AiCoachQuotaSnapshot
    service_snapshot: AiCoachQuotaSnapshot
    rate_limit_scope: AiCoachRateLimitScope | None = None
    retry_after_seconds: int | None = None
    already_processing: bool = False
    already_consumed: bool = False
    request_key_conflict: bool = False


def _aware_reset_at(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=MSK_TZ)


def _retry_after_seconds(reset_at: datetime, now: datetime) -> int:
    remaining = (_aware_reset_at(reset_at) - _aware_reset_at(now)).total_seconds()
    return max(0, ceil(remaining))


def _subject_key(user_id: int | None, account_key: str | None = None) -> str:
    if user_id is not None:
        return str(user_id)
    # Legacy service tests/callers may provide a non-numeric opaque key. Never
    # persist that key itself; production API calls always use the numeric user id.
    return f"legacy:{hashlib.sha256((account_key or '').encode()).hexdigest()}"


class PersistentAiCoachQuota:
    """Store only counters and opaque request reservations in PostgreSQL.

    The user and service windows are locked in id order. A reservation occupies a
    slot while the provider call is running, then is either consumed or released.
    Expired reservations are ignored/reclaimed, making process crashes bounded by
    the reservation lease instead of permanently leaking quota.
    """

    def __init__(self, *, clock=now_msk_naive) -> None:
        self._clock = clock

    def reserve(
        self,
        db: Session,
        *,
        user_id: int | None,
        request_key: str | None,
        account_key: str | None = None,
    ) -> QuotaDecision:
        key = request_key or str(uuid4())
        now = self._clock()
        subject_key = _subject_key(user_id, account_key)
        user_window = self._ensure_window(
            db,
            quota_kind=USER_QUOTA_KIND,
            subject_key=subject_key,
            user_id=user_id,
            now=now,
            limit_value=settings.ai_coach_per_user_request_limit,
        )
        service_window = self._ensure_window(
            db,
            quota_kind=SERVICE_QUOTA_KIND,
            subject_key=SERVICE_SUBJECT_KEY,
            user_id=None,
            now=now,
            limit_value=settings.ai_coach_global_request_limit,
        )
        windows = self._lock_windows(db, user_window.id, service_window.id)
        user_window = windows[user_window.id]
        service_window = windows[service_window.id]
        self._refresh_window(db, user_window, now=now)
        self._refresh_window(db, service_window, now=now)
        self._reclaim_expired(db, (user_window.id, service_window.id), now=now)
        db.flush()

        existing = (
            db.query(AiCoachQuotaReservation)
            .filter(AiCoachQuotaReservation.request_key == key)
            .with_for_update()
            .one_or_none()
        )
        if (
            existing is not None
            and existing.user_id is not None
            and user_id is not None
            and existing.user_id != user_id
        ):
            decision = QuotaDecision(
                granted=False,
                request_key=key,
                user_snapshot=self._snapshot(db, user_window, now=now),
                service_snapshot=self._snapshot(db, service_window, now=now),
                request_key_conflict=True,
            )
            db.commit()
            return decision
        if existing is not None and existing.status == RESERVED_STATUS:
            if existing.expires_at > now:
                decision = QuotaDecision(
                    granted=False,
                    request_key=key,
                    user_snapshot=self._snapshot(db, user_window, now=now),
                    service_snapshot=self._snapshot(db, service_window, now=now),
                    already_processing=True,
                )
                db.commit()
                return decision
            existing.status = EXPIRED_STATUS
            existing.finalized_at = now

        if existing is not None and existing.status == CONSUMED_STATUS:
            decision = QuotaDecision(
                granted=False,
                request_key=key,
                user_snapshot=self._snapshot(db, user_window, now=now),
                service_snapshot=self._snapshot(db, service_window, now=now),
                already_consumed=True,
            )
            db.commit()
            return decision

        user_snapshot = self._snapshot(db, user_window, now=now)
        service_snapshot = self._snapshot(db, service_window, now=now)
        if not user_snapshot.can_send:
            decision = QuotaDecision(
                granted=False,
                request_key=key,
                user_snapshot=user_snapshot,
                service_snapshot=service_snapshot,
                rate_limit_scope=AiCoachRateLimitScope.USER,
                retry_after_seconds=user_snapshot.retry_after_seconds,
            )
            _log_snapshot(
                "ai_coach_quota_rate_limited",
                user_snapshot,
                scope=AiCoachRateLimitScope.USER,
            )
            db.commit()
            return decision
        if not service_snapshot.can_send:
            decision = QuotaDecision(
                granted=False,
                request_key=key,
                user_snapshot=user_snapshot,
                service_snapshot=service_snapshot,
                rate_limit_scope=AiCoachRateLimitScope.SERVICE,
                retry_after_seconds=service_snapshot.retry_after_seconds,
            )
            _log_snapshot(
                "ai_coach_quota_rate_limited",
                user_snapshot,
                scope=AiCoachRateLimitScope.SERVICE,
                retry_after_seconds=service_snapshot.retry_after_seconds,
            )
            db.commit()
            return decision

        if existing is None:
            existing = AiCoachQuotaReservation(
                request_key=key,
                user_id=user_id,
                user_window_id=user_window.id,
                service_window_id=service_window.id,
                status=RESERVED_STATUS,
                expires_at=now + self._reservation_ttl(),
                created_at=now,
            )
            db.add(existing)
        else:
            existing.user_id = user_id
            existing.user_window_id = user_window.id
            existing.service_window_id = service_window.id
            existing.status = RESERVED_STATUS
            existing.expires_at = now + self._reservation_ttl()
            existing.created_at = now
            existing.finalized_at = None
        db.flush()
        decision = QuotaDecision(
            granted=True,
            request_key=key,
            user_snapshot=self._snapshot(db, user_window, now=now),
            service_snapshot=self._snapshot(db, service_window, now=now),
        )
        # Provider calls must not hold row locks or an open transaction.
        db.commit()
        return decision

    def consume(self, db: Session, *, request_key: str) -> bool:
        return self._finalize(db, request_key=request_key, status=CONSUMED_STATUS)

    def release(self, db: Session, *, request_key: str) -> bool:
        return self._finalize(db, request_key=request_key, status=RELEASED_STATUS)

    def snapshot(self, db: Session, *, user_id: int) -> AiCoachQuotaSnapshot:
        now = self._clock()
        window = self._ensure_window(
            db,
            quota_kind=USER_QUOTA_KIND,
            subject_key=str(user_id),
            user_id=user_id,
            now=now,
            limit_value=settings.ai_coach_per_user_request_limit,
        )
        window = self._lock_windows(db, window.id)[window.id]
        self._refresh_window(db, window, now=now)
        self._reclaim_expired(db, (window.id,), now=now)
        db.flush()
        return self._snapshot(db, window, now=now)

    def reset_runtime_state(self) -> None:
        """Compatibility no-op: durable quota must survive process restart."""

    def _reservation_ttl(self) -> timedelta:
        configured = max(
            30,
            settings.ai_coach_timeout_seconds * settings.ai_coach_max_attempts + 60,
        )
        return timedelta(seconds=min(600, configured))

    @staticmethod
    def _ensure_window(
        db: Session,
        *,
        quota_kind: str,
        subject_key: str,
        user_id: int | None,
        now: datetime,
        limit_value: int,
    ) -> AiCoachQuotaWindow:
        window = (
            db.query(AiCoachQuotaWindow)
            .filter(
                AiCoachQuotaWindow.quota_kind == quota_kind,
                AiCoachQuotaWindow.subject_key == subject_key,
            )
            .one_or_none()
        )
        if window is None:
            values = {
                "quota_kind": quota_kind,
                "subject_key": subject_key,
                "user_id": user_id,
                "window_started_at": now,
                "reset_at": now + timedelta(seconds=settings.ai_coach_quota_window_seconds),
                "limit_value": limit_value,
                "used_count": 0,
                "updated_at": now,
            }
            bind = db.get_bind()
            if bind.dialect.name == "postgresql":
                db.execute(
                    postgresql_insert(AiCoachQuotaWindow)
                    .values(**values)
                    .on_conflict_do_nothing(
                        index_elements=["quota_kind", "subject_key"],
                    )
                )
            elif bind.dialect.name == "sqlite":
                db.execute(
                    sqlite_insert(AiCoachQuotaWindow)
                    .values(**values)
                    .on_conflict_do_nothing(
                        index_elements=["quota_kind", "subject_key"],
                    )
                )
            else:
                db.add(AiCoachQuotaWindow(**values))
                db.flush()
            window = (
                db.query(AiCoachQuotaWindow)
                .filter(
                    AiCoachQuotaWindow.quota_kind == quota_kind,
                    AiCoachQuotaWindow.subject_key == subject_key,
                )
                .one()
            )
        window.limit_value = limit_value
        return window

    @staticmethod
    def _lock_windows(
        db: Session,
        *window_ids: int,
    ) -> dict[int, AiCoachQuotaWindow]:
        rows = (
            db.query(AiCoachQuotaWindow)
            .filter(AiCoachQuotaWindow.id.in_(window_ids))
            .order_by(AiCoachQuotaWindow.id.asc())
            .with_for_update()
            .all()
        )
        result = {row.id: row for row in rows}
        if len(result) != len(set(window_ids)):
            raise RuntimeError("AI Coach quota window is missing")
        return result

    @staticmethod
    def _refresh_window(db: Session, window: AiCoachQuotaWindow, *, now: datetime) -> None:
        if window.reset_at > now:
            return
        reservations = (
            db.query(AiCoachQuotaReservation)
            .filter(
                AiCoachQuotaReservation.status == RESERVED_STATUS,
                or_(
                    AiCoachQuotaReservation.user_window_id == window.id,
                    AiCoachQuotaReservation.service_window_id == window.id,
                ),
            )
            .with_for_update()
            .all()
        )
        for reservation in reservations:
            reservation.status = EXPIRED_STATUS
            reservation.finalized_at = now
        window.window_started_at = now
        window.reset_at = now + timedelta(seconds=settings.ai_coach_quota_window_seconds)
        window.used_count = 0
        window.updated_at = now

    @staticmethod
    def _reclaim_expired(
        db: Session,
        window_ids: tuple[int, ...],
        *,
        now: datetime,
    ) -> None:
        reservations = (
            db.query(AiCoachQuotaReservation)
            .filter(
                AiCoachQuotaReservation.status == RESERVED_STATUS,
                AiCoachQuotaReservation.expires_at <= now,
                or_(
                    AiCoachQuotaReservation.user_window_id.in_(window_ids),
                    AiCoachQuotaReservation.service_window_id.in_(window_ids),
                ),
            )
            .with_for_update()
            .all()
        )
        for reservation in reservations:
            reservation.status = EXPIRED_STATUS
            reservation.finalized_at = now

    def _finalize(self, db: Session, *, request_key: str, status: str) -> bool:
        now = self._clock()
        reservation = (
            db.query(AiCoachQuotaReservation)
            .filter(AiCoachQuotaReservation.request_key == request_key)
            .one_or_none()
        )
        if reservation is None:
            return False
        windows = self._lock_windows(
            db,
            reservation.user_window_id,
            reservation.service_window_id,
        )
        self._refresh_window(db, windows[reservation.user_window_id], now=now)
        self._refresh_window(db, windows[reservation.service_window_id], now=now)
        self._reclaim_expired(
            db,
            (reservation.user_window_id, reservation.service_window_id),
            now=now,
        )
        db.flush()
        reservation = (
            db.query(AiCoachQuotaReservation)
            .filter(AiCoachQuotaReservation.id == reservation.id)
            .with_for_update()
            .one()
        )
        if reservation.status != RESERVED_STATUS:
            _log_snapshot(
                "ai_coach_quota_finalize_failed",
                self._snapshot(db, windows[reservation.user_window_id], now=now),
            )
            return False
        if reservation.expires_at <= now:
            reservation.status = EXPIRED_STATUS
            reservation.finalized_at = now
            _log_snapshot(
                "ai_coach_quota_finalize_failed",
                self._snapshot(db, windows[reservation.user_window_id], now=now),
            )
            return False
        if status == CONSUMED_STATUS:
            for window_id in (reservation.user_window_id, reservation.service_window_id):
                window = windows[window_id]
                window.used_count += 1
                window.updated_at = now
        reservation.status = status
        reservation.finalized_at = now
        db.flush()
        _log_snapshot(
            "ai_coach_quota_consumed" if status == CONSUMED_STATUS else "ai_coach_quota_released",
            self._snapshot(db, windows[reservation.user_window_id], now=now),
        )
        return True

    @staticmethod
    def _snapshot(
        db: Session,
        window: AiCoachQuotaWindow,
        *,
        now: datetime,
    ) -> AiCoachQuotaSnapshot:
        active_reservations = (
            db.query(func.count(AiCoachQuotaReservation.id))
            .filter(
                AiCoachQuotaReservation.status == RESERVED_STATUS,
                AiCoachQuotaReservation.expires_at > now,
                or_(
                    AiCoachQuotaReservation.user_window_id == window.id,
                    AiCoachQuotaReservation.service_window_id == window.id,
                ),
            )
            .scalar()
            or 0
        )
        remaining = max(0, window.limit_value - window.used_count - int(active_reservations))
        return AiCoachQuotaSnapshot(
            limit=window.limit_value,
            used=window.used_count,
            remaining=remaining,
            reset_at=_aware_reset_at(window.reset_at),
            retry_after_seconds=_retry_after_seconds(window.reset_at, now),
            can_send=remaining > 0,
        )


ai_coach_quota = PersistentAiCoachQuota()


def _log_snapshot(
    event: str,
    snapshot: AiCoachQuotaSnapshot,
    *,
    scope: AiCoachRateLimitScope | None = None,
    retry_after_seconds: int | None = None,
) -> None:
    logger.info(
        event,
        extra={
            "user_quota_remaining": snapshot.remaining,
            "user_quota_limit": snapshot.limit,
            "quota_window_reset_at": snapshot.reset_at.isoformat(),
            "user_quota_exhausted": not snapshot.can_send,
            "rate_limit_scope": scope.value if scope is not None else None,
            "rate_limit_retry_after_seconds": (
                retry_after_seconds
                if retry_after_seconds is not None
                else snapshot.retry_after_seconds
            ),
        },
    )


__all__ = [
    "CONSUMED_STATUS",
    "EXPIRED_STATUS",
    "RELEASED_STATUS",
    "RESERVED_STATUS",
    "SERVICE_QUOTA_KIND",
    "USER_QUOTA_KIND",
    "PersistentAiCoachQuota",
    "QuotaDecision",
    "ai_coach_quota",
]
