from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, cast

from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import (
    now_for_user_naive,
    today_for_user,
    user_local_naive_to_utc_naive,
)
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.user import User
from fitminiapp_api.services.lifecycle_milestones import record_lifecycle_milestone

ProgressWeeklyActionKind = Literal[
    "weekly_review",
    "workout",
    "nutrition",
    "measurement",
    "none",
]
ProgressWeeklyActionStatus = Literal["available", "completed", "unavailable"]
ProgressWeeklyActionTarget = Literal["today", "nutrition", "body", "progress", "weekly_review"]
ProgressWeeklyActionReason = Literal[
    "review_required",
    "scheduled_training_gap",
    "nutrition_coverage_gap",
    "weight_trend_insufficient",
    "no_supported_action",
]

_PERSISTED_ACTION_KINDS = frozenset({"workout", "nutrition", "measurement", "none"})

_ACTION_COPY: dict[
    str,
    tuple[
        str,
        str,
        ProgressWeeklyActionTarget,
        ProgressWeeklyActionReason,
    ],
] = {
    "weekly_review": (
        "Пройти недельный обзор",
        "Сверьте факты недели и зафиксируйте следующий шаг.",
        "weekly_review",
        "review_required",
    ),
    "workout": (
        "Открыть план недели",
        "Завершите следующую запланированную тренировку и отметьте фактические подходы.",
        "today",
        "scheduled_training_gap",
    ),
    "nutrition": (
        "Записать питание",
        "Заполните пропущенный день, чтобы следующий обзор опирался на полный контекст.",
        "nutrition",
        "nutrition_coverage_gap",
    ),
    "measurement": (
        "Добавить замер",
        "Добавьте повторный замер веса: одна точка не образует тренд.",
        "body",
        "weight_trend_insufficient",
    ),
    "none": (
        "Отдельный шаг не выбран",
        "Данных для безопасного отдельного шага пока нет. Сохраняйте факты недели.",
        "progress",
        "no_supported_action",
    ),
}


def _current_week_start(user: User) -> date:
    submitted_on = today_for_user(user)
    return submitted_on - timedelta(days=submitted_on.weekday())


def derive_progress_weekly_action_kind(
    summary: dict,
) -> Literal["workout", "nutrition", "measurement", "none"]:
    training = summary.get("training") or {}
    if int(training.get("completed_workouts") or 0) < int(training.get("planned_workouts") or 0):
        return "workout"

    nutrition = summary.get("nutrition") or {}
    if int(nutrition.get("unlogged_days") or 0) > 0:
        return "nutrition"

    weight_trend = (summary.get("data_sufficiency") or {}).get("weight_trend") or {}
    if weight_trend.get("status") != "sufficient":
        return "measurement"

    return "none"


def build_progress_weekly_action(
    summary: dict,
    *,
    existing: WeeklyCheckIn | None,
) -> dict[str, object]:
    if existing is None:
        kind: ProgressWeeklyActionKind = "weekly_review"
        status: ProgressWeeklyActionStatus = "available"
        completed_at = None
    elif existing.status != "completed":
        kind = "none"
        status = "unavailable"
        completed_at = None
    else:
        stored_kind = existing.progress_action_kind
        kind = cast(
            ProgressWeeklyActionKind,
            stored_kind
            if stored_kind in _PERSISTED_ACTION_KINDS
            else derive_progress_weekly_action_kind(summary),
        )
        completed_at = existing.progress_action_completed_at
        status = "completed" if completed_at is not None else "available"

    title, detail, target, reason = _ACTION_COPY[kind]
    if status == "completed":
        title = "Шаг выполнен"
        detail = "Сервер подтвердил выполнение выбранного действия недели."
    elif status == "unavailable":
        title = "Действие недоступно"
        detail = "Эта неделя отмечена как пропущенная; новый шаг появится в следующем обзоре."

    return {
        "kind": kind,
        "status": status,
        "target": target,
        "reason": reason,
        "title": title,
        "detail": detail,
        "completed_at": completed_at,
    }


def record_progress_weekly_action_completion(
    db: Session,
    user: User,
    kind: Literal["workout", "nutrition", "measurement"],
) -> bool:
    """Confirm the selected action from the current weekly cycle once.

    The caller is already inside the authoritative mutation transaction. The
    weekly row is locked before changing its completion timestamp, so retries
    remain idempotent and only the selected action can satisfy the cycle.
    """

    week_start = _current_week_start(user)
    row = (
        db.query(WeeklyCheckIn)
        .filter(
            WeeklyCheckIn.user_id == user.id,
            WeeklyCheckIn.week_start == week_start,
        )
        .with_for_update()
        .first()
    )
    if row is None or row.status != "completed":
        return False
    selected_kind = row.progress_action_kind
    if selected_kind is None:
        selected_kind = derive_progress_weekly_action_kind(row.summary)
    if selected_kind != kind:
        return False
    if row.progress_action_completed_at is not None:
        return True

    completed_at = now_for_user_naive(user)
    if row.created_at and completed_at < row.created_at:
        return False
    row.progress_action_completed_at = completed_at
    record_lifecycle_milestone(
        db,
        user,
        "progress_next_action_completed",
        occurred_at=user_local_naive_to_utc_naive(completed_at, user),
    )
    return True
