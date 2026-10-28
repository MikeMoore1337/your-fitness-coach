from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.models.user import CoachClient, CoachClientInvite, User
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.coach_clients import close_user_coaching_relationships

TRAINER_CAPABILITY_TERMS_VERSION = "trainer-capability-v1"


def _locked_user(db: Session, user: User) -> User:
    if settings.dev_auth_fixed_accounts_only:
        raise HTTPException(status_code=403, detail="Роли изолированного DEV фиксированы")
    # Auth already loaded this row; refresh it after waiting for a concurrent lock holder.
    return db.query(User).filter(User.id == user.id).populate_existing().with_for_update().one()


def _relationship_counts(db: Session, user_id: int) -> tuple[int, int]:
    active_client_count = (
        db.query(func.count(CoachClient.id))
        .filter(
            CoachClient.coach_user_id == user_id,
            CoachClient.status == "active",
        )
        .scalar()
        or 0
    )
    pending_invite_count = (
        db.query(func.count(CoachClientInvite.id))
        .filter(
            CoachClientInvite.coach_user_id == user_id,
            CoachClientInvite.status == "pending",
        )
        .scalar()
        or 0
    )
    return int(active_client_count), int(pending_invite_count)


def trainer_capability_state(
    db: Session,
    user: User,
    *,
    activated_now: bool = False,
) -> dict:
    active_client_count, pending_invite_count = _relationship_counts(db, user.id)
    return {
        "is_active": user.is_coach,
        "activated_now": activated_now,
        "active_client_count": active_client_count,
        "pending_invite_count": pending_invite_count,
        "can_disable": user.is_coach
        and active_client_count == 0
        and not settings.dev_auth_fixed_accounts_only,
        "terms_version": TRAINER_CAPABILITY_TERMS_VERSION,
    }


def activate_trainer_capability(db: Session, user: User) -> dict:
    locked_user = _locked_user(db, user)
    activated_now = not locked_user.is_coach
    if activated_now:
        locked_user.is_coach = True
        record_audit_event(
            db,
            action="trainer_capability.activated",
            resource_type="user",
            actor_user_id=locked_user.id,
            target_user_id=locked_user.id,
            resource_id=locked_user.id,
            details={
                "source": "profile",
                "terms_version": TRAINER_CAPABILITY_TERMS_VERSION,
            },
        )
        db.commit()
        db.refresh(locked_user)
    return trainer_capability_state(db, locked_user, activated_now=activated_now)


def deactivate_trainer_capability(db: Session, user: User) -> dict:
    locked_user = _locked_user(db, user)
    if not locked_user.is_coach:
        return trainer_capability_state(db, locked_user)

    active_client_count, pending_invite_count = _relationship_counts(db, locked_user.id)
    if active_client_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Сначала завершите активные отношения с клиентами. "
                "История клиентов при отключении не удаляется."
            ),
        )

    close_user_coaching_relationships(
        db,
        locked_user,
        include_as_client=False,
        reason="trainer_capability_disabled",
        actor_user_id=locked_user.id,
    )
    locked_user.is_coach = False
    record_audit_event(
        db,
        action="trainer_capability.deactivated",
        resource_type="user",
        actor_user_id=locked_user.id,
        target_user_id=locked_user.id,
        resource_id=locked_user.id,
        details={"pending_invites_revoked": pending_invite_count},
    )
    db.commit()
    db.refresh(locked_user)
    return trainer_capability_state(db, locked_user)
