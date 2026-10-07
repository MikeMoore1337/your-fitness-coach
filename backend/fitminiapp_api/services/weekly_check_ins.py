from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.core.timezone import (
    get_user_timezone_name,
    now_for_user_naive,
    today_for_user,
    user_local_naive_to_utc_naive,
)
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.nutrition_plan import NutritionPlan, NutritionPlanOperation
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.check_in import (
    WeeklyCheckInSubmitRequest,
    WeeklyCheckInSummary,
    WeeklyPlanningReviewConfirmRequest,
    WeeklyPlanningReviewSummary,
)
from fitminiapp_api.schemas.food_diary import FoodDiaryNutrition, FoodDiaryTargets
from fitminiapp_api.services.diary_nutrition import DiaryDayNutrition, aggregate_diary_entries
from fitminiapp_api.services.energy_calibration import (
    EnergyCalibrationNotFoundError,
    get_energy_calibration_snapshot,
    inspect_energy_calibration,
)
from fitminiapp_api.services.lifecycle_milestones import record_lifecycle_milestone
from fitminiapp_api.services.nutrition import (
    get_current_nutrition_target,
    get_nutrition_target_for_date,
)
from fitminiapp_api.services.nutrition_plan import (
    MAX_ITEMS_PER_DAY,
    NutritionPlanError,
    _fingerprint,
    _operation,
    copy_pending_plan_items,
    get_plan_week,
)
from fitminiapp_api.services.progress import build_progress_summary_for_range
from fitminiapp_api.services.progress_weekly_action import (
    build_progress_weekly_action,
    derive_progress_weekly_action_kind,
)

SUMMARY_VERSION = "weekly-review-summary-v2"
ZERO = Decimal("0")


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


def _sum_optional(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return left + right


def _sum_nutrition(values: list[FoodDiaryNutrition]) -> FoodDiaryNutrition:
    return FoodDiaryNutrition(
        energy_kcal=sum((value.energy_kcal for value in values), start=ZERO),
        protein_g=_sum_nutrition_field(values, "protein_g"),
        fat_g=_sum_nutrition_field(values, "fat_g"),
        carbs_g=_sum_nutrition_field(values, "carbs_g"),
        fiber_g=_sum_nutrition_field(values, "fiber_g"),
    )


def _sum_nutrition_field(
    values: list[FoodDiaryNutrition],
    field: str,
) -> Decimal | None:
    result: Decimal | None = ZERO
    for value in values:
        result = _sum_optional(result, getattr(value, field))
    return result


def _diary_nutrition(total: DiaryDayNutrition) -> FoodDiaryNutrition:
    return FoodDiaryNutrition(
        energy_kcal=total.calories if total.calories is not None else ZERO,
        protein_g=total.protein_g,
        fat_g=total.fat_g,
        carbs_g=total.carbs_g,
        fiber_g=total.fiber_g,
    )


def _planning_operation_key(source_date: date, source_revision: int) -> str:
    return f"weekly-review-plan:{source_date.isoformat()}:{source_revision}"


def build_weekly_planning_review(
    db: Session,
    user: User,
    *,
    week_start: date,
    period_end: date,
) -> dict:
    plan_week = get_plan_week(db, user, week_start)
    diary_entries = (
        db.query(FoodDiaryEntry)
        .filter(
            FoodDiaryEntry.user_id == user.id,
            FoodDiaryEntry.diary_date.between(week_start, plan_week.week_end),
        )
        .order_by(FoodDiaryEntry.diary_date.asc(), FoodDiaryEntry.id.asc())
        .all()
    )
    diary_totals = aggregate_diary_entries(diary_entries)
    next_plans = (
        db.query(NutritionPlan)
        .options(selectinload(NutritionPlan.items))
        .filter(
            NutritionPlan.user_id == user.id,
            NutritionPlan.plan_date.between(
                week_start + timedelta(days=7), week_start + timedelta(days=13)
            ),
        )
        .all()
    )
    next_plans_by_date = {plan.plan_date: plan for plan in next_plans}

    day_summaries: list[dict] = []
    observed_days: list[dict] = []
    candidate_specs: list[tuple[date, date, int, int, int, int]] = []
    for day in plan_week.days:
        day_items = [item for slot in day.slots for item in slot.items]
        planned_items = len(day_items)
        consumed_items = sum(item.status == "consumed" for item in day_items)
        pending_items = sum(item.status == "planned" for item in day_items)
        skipped_items = sum(item.status == "skipped" for item in day_items)
        observed = day.plan_date <= period_end
        actual = diary_totals.get((user.id, day.plan_date))
        consumed = _diary_nutrition(actual) if actual is not None and actual.has_entries else None
        plan_status = (
            "no_plan" if planned_items == 0 else "partial" if pending_items > 0 else "complete"
        )
        day_summary = {
            "diary_date": day.plan_date,
            "observed": observed,
            "plan_status": plan_status,
            "plan_revision": day.revision,
            "planned_items": planned_items,
            "consumed_items": consumed_items,
            "pending_items": pending_items,
            "skipped_items": skipped_items,
            "planned": day.planned,
            "consumed": consumed,
            "target": day.targets,
        }
        day_summaries.append(day_summary)
        if observed:
            observed_days.append(day_summary)
            if pending_items > 0:
                target_plan = next_plans_by_date.get(day.plan_date + timedelta(days=7))
                target_item_count = len(target_plan.items) if target_plan is not None else 0
                if target_item_count + pending_items <= MAX_ITEMS_PER_DAY:
                    candidate_specs.append(
                        (
                            day.plan_date,
                            day.plan_date + timedelta(days=7),
                            day.revision,
                            target_plan.revision if target_plan is not None else 0,
                            pending_items,
                            target_item_count,
                        )
                    )

    operation_keys = {
        _planning_operation_key(source_date, source_revision)
        for source_date, _, source_revision, _, _, _ in candidate_specs
    }
    applied_keys = {
        key
        for (key,) in db.query(NutritionPlanOperation.idempotency_key)
        .filter(
            NutritionPlanOperation.user_id == user.id,
            NutritionPlanOperation.idempotency_key.in_(operation_keys),
        )
        .all()
    }
    proposals = [
        {
            "source_date": source_date,
            "target_date": target_date,
            "source_revision": source_revision,
            "target_revision": target_revision,
            "pending_item_count": pending_item_count,
            "target_item_count": target_item_count,
        }
        for (
            source_date,
            target_date,
            source_revision,
            target_revision,
            pending_item_count,
            target_item_count,
        ) in candidate_specs
        if _planning_operation_key(source_date, source_revision) not in applied_keys
    ]

    planned_days = sum(day["planned_items"] > 0 for day in observed_days)
    target_days = sum(day["target"] is not None for day in observed_days)
    consumed_days = sum(day["consumed"] is not None for day in observed_days)
    pending_days = sum(day["pending_items"] > 0 for day in observed_days)
    repeated_miss_dates = [day["diary_date"] for day in observed_days if day["pending_items"] > 0]
    if len(repeated_miss_dates) < 2:
        repeated_miss_dates = []

    planned_total = _sum_nutrition([day["planned"] for day in observed_days])
    consumed_values = [day["consumed"] for day in observed_days if day["consumed"] is not None]
    target_values = [day["target"] for day in observed_days if day["target"] is not None]
    consumed_total = _sum_nutrition(consumed_values) if consumed_values else None
    target_total = (
        FoodDiaryTargets(
            energy_kcal=sum((value.energy_kcal for value in target_values), start=ZERO),
            protein_g=_sum_nutrition_field(target_values, "protein_g"),
            fat_g=_sum_nutrition_field(target_values, "fat_g"),
            carbs_g=_sum_nutrition_field(target_values, "carbs_g"),
        )
        if target_values
        else None
    )
    availability = (
        "no_data"
        if not planned_days and not target_days and not consumed_days
        else "no_plan"
        if not planned_days
        else "no_target"
        if not target_days
        else "available"
    )
    return WeeklyPlanningReviewSummary.model_validate(
        {
            "week_start": week_start,
            "week_end": plan_week.week_end,
            "availability": availability,
            "days": day_summaries,
            "planned_days": planned_days,
            "target_days": target_days,
            "consumed_days": consumed_days,
            "pending_days": pending_days,
            "repeated_miss_dates": repeated_miss_dates,
            "planned_total": planned_total,
            "consumed_total": consumed_total,
            "target_total": target_total,
            "proposals": proposals,
        }
    ).model_dump(mode="json")


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
            "exact_entry_count": progress["nutrition"]["exact_entry_count"],
            "approximate_entry_count": progress["nutrition"]["approximate_entry_count"],
            "partial_entry_count": progress["nutrition"]["partial_entry_count"],
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
            "planning_review": build_weekly_planning_review(
                db,
                user,
                week_start=week_start,
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
        "progress_action_kind": row.progress_action_kind,
        "progress_action_completed_at": row.progress_action_completed_at,
        "created_at": row.created_at,
    }


def get_current_weekly_check_in(db: Session, user: User) -> dict:
    week_start, week_end, submitted_on = current_week_bounds(user)
    existing = (
        db.query(WeeklyCheckIn)
        .filter(WeeklyCheckIn.user_id == user.id, WeeklyCheckIn.week_start == week_start)
        .first()
    )
    if existing:
        summary = {
            **existing.summary,
            "nutrition": {
                **existing.summary.get("nutrition", {}),
                "planning_review": build_weekly_planning_review(
                    db,
                    user,
                    week_start=week_start,
                    period_end=submitted_on,
                ),
            },
        }
    else:
        summary = build_weekly_summary(db, user, week_start=week_start, period_end=submitted_on)
    return {
        "week_start": week_start,
        "week_end": week_end,
        "submitted_on": submitted_on,
        "timezone": get_user_timezone_name(user),
        "existing": serialize_weekly_check_in(existing) if existing else None,
        "summary": summary,
        "progress_action": build_progress_weekly_action(summary, existing=existing),
    }


def confirm_weekly_planning_review(
    db: Session,
    user: User,
    payload: WeeklyPlanningReviewConfirmRequest,
) -> dict:
    week_start, week_end, submitted_on = current_week_bounds(user)
    if payload.week_start != week_start:
        raise WeeklyCheckInConflictError("Недельный обзор устарел; обновите страницу")

    replayed = True
    try:
        db.query(User.id).filter(User.id == user.id).with_for_update().one()
        for adjustment in payload.adjustments:
            operation_key = _planning_operation_key(
                adjustment.source_date,
                adjustment.source_revision,
            )
            _, was_replayed = _operation(
                db,
                user,
                key=operation_key,
                fingerprint=_fingerprint(
                    {
                        "week_start": payload.week_start,
                        **adjustment.model_dump(mode="json"),
                    }
                ),
                kind="copy",
                target_date=adjustment.target_date,
            )
            if was_replayed:
                continue
            replayed = False
            try:
                copy_pending_plan_items(
                    db,
                    user,
                    source_date=adjustment.source_date,
                    target_date=adjustment.target_date,
                    expected_source_revision=adjustment.source_revision,
                    expected_target_revision=adjustment.target_revision,
                )
            except NutritionPlanError as exc:
                raise WeeklyCheckInConflictError(str(exc)) from exc

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "week_start": week_start,
        "week_end": week_end,
        "replayed": replayed,
        "planning_review": build_weekly_planning_review(
            db,
            user,
            week_start=week_start,
            period_end=submitted_on,
        ),
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
        progress_action_kind=(
            derive_progress_weekly_action_kind(summary) if payload.status == "completed" else "none"
        ),
        created_at=now_for_user_naive(user),
    )
    db.add(row)
    if payload.status == "completed":
        record_lifecycle_milestone(
            db,
            user,
            "weekly_review_completed",
            occurred_at=user_local_naive_to_utc_naive(row.created_at, user),
            day_scope=True,
        )
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
