from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import get_user_timezone_name, now_msk_naive
from fitminiapp_api.models.notification import Notification
from fitminiapp_api.models.user import CoachClient, CoachClientInvite, User, UserProfile
from fitminiapp_api.schemas.nutrition import NutritionTargetResponse
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.auth_identities import ensure_telegram_identity
from fitminiapp_api.services.profile import serialize_body_priority
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.telegram_auth import normalize_telegram_username


def get_or_create_user_by_telegram_id(
    db: Session,
    telegram_user_id: int,
    full_name: str | None = None,
) -> User:
    user = db.query(User).filter(User.telegram_user_id == telegram_user_id).first()
    if not user:
        user = User(
            telegram_user_id=telegram_user_id,
            username=f"user_{telegram_user_id}",
        )
        db.add(user)
        db.flush()

        db.add(
            UserProfile(
                user_id=user.id,
                full_name=full_name or f"Клиент {telegram_user_id}",
            )
        )
        ensure_telegram_identity(db, user, mark_login=False)
        db.commit()
        db.refresh(user)
    return user


def _coach_client_ids(db: Session, coach: User) -> list[int]:
    return [
        row.client_user_id
        for row in db.query(CoachClient.client_user_id)
        .filter(CoachClient.coach_user_id == coach.id, CoachClient.status == "active")
        .all()
    ]


def _is_coach_client(db: Session, coach: User, client: User) -> bool:
    return (
        db.query(CoachClient)
        .filter(
            CoachClient.coach_user_id == coach.id,
            CoachClient.client_user_id == client.id,
            CoachClient.status == "active",
        )
        .first()
        is not None
    )


def get_client_managed_by_coach(db: Session, coach: User, client_id: int) -> User:
    """Return an active client from this coach's own client list."""
    client = (
        db.query(User)
        .options(joinedload(User.profile))
        .join(CoachClient, CoachClient.client_user_id == User.id)
        .filter(
            CoachClient.coach_user_id == coach.id,
            CoachClient.client_user_id == client_id,
            CoachClient.status == "active",
            User.is_active.is_(True),
        )
        .first()
    )
    if not client:
        raise ProgramError("Client link not found")
    return client


def _get_existing_user_by_telegram_id(db: Session, telegram_user_id: int) -> User | None:
    return db.query(User).filter(User.telegram_user_id == telegram_user_id).first()


def _resolve_manageable_user(
    db: Session,
    current_user: User,
    target_telegram_user_id: int | None,
) -> User:
    if not target_telegram_user_id or target_telegram_user_id == current_user.telegram_user_id:
        return current_user

    target_user = _get_existing_user_by_telegram_id(db, target_telegram_user_id)
    if not target_user:
        raise ProgramError("Client is not linked to coach")

    if current_user.is_coach and _is_coach_client(db, current_user, target_user):
        return target_user

    raise ProgramError("No permission to manage this user")


def _can_manage_user_id(db: Session, current_user: User, owner_user_id: int | None) -> bool:
    if owner_user_id is None:
        return False
    if owner_user_id == current_user.id:
        return True
    return current_user.is_coach and owner_user_id in _coach_client_ids(db, current_user)


def _client_entry_from_user(
    db: Session,
    user: User,
    private_name: str | None,
    nutrition_target: NutritionTargetResponse | None,
    *,
    include_preferences_context: bool,
    operational_status: str = "active",
) -> dict:
    from fitminiapp_api.services.training_preferences import serialize_training_preferences

    profile = user.profile
    return {
        "id": user.id,
        "invite_id": None,
        "telegram_user_id": user.telegram_user_id,
        "username": user.username,
        "full_name": private_name,
        "birth_date": profile.birth_date if profile else None,
        "goal": profile.goal if profile else None,
        "level": profile.level if profile else None,
        "height_cm": profile.height_cm if profile else None,
        "weight_kg": profile.weight_kg if profile else None,
        "workouts_per_week": profile.workouts_per_week if profile else None,
        "cardio_trainings_per_week": (profile.cardio_trainings_per_week if profile else None),
        "resting_heart_rate": profile.resting_heart_rate if profile else None,
        "body_priority": serialize_body_priority(profile),
        "training_preferences": (
            serialize_training_preferences(
                db,
                user,
                profile,
                include_runtime_context=include_preferences_context,
            )
            if profile
            else None
        ),
        "timezone": get_user_timezone_name(user),
        "kbju": nutrition_target,
        "status": "active",
        "operational_status": operational_status,
    }


def _client_entry_from_invite(invite: CoachClientInvite) -> dict:
    synthetic_username = (
        invite.telegram_user_id is not None and invite.username == f"user_{invite.telegram_user_id}"
    )
    return {
        "id": None,
        "invite_id": invite.id,
        "telegram_user_id": invite.telegram_user_id,
        "username": None if synthetic_username else invite.username,
        "full_name": invite.full_name,
        "birth_date": None,
        "goal": None,
        "level": None,
        "height_cm": None,
        "weight_kg": None,
        "workouts_per_week": None,
        "cardio_trainings_per_week": None,
        "resting_heart_rate": None,
        "body_priority": None,
        "training_preferences": None,
        "timezone": None,
        "kbju": None,
        "status": "pending",
        "operational_status": "active",
    }


def _trainer_entry_from_user(user: User) -> dict:
    display_name = user.profile.full_name if user.profile else None
    if not display_name:
        name_parts = [user.first_name, user.last_name]
        display_name = " ".join(part for part in name_parts if part) or None

    return {
        "id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "username": user.username,
        "full_name": display_name,
        "can_open_chat": bool(user.username),
        "chat_url": f"https://t.me/{user.username}" if user.username else None,
        "chat_unavailable_reason": None
        if user.username
        else "У тренера не указан username, открыть чат из приложения нельзя",
    }


def cancel_client_request_notification(db: Session, invite_id: int) -> None:
    db.query(Notification).filter(
        Notification.dedupe_key == f"trainer_request:{invite_id}",
        Notification.status.in_(("queued", "processing", "failed")),
    ).update(
        {
            Notification.status: "cancelled",
            Notification.processing_started_at: None,
            Notification.next_attempt_at: None,
        },
        synchronize_session=False,
    )


def remove_client_for_coach(db: Session, coach: User, client_id: int) -> None:
    link = (
        db.query(CoachClient)
        .filter(
            CoachClient.coach_user_id == coach.id,
            CoachClient.client_user_id == client_id,
            CoachClient.status == "active",
        )
        .first()
    )
    if not link:
        raise ProgramError("Client link not found")

    link.status = "ended"
    link.ended_at = now_msk_naive()
    link.ended_reason = "removed_by_trainer"
    db.commit()


def revoke_coach_invite(db: Session, coach: User, invite_id: int) -> None:
    invite = (
        db.query(CoachClientInvite)
        .filter(
            CoachClientInvite.id == invite_id,
            CoachClientInvite.coach_user_id == coach.id,
            CoachClientInvite.status == "pending",
        )
        .with_for_update()
        .first()
    )
    if not invite:
        raise ProgramError("Client invite not found")

    invite.status = "revoked"
    cancel_client_request_notification(db, invite.id)
    db.commit()


def close_user_coaching_relationships(
    db: Session,
    user: User,
    *,
    include_as_client: bool,
    reason: str,
    actor_user_id: int | None = None,
) -> None:
    """End active relations and revoke pending invites without erasing history."""
    relation_filters = [CoachClient.coach_user_id == user.id]
    invite_filters = [CoachClientInvite.coach_user_id == user.id]
    if include_as_client:
        relation_filters.append(CoachClient.client_user_id == user.id)
        invite_filters.append(CoachClientInvite.client_user_id == user.id)

    now = now_msk_naive()
    relations = (
        db.query(CoachClient).filter(CoachClient.status == "active", or_(*relation_filters)).all()
    )
    for relation in relations:
        relation.status = "ended"
        relation.ended_at = now
        relation.ended_reason = reason
        record_audit_event(
            db,
            action="coach.relation_ended",
            resource_type="coach_client",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            resource_id=relation.id,
            details={"status": "ended", "reason": reason},
        )

    invites = (
        db.query(CoachClientInvite)
        .filter(CoachClientInvite.status == "pending", or_(*invite_filters))
        .all()
    )
    for invite in invites:
        invite.status = "revoked"
        cancel_client_request_notification(db, invite.id)
        record_audit_event(
            db,
            action="coach.invite_revoked",
            resource_type="coach_client_invite",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            resource_id=invite.id,
            details={"status": "revoked", "reason": reason},
        )


def get_current_trainer(db: Session, client: User) -> dict | None:
    trainer = (
        db.query(User)
        .join(CoachClient, CoachClient.coach_user_id == User.id)
        .options(joinedload(User.profile))
        .filter(
            CoachClient.client_user_id == client.id,
            CoachClient.status == "active",
            User.is_active.is_(True),
            User.is_coach.is_(True),
        )
        .order_by(CoachClient.id.desc())
        .first()
    )
    if not trainer:
        return None
    return _trainer_entry_from_user(trainer)


def remove_current_trainer(db: Session, client: User) -> None:
    relation = (
        db.query(CoachClient)
        .filter(CoachClient.client_user_id == client.id, CoachClient.status == "active")
        .first()
    )
    if relation:
        relation.status = "ended"
        relation.ended_at = now_msk_naive()
        relation.ended_reason = "removed_by_client"
    db.commit()


def create_coach_invite_link(db: Session, coach: User) -> dict:
    # require_coach loaded this row before the lock; do not reuse stale capability state.
    coach = db.query(User).filter(User.id == coach.id).populate_existing().with_for_update().one()
    if not coach.is_active or not coach.is_coach:
        raise ProgramError("Режим тренера недоступен")
    raw_token = secrets.token_urlsafe(24)
    invite = CoachClientInvite(
        coach_user_id=coach.id,
        source="invite_link",
        status="pending",
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        expires_at=now_msk_naive() + timedelta(days=14),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    start_param = f"trainer_{raw_token}"
    bot_username = settings.telegram_bot_username.strip().lstrip("@")
    telegram_url = f"https://t.me/{bot_username}?startapp={start_param}" if bot_username else None
    web_url = f"{settings.frontend_base_url.rstrip('/')}/join/{raw_token}"
    return {
        "invite_id": invite.id,
        "code": raw_token,
        "start_param": start_param,
        # Keep the legacy field for older Telegram clients while new clients
        # prefer the universal web URL.
        "url": telegram_url,
        "web_url": web_url,
        "telegram_url": telegram_url,
        "expires_at": invite.expires_at,
    }


def _get_available_invite_by_token(
    db: Session,
    raw_token: str,
    *,
    lock: bool,
) -> CoachClientInvite:
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    query = db.query(CoachClientInvite).filter(CoachClientInvite.token_hash == token_hash)
    if lock:
        query = query.with_for_update()
    invite = query.first()
    if not invite or invite.status != "pending":
        raise ProgramError("Приглашение не найдено или уже недействительно")
    if invite.expires_at and invite.expires_at < now_msk_naive():
        raise ProgramError("Срок действия приглашения истёк")
    return invite


def _available_invite_coach(
    db: Session,
    invite: CoachClientInvite,
    *,
    lock: bool = False,
) -> User:
    query = db.query(User).filter(User.id == invite.coach_user_id)
    if lock:
        query = query.populate_existing().with_for_update()
    else:
        query = query.options(joinedload(User.profile))
    coach = query.first()
    if not coach or not coach.is_active or not coach.is_coach:
        raise ProgramError("Тренер недоступен")
    return coach


def preview_coach_invite_link(db: Session, client: User, raw_token: str) -> dict:
    """Validate an invite and show its coach without changing database state."""
    invite = _get_available_invite_by_token(db, raw_token, lock=False)
    if invite.coach_user_id == client.id:
        raise ProgramError("Нельзя принять собственное приглашение")
    coach = _available_invite_coach(db, invite)
    current_trainer = get_current_trainer(db, client)
    return {
        "invite_id": invite.id,
        "coach": _trainer_entry_from_user(coach),
        "created_at": invite.created_at,
        "expires_at": invite.expires_at,
        "requires_trainer_change": bool(current_trainer and current_trainer["id"] != coach.id),
        "already_current_trainer": bool(current_trainer and current_trainer["id"] == coach.id),
        "current_trainer": current_trainer,
    }


def confirm_coach_invite_link(db: Session, client: User, raw_token: str) -> None:
    """Consume a one-time invite for exactly the authenticated client."""
    invite = _get_available_invite_by_token(db, raw_token, lock=False)
    coach = _available_invite_coach(db, invite, lock=True)
    db.query(User).filter(User.id == client.id).with_for_update().one()
    invite = _get_available_invite_by_token(db, raw_token, lock=True)
    if invite.coach_user_id == client.id:
        raise ProgramError("Нельзя принять собственное приглашение")

    active_relation = (
        db.query(CoachClient)
        .filter(
            CoachClient.client_user_id == client.id,
            CoachClient.status == "active",
        )
        .first()
    )
    if active_relation and active_relation.coach_user_id != coach.id:
        active_relation.status = "ended"
        active_relation.ended_at = now_msk_naive()
        active_relation.ended_reason = "client_switched_trainer"
    if not active_relation or active_relation.coach_user_id != coach.id:
        db.add(
            CoachClient(
                coach_user_id=coach.id,
                client_user_id=client.id,
                private_name=client.profile.full_name if client.profile else None,
                status="active",
                accepted_at=now_msk_naive(),
            )
        )

    invite.status = "accepted"
    invite.accepted_at = now_msk_naive()
    invite.client_user_id = client.id
    invite.telegram_user_id = client.telegram_user_id
    invite.username = normalize_telegram_username(client.username)
    invite.full_name = client.profile.full_name if client.profile else None
    cancel_client_request_notification(db, invite.id)
    db.commit()
