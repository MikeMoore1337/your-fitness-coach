from __future__ import annotations

import logging
import re

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.account import AccountDataExport
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.auth_identity import AuthIdentity
from fitminiapp_api.models.notification import Notification
from fitminiapp_api.models.user import CoachClient, User, UserProfile
from fitminiapp_api.services.account_exports import (
    AccountExportError,
    build_account_export_archive,
    complete_account_export,
    fail_account_export,
    lock_account_export_generation,
    start_account_export,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.coach_clients import close_user_coaching_relationships
from fitminiapp_api.services.lifecycle_reporting import lifecycle_funnel_report
from fitminiapp_api.services.root_admin import is_root_user
from fitminiapp_api.services.token_service import revoke_all_user_refresh_tokens
from fitminiapp_api.services.trainer_capacity_reporting import build_trainer_capacity_report

logger = logging.getLogger(__name__)

ADMIN_OPERATION_REASONS = {
    "security_incident",
    "abuse",
    "account_recovery",
    "support_request",
    "relationship_safety",
}
_SAFE_ERROR_CODE = re.compile(r"^[a-z0-9_.-]{1,64}$")


def _display_name(user: User, profile: UserProfile | None) -> str:
    return (
        (profile.full_name.strip() if profile and profile.full_name else "")
        or (user.username.strip() if user.username else "")
        or f"Аккаунт #{user.id}"
    )


def _mask_email(email: str) -> str:
    local, separator, domain = email.partition("@")
    if not separator or not local or not domain:
        return "Идентификатор скрыт"
    visible = local[0]
    return f"{visible}***@{domain.lower()}"


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _safe_error_code(value: str | None) -> str | None:
    if value and _SAFE_ERROR_CODE.fullmatch(value):
        return value
    return "unavailable" if value else None


def _serialize_search_user(
    user: User,
    profile: UserProfile | None,
    providers: list[str],
) -> dict:
    return {
        "id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "username": user.username,
        "display_name": _display_name(user, profile),
        "is_active": user.is_active,
        "is_trainer": user.is_coach,
        "is_root": is_root_user(user),
        "created_at": user.created_at,
        "linked_providers": sorted(set(providers)),
    }


def search_users(db: Session, query: str, *, limit: int = 20) -> list[dict]:
    normalized = query.strip().lstrip("@").lower()
    if len(normalized) < 2 and not normalized.isdigit():
        return []

    users = db.query(User, UserProfile).outerjoin(UserProfile, UserProfile.user_id == User.id)
    if normalized.isdigit():
        numeric = int(normalized)
        users = users.filter(or_(User.id == numeric, User.telegram_user_id == numeric))
    elif "@" in normalized:
        users = users.join(AuthIdentity, AuthIdentity.user_id == User.id).filter(
            func.lower(AuthIdentity.email) == normalized
        )
    else:
        pattern = f"%{_escape_like(normalized)}%"
        users = users.filter(
            or_(
                func.lower(func.coalesce(User.username, "")).like(pattern, escape="\\"),
                func.lower(func.coalesce(UserProfile.full_name, "")).like(pattern, escape="\\"),
            )
        )

    rows = users.order_by(User.id.desc()).limit(limit).all()
    user_ids = [user.id for user, _ in rows]
    providers_by_user: dict[int, list[str]] = {user_id: [] for user_id in user_ids}
    if user_ids:
        for user_id, provider in db.query(AuthIdentity.user_id, AuthIdentity.provider).filter(
            AuthIdentity.user_id.in_(user_ids)
        ):
            providers_by_user[user_id].append(provider)
    return [
        _serialize_search_user(user, profile, providers_by_user[user.id]) for user, profile in rows
    ]


def get_user_or_404(db: Session, user_id: int, *, lock: bool = False) -> User:
    query = db.query(User).filter(User.id == user_id)
    if lock:
        query = query.populate_existing().with_for_update()
    user = query.first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return user


def require_mutable_target(user: User) -> None:
    if is_root_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Операции с Root-аккаунтом запрещены",
        )


def _serialize_identity(identity: AuthIdentity) -> dict:
    if identity.provider == "telegram":
        identifier = f"Telegram ID {identity.subject}"
    elif identity.email:
        identifier = _mask_email(identity.email)
    else:
        identifier = "Идентификатор скрыт"
    return {
        "provider": identity.provider,
        "identifier": identifier,
        "verified": identity.provider == "telegram" or identity.email_verified,
        "last_login_at": identity.last_login_at,
    }


def _serialize_relationships(db: Session, user: User) -> list[dict]:
    rows = (
        db.query(CoachClient)
        .filter(or_(CoachClient.coach_user_id == user.id, CoachClient.client_user_id == user.id))
        .order_by(CoachClient.id.desc())
        .limit(30)
        .all()
    )
    counterparty_ids = {
        row.client_user_id if row.coach_user_id == user.id else row.coach_user_id for row in rows
    }
    counterparties = (
        db.query(User, UserProfile)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .filter(User.id.in_(counterparty_ids))
        .all()
        if counterparty_ids
        else []
    )
    names = {item.id: _display_name(item, profile) for item, profile in counterparties}
    protected_ids = {item.id for item, _ in counterparties if is_root_user(item)}
    return [
        {
            "id": row.id,
            "account_role": "trainer" if row.coach_user_id == user.id else "client",
            "counterparty_user_id": (
                row.client_user_id if row.coach_user_id == user.id else row.coach_user_id
            ),
            "counterparty_name": names.get(
                row.client_user_id if row.coach_user_id == user.id else row.coach_user_id,
                "Аккаунт недоступен",
            ),
            "status": row.status,
            "created_at": row.created_at,
            "accepted_at": row.accepted_at,
            "ended_at": row.ended_at,
            "ended_reason": row.ended_reason,
            "can_end": (
                row.status == "active"
                and not is_root_user(user)
                and (row.client_user_id if row.coach_user_id == user.id else row.coach_user_id)
                not in protected_ids
            ),
        }
        for row in rows
    ]


def _job_from_notification(row: Notification) -> dict:
    return {
        "job_id": f"notification:{row.id}",
        "kind": "notification",
        "user_id": row.user_id,
        "status": row.status,
        "created_at": row.created_at,
        "scheduled_for": row.scheduled_for,
        "completed_at": row.sent_at,
        "attempt_count": row.attempt_count,
        "error_code": None,
        "retry_allowed": False,
    }


def _job_from_export(row: AccountDataExport) -> dict:
    return {
        "job_id": f"export:{row.export_id}",
        "kind": "account_export",
        "user_id": row.user_id,
        "status": row.status,
        "created_at": row.created_at,
        "scheduled_for": None,
        "completed_at": row.completed_at,
        "attempt_count": None,
        "error_code": _safe_error_code(row.error_code),
        "retry_allowed": row.status in {"error", "expired"},
    }


def list_jobs(db: Session, *, user_id: int | None = None, limit: int = 50) -> list[dict]:
    notifications = db.query(Notification)
    exports = db.query(AccountDataExport)
    if user_id is not None:
        notifications = notifications.filter(Notification.user_id == user_id)
        exports = exports.filter(AccountDataExport.user_id == user_id)
    rows = [
        *(
            _job_from_notification(row)
            for row in notifications.order_by(Notification.id.desc()).limit(limit)
        ),
        *(
            _job_from_export(row)
            for row in exports.order_by(AccountDataExport.id.desc()).limit(limit)
        ),
    ]
    rows.sort(key=lambda row: row["created_at"], reverse=True)
    return rows[:limit]


def _audit_reason(details: dict | None) -> str | None:
    reason = details.get("reason") if isinstance(details, dict) else None
    return reason if reason in ADMIN_OPERATION_REASONS else None


def _serialize_audit(row: AuditEvent) -> dict:
    return {
        "id": row.id,
        "action": row.action,
        "actor_user_id": row.actor_user_id,
        "target_user_id": row.target_user_id,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "reason": _audit_reason(row.details),
        "created_at": row.created_at,
    }


def list_audit_events(
    db: Session,
    *,
    target_user_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    query = db.query(AuditEvent)
    if target_user_id is not None:
        query = query.filter(AuditEvent.target_user_id == target_user_id)
    return [
        _serialize_audit(row)
        for row in query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
        .all()
    ]


def user_detail(db: Session, user_id: int) -> dict:
    user = get_user_or_404(db, user_id)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    identities = (
        db.query(AuthIdentity)
        .filter(AuthIdentity.user_id == user.id)
        .order_by(AuthIdentity.provider.asc())
        .all()
    )
    payload = _serialize_search_user(user, profile, [item.provider for item in identities])
    payload.update(
        {
            "identities": [_serialize_identity(item) for item in identities],
            "relationships": _serialize_relationships(db, user),
            "jobs": list_jobs(db, user_id=user.id, limit=20),
            "audit_history": list_audit_events(db, target_user_id=user.id, limit=30),
        }
    )
    return payload


def update_user_status(
    db: Session,
    *,
    actor: User,
    target_user_id: int,
    is_active: bool,
    reason: str,
) -> dict:
    target = get_user_or_404(db, target_user_id, lock=True)
    require_mutable_target(target)
    changed = target.is_active != is_active
    if changed:
        target.is_active = is_active
        if not is_active:
            revoke_all_user_refresh_tokens(db, target.id, commit=False)
            close_user_coaching_relationships(
                db,
                target,
                include_as_client=True,
                reason=f"root_block:{reason}",
                actor_user_id=actor.id,
            )
        record_audit_event(
            db,
            action="root.account_unblocked" if is_active else "root.account_blocked",
            resource_type="user",
            actor_user_id=actor.id,
            target_user_id=target.id,
            resource_id=target.id,
            details={"reason": reason},
        )
        db.commit()
        logger.info(
            "root_admin_operation_completed",
            extra={
                "operation": "account_unblocked" if is_active else "account_blocked",
                "actor_user_id": actor.id,
                "target_user_id": target.id,
            },
        )
    return user_detail(db, target.id)


def update_trainer_capability(
    db: Session,
    *,
    actor: User,
    target_user_id: int,
    is_active: bool,
    reason: str,
) -> dict:
    target = get_user_or_404(db, target_user_id, lock=True)
    require_mutable_target(target)
    changed = target.is_coach != is_active
    if changed:
        if not is_active:
            close_user_coaching_relationships(
                db,
                target,
                include_as_client=False,
                reason=f"root_trainer_revoked:{reason}",
                actor_user_id=actor.id,
            )
        target.is_coach = is_active
        record_audit_event(
            db,
            action=(
                "root.trainer_capability_restored"
                if is_active
                else "root.trainer_capability_revoked"
            ),
            resource_type="user",
            actor_user_id=actor.id,
            target_user_id=target.id,
            resource_id=target.id,
            details={"reason": reason},
        )
        db.commit()
        logger.info(
            "root_admin_operation_completed",
            extra={
                "operation": (
                    "trainer_capability_restored" if is_active else "trainer_capability_revoked"
                ),
                "actor_user_id": actor.id,
                "target_user_id": target.id,
            },
        )
    return user_detail(db, target.id)


def end_relationship(
    db: Session,
    *,
    actor: User,
    relationship_id: int,
    reason: str,
) -> dict:
    relation = (
        db.query(CoachClient)
        .filter(CoachClient.id == relationship_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if relation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Связь не найдена")
    coach = get_user_or_404(db, relation.coach_user_id)
    client = get_user_or_404(db, relation.client_user_id)
    require_mutable_target(coach)
    require_mutable_target(client)
    if relation.status == "active":
        relation.status = "ended"
        relation.ended_at = now_msk_naive()
        relation.ended_reason = f"root_end:{reason}"
        record_audit_event(
            db,
            action="root.coach_relationship_ended",
            resource_type="coach_client",
            actor_user_id=actor.id,
            target_user_id=client.id,
            resource_id=relation.id,
            details={"reason": reason, "coach_user_id": coach.id},
        )
        db.commit()
        logger.info(
            "root_admin_operation_completed",
            extra={
                "operation": "coach_relationship_ended",
                "actor_user_id": actor.id,
                "target_user_id": client.id,
                "resource_id": relation.id,
            },
        )
    return user_detail(db, client.id)


def retry_account_export(
    db: Session,
    *,
    actor: User,
    export_id: str,
) -> dict:
    previous = db.query(AccountDataExport).filter(AccountDataExport.export_id == export_id).first()
    if previous is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Задача экспорта не найдена"
        )
    if previous.status not in {"error", "expired"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Повтор доступен только для ошибочного или истёкшего экспорта",
        )
    target = get_user_or_404(db, previous.user_id)
    require_mutable_target(target)
    previous_status = previous.status
    row = start_account_export(db, target)
    generation_id = row.export_id
    db.commit()
    try:
        archive_bytes, filename = build_account_export_archive(db, target)
        current = lock_account_export_generation(db, target.id, generation_id)
        if current is None:
            latest = (
                db.query(AccountDataExport).filter(AccountDataExport.user_id == target.id).one()
            )
            return _job_from_export(latest)
        complete_account_export(current, archive_bytes, filename)
        result_status = "ready"
    except AccountExportError as exc:
        current = lock_account_export_generation(db, target.id, generation_id)
        if current is None:
            latest = (
                db.query(AccountDataExport).filter(AccountDataExport.user_id == target.id).one()
            )
            return _job_from_export(latest)
        fail_account_export(current, exc.error_code)
        result_status = "error"
    except Exception:
        db.rollback()
        current = lock_account_export_generation(db, target.id, generation_id)
        if current is None:
            latest = (
                db.query(AccountDataExport).filter(AccountDataExport.user_id == target.id).one()
            )
            return _job_from_export(latest)
        fail_account_export(current, "generation_failed")
        result_status = "error"
        logger.exception(
            "root_admin_export_retry_failed",
            extra={"actor_user_id": actor.id, "target_user_id": target.id},
        )
    record_audit_event(
        db,
        action="root.account_export_retried",
        resource_type="account_data_export",
        actor_user_id=actor.id,
        target_user_id=target.id,
        resource_id=generation_id,
        details={"previous_status": previous_status, "result_status": result_status},
    )
    db.commit()
    db.refresh(current)
    logger.info(
        "root_admin_operation_completed",
        extra={
            "operation": "account_export_retried",
            "actor_user_id": actor.id,
            "target_user_id": target.id,
            "result_status": result_status,
        },
    )
    return _job_from_export(current)


def funnel_aggregates(db: Session, *, period_days: int) -> dict:
    return lifecycle_funnel_report(db, period_days=period_days)


def trainer_capacity_aggregates(db: Session, *, period_days: int) -> dict:
    """Return trainer capacity metrics without changing the client KPI funnel."""

    return build_trainer_capacity_report(db, period_days=period_days)
