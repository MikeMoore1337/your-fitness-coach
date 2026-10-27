from __future__ import annotations

from datetime import timedelta
from statistics import median

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.coach_crm import CoachTask
from fitminiapp_api.models.user import CoachClient, CoachClientInvite, User
from fitminiapp_api.services.coach_capacity import capacity_band_for_count
from fitminiapp_api.services.root_admin import is_root_user

TRAINER_CLIENT_ACTIONS = frozenset(
    {
        "coach.business_session_created",
        "coach.client_operational_status_changed",
        "coach.client_profile_updated",
        "coach.invite_created",
        "coach.invite_accepted",
        "coach.package_created",
        "coach.payment_recorded",
        "coach.program_assigned",
        "coach.task_created",
        "coach.weekly_check_in_reviewed",
    }
)

_CAPACITY_BANDS = ("0_9", "10_29", "30_99", "100_plus")


def _real_user_ids(users: list[User]) -> set[int]:
    return {int(user.id) for user in users if not user.is_admin and not is_root_user(user)}


def build_trainer_capacity_report(db: Session, *, period_days: int) -> dict:
    as_of = now_msk_naive()
    cohort_since = as_of - timedelta(days=period_days)
    activation_events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.action == "trainer_capability.activated",
            AuditEvent.created_at >= cohort_since,
            AuditEvent.created_at <= as_of,
        )
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        .all()
    )
    activation_candidate_ids = {
        int(user_id)
        for event in activation_events
        for user_id in [event.target_user_id or event.actor_user_id]
        if user_id is not None
    }
    activation_users = db.query(User).filter(User.id.in_(activation_candidate_ids or [-1])).all()
    activation_user_ids = _real_user_ids(activation_users)
    first_activation_events: dict[int, AuditEvent] = {}
    for event in activation_events:
        trainer_id = event.target_user_id or event.actor_user_id
        if trainer_id is None or int(trainer_id) not in activation_user_ids:
            continue
        first_activation_events.setdefault(int(trainer_id), event)

    created_users = (
        db.query(User)
        .filter(
            User.created_at >= cohort_since,
            User.created_at <= as_of,
            User.is_admin.is_(False),
        )
        .all()
    )
    eligible_user_ids = _real_user_ids(created_users) | activation_user_ids
    activated_trainer_count = len(first_activation_events)
    trainer_activation_rate_percent = (
        round(activated_trainer_count * 100 / len(eligible_user_ids), 1)
        if eligible_user_ids
        else None
    )

    active_trainers = (
        db.query(User)
        .filter(
            User.is_coach.is_(True),
            User.is_active.is_(True),
            User.is_admin.is_(False),
        )
        .order_by(User.id.asc())
        .all()
    )
    active_trainer_ids = _real_user_ids(active_trainers)

    active_relations = (
        db.query(CoachClient)
        .join(User, User.id == CoachClient.client_user_id)
        .filter(
            CoachClient.status == "active",
            CoachClient.coach_user_id.in_(active_trainer_ids or [-1]),
            User.is_active.is_(True),
        )
        .all()
    )
    client_counts: dict[int, int] = {}
    for relation in active_relations:
        client_counts[relation.coach_user_id] = client_counts.get(relation.coach_user_id, 0) + 1

    capacity_band_totals = {
        band: {"trainer_count": 0, "active_client_count": 0} for band in _CAPACITY_BANDS
    }
    for trainer_id in sorted(active_trainer_ids):
        client_count = client_counts.get(trainer_id, 0)
        band = capacity_band_for_count(client_count)
        capacity_band_totals[band]["trainer_count"] += 1
        capacity_band_totals[band]["active_client_count"] += client_count

    pending_invite_count = int(
        db.query(func.count(CoachClientInvite.id))
        .filter(
            CoachClientInvite.coach_user_id.in_(active_trainer_ids or [-1]),
            CoachClientInvite.status == "pending",
        )
        .scalar()
        or 0
    )
    open_task_count = int(
        db.query(func.count(CoachTask.id))
        .join(
            CoachClient,
            and_(
                CoachClient.coach_user_id == CoachTask.coach_user_id,
                CoachClient.client_user_id == CoachTask.client_user_id,
                CoachClient.status == "active",
            ),
        )
        .join(User, User.id == CoachTask.client_user_id)
        .filter(
            CoachTask.coach_user_id.in_(active_trainer_ids or [-1]),
            CoachTask.state == "open",
            User.is_active.is_(True),
        )
        .scalar()
        or 0
    )

    action_events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.actor_user_id.in_(active_trainer_ids or [-1]),
            AuditEvent.action.in_(TRAINER_CLIENT_ACTIONS),
            AuditEvent.created_at >= cohort_since,
            AuditEvent.created_at <= as_of,
        )
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        .all()
    )
    action_events_by_trainer: dict[int, list[AuditEvent]] = {}
    for event in action_events:
        if event.actor_user_id is not None:
            action_events_by_trainer.setdefault(int(event.actor_user_id), []).append(event)

    time_to_first_action_seconds: list[float] = []
    for trainer_id, event in first_activation_events.items():
        first_action = next(
            (
                action
                for action in action_events_by_trainer.get(trainer_id, [])
                if action.created_at >= event.created_at
            ),
            None,
        )
        if first_action is None:
            continue
        time_to_first_action_seconds.append(
            max(0.0, (first_action.created_at - event.created_at).total_seconds())
        )

    return {
        "period_days": period_days,
        "cohort_since": cohort_since,
        "cohort_until": as_of,
        "as_of": as_of,
        "eligible_account_count": len(eligible_user_ids),
        "activated_trainer_count": activated_trainer_count,
        "trainer_activation_rate_percent": trainer_activation_rate_percent,
        "trainers_with_first_client_action": len(time_to_first_action_seconds),
        "time_to_first_client_action_median_seconds": (
            float(median(time_to_first_action_seconds)) if time_to_first_action_seconds else None
        ),
        "active_trainer_count": len(active_trainer_ids),
        "active_client_count": len(active_relations),
        "pending_invite_count": pending_invite_count,
        "open_task_count": open_task_count,
        "authorized_client_action_success_count": len(action_events),
        "authorized_client_action_failure_count": None,
        "authorized_client_action_failure_status": "not_recorded",
        "response_time_p50_ms": None,
        "response_time_p95_ms": None,
        "response_time_status": "not_measured",
        "capacity_bands": [
            {
                "band": band,
                "trainer_count": capacity_band_totals[band]["trainer_count"],
                "active_client_count": capacity_band_totals[band]["active_client_count"],
            }
            for band in _CAPACITY_BANDS
        ],
        "coverage_note": (
            "Отдельный trainer-capacity срез использует только подтверждённые аккаунты, "
            "связи, приглашения, открытые задачи и audit-события действий тренера. "
            "Клиентский funnel и его KPI в этот срез не входят."
        ),
        "exclusions": [
            "Root/admin-аккаунты и неактивные пользователи исключены из текущих capacity-срезов.",
            "Неуспешные запросы не сохраняются как audit-события, поэтому failure count не измерен.",
            "Request latency не сохраняется, поэтому p50/p95 response time не измерены.",
        ],
    }


__all__ = ["TRAINER_CLIENT_ACTIONS", "build_trainer_capacity_report"]
