from __future__ import annotations

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.coach_crm import CoachTask
from fitminiapp_api.models.program import UserProgram
from fitminiapp_api.models.user import CoachClient, CoachClientInvite, User
from fitminiapp_api.services.coach_attention import build_coach_attention

CAPACITY_SCALE_BOUNDARIES = (10, 30, 100)


def capacity_band_for_count(active_client_count: int) -> str:
    if active_client_count < CAPACITY_SCALE_BOUNDARIES[0]:
        return "0_9"
    if active_client_count < CAPACITY_SCALE_BOUNDARIES[1]:
        return "10_29"
    if active_client_count < CAPACITY_SCALE_BOUNDARIES[2]:
        return "30_99"
    return "100_plus"


def _next_capacity_boundary(active_client_count: int) -> int | None:
    return next(
        (boundary for boundary in CAPACITY_SCALE_BOUNDARIES if active_client_count < boundary),
        None,
    )


def _active_client_ids(db: Session, coach: User) -> list[int]:
    return [
        int(client_id)
        for (client_id,) in (
            db.query(CoachClient.client_user_id)
            .join(User, User.id == CoachClient.client_user_id)
            .filter(
                CoachClient.coach_user_id == coach.id,
                CoachClient.status == "active",
                User.is_active.is_(True),
            )
            .order_by(CoachClient.client_user_id.asc())
            .all()
        )
    ]


def build_coach_capacity_snapshot(db: Session, coach: User) -> dict:
    """Build factual capacity evidence from the existing Coach OS relations.

    This intentionally does not create a queue, persist a score, or inspect client
    health/readiness facts. Counts are limited to the coach's active relations and
    existing operational records.
    """

    active_client_ids = _active_client_ids(db, coach)
    active_client_id_set = set(active_client_ids)
    active_client_count = len(active_client_ids)

    pending_invite_count = int(
        db.query(func.count(CoachClientInvite.id))
        .filter(
            CoachClientInvite.coach_user_id == coach.id,
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
            CoachTask.coach_user_id == coach.id,
            CoachTask.state == "open",
            User.is_active.is_(True),
        )
        .scalar()
        or 0
    )

    program_client_ids = {
        int(client_id)
        for (client_id,) in (
            db.query(UserProgram.user_id)
            .join(
                CoachClient,
                and_(
                    CoachClient.client_user_id == UserProgram.user_id,
                    CoachClient.coach_user_id == coach.id,
                    CoachClient.status == "active",
                ),
            )
            .join(User, User.id == UserProgram.user_id)
            .filter(
                UserProgram.is_active.is_(True),
                UserProgram.status.in_(("scheduled", "active")),
                User.is_active.is_(True),
            )
            .distinct()
            .all()
        )
    }
    clients_with_active_program_count = len(program_client_ids & active_client_id_set)
    without_program_count = active_client_count - clients_with_active_program_count
    roster_coverage_percent = (
        round(clients_with_active_program_count * 100 / active_client_count, 1)
        if active_client_count
        else None
    )

    attention = build_coach_attention(db, coach, limit=100)
    attention_items = attention["items"]
    attention_item_count = int(attention["total"])
    attention_client_count = len({int(item["client"]["id"]) for item in attention_items})

    bottleneck_values = (
        ("attention", attention_item_count, "attention"),
        ("open_tasks", open_task_count, "tasks"),
        ("without_program", without_program_count, "without_program"),
        ("pending_invites", pending_invite_count, "pending"),
    )
    bottlenecks = [
        {"key": key, "count": count, "action": action}
        for key, count, action in sorted(
            (item for item in bottleneck_values if item[1] > 0),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    return {
        "active_client_count": active_client_count,
        "pending_invite_count": pending_invite_count,
        "open_task_count": open_task_count,
        "attention_item_count": attention_item_count,
        "attention_client_count": attention_client_count,
        "attention_items_returned": len(attention_items),
        "attention_items_truncated": attention_item_count > len(attention_items),
        "clients_with_active_program_count": clients_with_active_program_count,
        "roster_coverage_percent": roster_coverage_percent,
        "capacity_band": capacity_band_for_count(active_client_count),
        "next_capacity_boundary": _next_capacity_boundary(active_client_count),
        "scale_boundaries": CAPACITY_SCALE_BOUNDARIES,
        "bottlenecks": bottlenecks,
        "generated_at": now_msk_naive(),
    }


__all__ = [
    "CAPACITY_SCALE_BOUNDARIES",
    "build_coach_capacity_snapshot",
    "capacity_band_for_count",
]
