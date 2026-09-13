from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import (
    get_user_timezone_name,
    now_for_user_naive,
    today_for_user,
)
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.check_in import WeeklyCheckInSubmitRequest, WeeklyCheckInSummary
from fitminiapp_api.services.diary_nutrition import aggregate_diary_entries
from fitminiapp_api.services.energy_calibration import (
    EnergyCalibrationNotFoundError,
    get_energy_calibration_snapshot,
    inspect_energy_calibration,
)
from fitminiapp_api.services.nutrition import (
    get_current_nutrition_target,
    get_nutrition_target_for_date,
)
from fitminiapp_api.services.progress import build_progress_summary_for_range

SUMMARY_VERSION = "weekly-review-summary-v2"


class WeeklyCheckInConflictError(Exception):
    pass


def current_week_bounds(user: User) -> tuple[date, date, date]:
    submitted_on = today_for_user(user)
    week_start = submitted_on - timedelta(days=submitted_on.weekday())
    return week_start, week_start + timedelta(days=6), submitted_on


def _suspicious_low_nutrition_days(
    db: Session,
    user: User,
    *,
    period_start: date,
    period_end: date,
) -> list[dict]:
    status_rows = (
        db.query(FoodDiaryDayStatus.diary_date)
        .filter(
            FoodDiaryDayStatus.user_id == user.id,
            FoodDiaryDayStatus.diary_date.between(period_start, period_end),
            FoodDiaryDayStatus.status == "complete",
        )
        .order_by(FoodDiaryDayStatus.diary_date.asc())
        .all()
    )
    entries = (
        db.query(FoodDiaryEntry)
        .filter(
            FoodDiaryEntry.user_id == user.id,
            FoodDiaryEntry.diary_date.between(period_start, period_end),
        )
        .order_by(FoodDiaryEntry.diary_date.asc(), FoodDiaryEntry.id.asc())
        .all()
    )
    totals_by_key = aggregate_diary_entries(entries)
    result: list[dict] = []
    for (diary_date,) in status_rows:
        target = get_nutrition_target_for_date(db, user.id, diary_date)
        total = totals_by_key.get((user.id, diary_date))
        calories_total = (
            total.calories if total is not None and total.calories is not None else Decimal("0")
        )
        if target is None:
            continue
        calories = max(0, int(float(calories_total) + 0.5))
        if calories >= target.calories / 2:
            continue
        result.append(
            {
                "diary_date": diary_date,
                "calories": calories,
                "target_calories": target.calories,
            }
        )
    return result


def _adaptive_summary(
    db: Session,
    user: User,
    calibration_id: int | None,
) -> dict:
    try:
        calibration = (
            get_energy_calibration_snapshot(db, user, calibration_id)
            if calibration_id is not None
            else inspect_energy_calibration(db, user)
        )
    except EnergyCalibrationNotFoundError as exc:
        raise WeeklyCheckInConflictError("Предложение калибровки недоступно") from exc
    decision = {
        "accepted": "accepted",
        "rejected": "kept",
        "pending": "deferred",
        "no_change": "no_change",
    }.get(calibration.status, "not_available")
    return {
        "decision": decision,
        "calibration": calibration.model_dump(mode="json"),
    }


def build_weekly_summary(
    db: Session,
    user: User,
    *,
    week_start: date,
    period_end: date,
) -> dict:
    progress = build_progress_summary_for_range(db, user, week_start, period_end)
    body_progress = build_progress_summary_for_range(
        db,
        user,
        period_end - timedelta(days=89),
        period_end,
    )
    trends = body_progress["body"]["trends"]
    current_target = get_current_nutrition_target(db, user.id)
    weight_trend = next((trend for trend in trends if trend["metric"] == "weight_kg"), None)
    anthropometry_trends = [
        trend
        for trend in trends
        if trend["metric"] != "weight_kg" and trend["interpretation_status"] == "available"
    ]
    summary = {
        "ruleset_version": SUMMARY_VERSION,
        "period_start": week_start,
        "period_end": period_end,
        "goal": user.profile.goal if user.profile else None,
        "training": {
            "planned_workouts": progress["training"]["planned_workouts"],
            "completed_workouts": progress["training"]["completed_workouts"],
            "adherence": progress["adherence"]["workouts"],
        },
        "nutrition": {
            "logged_days": progress["nutrition"]["logged_days"],
            "complete_days": progress["nutrition"]["complete_days"],
            "incomplete_days": progress["nutrition"]["incomplete_days"],
            "fasted_days": progress["nutrition"]["fasted_days"],
            "unlogged_days": progress["nutrition"]["unlogged_days"],
            "average_calories": progress["nutrition"]["average_calories"],
            "target_calories": progress["nutrition"]["target_calories"],
            "average_protein_g": progress["nutrition"]["average_protein_g"],
            "target_protein_g": progress["nutrition"]["target_protein_g"],
            "calories_adherence": progress["adherence"]["calories"],
            "protein_adherence": progress["adherence"]["protein"],
            "current_target": (
                {
                    "effective_from": current_target.effective_from,
                    "source": current_target.source,
                    "calories": current_target.calories,
                    "protein_g": current_target.protein_g,
                    "fat_g": current_target.fat_g,
                    "carbs_g": current_target.carbs_g,
                }
                if current_target is not None
                else None
            ),
            "suspicious_low_days": _suspicious_low_nutrition_days(
                db,
                user,
                period_start=week_start,
                period_end=period_end,
            ),
        },
        "weight_trend": weight_trend,
        "anthropometry_trends": anthropometry_trends,
        "body_priority": body_progress["body"]["priority"],
        "progression": {
            "training_volume_kg": progress["training"]["volume_kg"],
            "new_personal_records": progress["training"]["new_personal_records"],
        },
        "data_sufficiency": {
            **progress["data_sufficiency"],
            "weight_trend": body_progress["data_sufficiency"]["weight_trend"],
            "anthropometry": body_progress["data_sufficiency"]["anthropometry"],
        },
        "adaptive_energy": None,
    }
    return WeeklyCheckInSummary.model_validate(summary).model_dump(mode="json")


def serialize_weekly_check_in(row: WeeklyCheckIn) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "week_start": row.week_start,
        "week_end": row.week_end,
        "submitted_on": row.submitted_on,
        "timezone": row.timezone,
        "status": row.status,
        "summary_version": row.summary_version,
        "summary": row.summary,
        "training_load": row.training_load,
        "recovery": row.recovery,
        "hunger": row.hunger,
        "adherence_difficulty": row.adherence_difficulty,
        "note": row.note,
        "created_at": row.created_at,
    }


def get_current_weekly_check_in(db: Session, user: User) -> dict:
    week_start, week_end, submitted_on = current_week_bounds(user)
    existing = (
        db.query(WeeklyCheckIn)
        .filter(WeeklyCheckIn.user_id == user.id, WeeklyCheckIn.week_start == week_start)
        .first()
    )
    summary = (
        existing.summary
        if existing
        else build_weekly_summary(db, user, week_start=week_start, period_end=submitted_on)
    )
    return {
        "week_start": week_start,
        "week_end": week_end,
        "submitted_on": submitted_on,
        "timezone": get_user_timezone_name(user),
        "existing": serialize_weekly_check_in(existing) if existing else None,
        "summary": summary,
    }


def submit_weekly_check_in(
    db: Session,
    user: User,
    payload: WeeklyCheckInSubmitRequest,
) -> WeeklyCheckIn:
    week_start, week_end, submitted_on = current_week_bounds(user)
    db.query(User).filter(User.id == user.id).with_for_update().one()
    if (
        db.query(WeeklyCheckIn.id)
        .filter(WeeklyCheckIn.user_id == user.id, WeeklyCheckIn.week_start == week_start)
        .first()
    ):
        raise WeeklyCheckInConflictError("Итоги этой недели уже сохранены")

    note = payload.note.strip() if payload.note else None
    summary = build_weekly_summary(db, user, week_start=week_start, period_end=submitted_on)
    if payload.status == "completed":
        summary["adaptive_energy"] = _adaptive_summary(db, user, payload.energy_calibration_id)
    row = WeeklyCheckIn(
        user_id=user.id,
        week_start=week_start,
        week_end=week_end,
        submitted_on=submitted_on,
        timezone=get_user_timezone_name(user),
        status=payload.status,
        summary_version=SUMMARY_VERSION,
        summary=WeeklyCheckInSummary.model_validate(summary).model_dump(mode="json"),
        training_load=payload.training_load,
        recovery=payload.recovery,
        hunger=payload.hunger,
        adherence_difficulty=payload.adherence_difficulty,
        note=note or None,
        created_at=now_for_user_naive(user),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WeeklyCheckInConflictError("Итоги этой недели уже сохранены") from exc
    db.refresh(row)
    return row


def list_weekly_check_ins(
    db: Session,
    user: User,
    *,
    limit: int,
    offset: int,
) -> dict:
    query = db.query(WeeklyCheckIn).filter(WeeklyCheckIn.user_id == user.id)
    total = query.count()
    rows = (
        query.order_by(WeeklyCheckIn.week_start.desc(), WeeklyCheckIn.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [serialize_weekly_check_in(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
