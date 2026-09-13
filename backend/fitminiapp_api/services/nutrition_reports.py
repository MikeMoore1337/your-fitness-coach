from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import today_for_user
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.hydration import HydrationEntry, HydrationGoal
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.progress import NutritionReportPeriod
from fitminiapp_api.services.diary_nutrition import aggregate_diary_entries
from fitminiapp_api.services.period_bounds import (
    PeriodBoundsError,
    ReportBounds,
    resolve_report_bounds,
)
from fitminiapp_api.services.progress import is_calorie_target_met, is_protein_target_met

METRICS = ("calories", "protein_g", "fat_g", "carbs_g")

NutritionReportError = PeriodBoundsError


@dataclass(frozen=True)
class AggregatedDiaryDay:
    diary_date: date
    calories: Decimal | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    carbs_g: Decimal | None
    has_entries: bool


def _aggregated_diary_days(
    db: Session,
    user_id: int,
    bounds: ReportBounds,
) -> dict[date, AggregatedDiaryDay]:
    entries = (
        db.query(FoodDiaryEntry)
        .filter(
            FoodDiaryEntry.user_id == user_id,
            FoodDiaryEntry.diary_date.between(bounds.start, bounds.end),
        )
        .order_by(FoodDiaryEntry.diary_date.asc(), FoodDiaryEntry.id.asc())
        .all()
    )
    totals_by_key = aggregate_diary_entries(entries)
    result: dict[date, AggregatedDiaryDay] = {}
    for (entry_user_id, diary_date), totals in sorted(totals_by_key.items()):
        if entry_user_id != user_id:
            continue
        result[diary_date] = AggregatedDiaryDay(
            diary_date=diary_date,
            calories=totals.calories,
            protein_g=None if totals.missing_macros else totals.protein_g,
            fat_g=None if totals.missing_macros else totals.fat_g,
            carbs_g=None if totals.missing_macros else totals.carbs_g,
            has_entries=True,
        )
    return result


def _effective_target(
    targets: list[NutritionTarget],
    diary_date: date,
) -> NutritionTarget | None:
    return next(
        (
            target
            for target in targets
            if target.effective_from <= diary_date
            and (target.effective_to is None or diary_date < target.effective_to)
        ),
        None,
    )


def _effective_hydration_goal(goals: list[HydrationGoal], diary_date: date) -> HydrationGoal | None:
    return next(
        (
            goal
            for goal in goals
            if goal.effective_from <= diary_date
            and (goal.effective_to is None or diary_date < goal.effective_to)
        ),
        None,
    )


def _metric_summary(points: list[dict], metric: str) -> dict:
    values = [point[metric] for point in points if point[metric] is not None]
    if not values:
        return {"average": None, "minimum": None, "maximum": None, "sample_days": 0}
    return {
        "average": round(sum(values) / len(values), 1),
        "minimum": round(min(values), 1),
        "maximum": round(max(values), 1),
        "sample_days": len(values),
    }


def _target_comparison(points: list[dict], metric: str, target_metric: str) -> dict:
    comparable = [
        point for point in points if point[metric] is not None and point[target_metric] is not None
    ]
    if not comparable:
        return {
            "average_actual": None,
            "average_target": None,
            "average_deviation": None,
            "evaluated_days": 0,
        }
    actual = sum(point[metric] for point in comparable) / len(comparable)
    target = sum(point[target_metric] for point in comparable) / len(comparable)
    return {
        "average_actual": round(actual, 1),
        "average_target": round(target, 1),
        "average_deviation": round(actual - target, 1),
        "evaluated_days": len(comparable),
    }


def build_nutrition_report(
    db: Session,
    user: User,
    period: NutritionReportPeriod,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    bounds = resolve_report_bounds(user, period, date_from=date_from, date_to=date_to)
    today = today_for_user(user)
    diary_by_date = _aggregated_diary_days(db, user.id, bounds)
    statuses = {
        row.diary_date: row.status
        for row in db.query(FoodDiaryDayStatus)
        .filter(
            FoodDiaryDayStatus.user_id == user.id,
            FoodDiaryDayStatus.diary_date.between(bounds.start, bounds.end),
        )
        .all()
    }
    targets = (
        db.query(NutritionTarget)
        .filter(
            NutritionTarget.user_id == user.id,
            NutritionTarget.effective_from <= bounds.end,
            or_(
                NutritionTarget.effective_to.is_(None), NutritionTarget.effective_to > bounds.start
            ),
        )
        .order_by(NutritionTarget.effective_from.desc(), NutritionTarget.id.desc())
        .all()
    )
    hydration_rows = (
        db.query(HydrationEntry.diary_date, func.sum(HydrationEntry.volume_ml).label("total_ml"))
        .filter(
            HydrationEntry.user_id == user.id,
            HydrationEntry.diary_date.between(bounds.start, bounds.end),
        )
        .group_by(HydrationEntry.diary_date)
        .all()
    )
    hydration_by_date = {row.diary_date: int(row.total_ml) for row in hydration_rows}
    hydration_goals = (
        db.query(HydrationGoal)
        .filter(
            HydrationGoal.user_id == user.id,
            HydrationGoal.effective_from <= bounds.end,
            or_(HydrationGoal.effective_to.is_(None), HydrationGoal.effective_to > bounds.start),
        )
        .order_by(HydrationGoal.effective_from.desc(), HydrationGoal.id.desc())
        .all()
    )
    effective_change_dates = {
        target.effective_from
        for target in targets
        if bounds.start <= target.effective_from <= bounds.end
        and (target.effective_to is None or target.effective_to > target.effective_from)
    }

    daily: list[dict] = []
    logged_points: list[dict] = []
    for offset in range((bounds.end - bounds.start).days + 1):
        diary_date = bounds.start + timedelta(days=offset)
        aggregate = diary_by_date.get(diary_date)
        explicit_status = statuses.get(diary_date)
        status = explicit_status or ("incomplete" if aggregate else "missing")
        if status == "fasted" and aggregate is None:
            aggregate = AggregatedDiaryDay(
                diary_date=diary_date,
                calories=Decimal(0),
                protein_g=Decimal(0),
                fat_g=Decimal(0),
                carbs_g=Decimal(0),
                has_entries=False,
            )
        target = _effective_target(targets, diary_date)
        hydration_goal = _effective_hydration_goal(hydration_goals, diary_date)
        hydration_target_ml = (
            hydration_goal.target_ml
            if hydration_goal is not None and hydration_goal.status == "enabled"
            else None
        )
        hydration_ml = hydration_by_date.get(diary_date)
        is_logged = status in {"complete", "fasted"}
        actual = {
            metric: round(float(getattr(aggregate, metric)), 1)
            if aggregate is not None and getattr(aggregate, metric) is not None
            else None
            for metric in METRICS
        }
        target_values = {
            "target_calories": target.calories if target else None,
            "target_protein_g": target.protein_g if target else None,
            "target_fat_g": target.fat_g if target else None,
            "target_carbs_g": target.carbs_g if target else None,
        }
        comparison_actual = actual if is_logged else dict.fromkeys(METRICS)
        point = {
            "diary_date": diary_date,
            "status": status,
            "is_current_day": diary_date == today,
            **actual,
            **target_values,
            "calorie_deviation": (
                round(comparison_actual["calories"] - target.calories, 1)
                if comparison_actual["calories"] is not None and target
                else None
            ),
            "protein_deviation_g": (
                round(comparison_actual["protein_g"] - target.protein_g, 1)
                if comparison_actual["protein_g"] is not None and target
                else None
            ),
            "fat_deviation_g": (
                round(comparison_actual["fat_g"] - target.fat_g, 1)
                if comparison_actual["fat_g"] is not None and target
                else None
            ),
            "carbs_deviation_g": (
                round(comparison_actual["carbs_g"] - target.carbs_g, 1)
                if comparison_actual["carbs_g"] is not None and target
                else None
            ),
            "within_calorie_tolerance": (
                is_calorie_target_met(Decimal(str(comparison_actual["calories"])), target.calories)
                if comparison_actual["calories"] is not None and target
                else None
            ),
            "meets_protein_target": (
                is_protein_target_met(
                    Decimal(str(comparison_actual["protein_g"])), target.protein_g
                )
                if comparison_actual["protein_g"] is not None and target
                else None
            ),
            "target_changed": diary_date in effective_change_dates,
            "hydration_ml": hydration_ml,
            "hydration_target_ml": hydration_target_ml,
            "hydration_progress_percent": (
                round(hydration_ml * 100 / hydration_target_ml, 1)
                if hydration_ml is not None and hydration_target_ml
                else None
            ),
        }
        daily.append(point)
        if is_logged:
            logged_points.append({**comparison_actual, **target_values, **point})

    counts = {
        status: sum(point["status"] == status for point in daily) for status in statuses_set()
    }
    logged_days = counts["complete"] + counts["fasted"]
    calorie_evaluated = [point for point in daily if point["within_calorie_tolerance"] is not None]
    protein_evaluated = [point for point in daily if point["meets_protein_target"] is not None]
    current_day = next((point for point in daily if point["is_current_day"]), None)
    summary = {
        "logged_days": logged_days,
        "eligible_days": len(daily),
        "coverage_percent": round(logged_days * 100 / len(daily), 1),
        "complete_days": counts["complete"],
        "incomplete_days": counts["incomplete"],
        "fasted_days": counts["fasted"],
        "missing_days": counts["missing"],
        "current_day_status": current_day["status"] if current_day else None,
        **{metric: _metric_summary(logged_points, metric) for metric in METRICS},
        "calorie_comparison": _target_comparison(logged_points, "calories", "target_calories"),
        "protein_comparison": _target_comparison(logged_points, "protein_g", "target_protein_g"),
        "fat_comparison": _target_comparison(logged_points, "fat_g", "target_fat_g"),
        "carbs_comparison": _target_comparison(logged_points, "carbs_g", "target_carbs_g"),
        "days_within_calorie_tolerance": sum(
            point["within_calorie_tolerance"] is True for point in calorie_evaluated
        ),
        "calorie_tolerance_evaluated_days": len(calorie_evaluated),
        "days_meeting_protein_target": sum(
            point["meets_protein_target"] is True for point in protein_evaluated
        ),
        "protein_target_evaluated_days": len(protein_evaluated),
    }
    target_changes = [
        {
            "effective_from": target.effective_from,
            "source": target.source,
            "calories": target.calories,
            "protein_g": target.protein_g,
            "fat_g": target.fat_g,
            "carbs_g": target.carbs_g,
        }
        for target in sorted(targets, key=lambda item: (item.effective_from, item.id))
        if target.effective_from in effective_change_dates
    ]
    hydration_visible = bool(hydration_by_date or hydration_goals)
    hydration_daily_values = [
        point["hydration_ml"] for point in daily if point["hydration_ml"] is not None
    ]
    hydration_comparable = [
        point
        for point in daily
        if point["hydration_ml"] is not None and point["hydration_target_ml"] is not None
    ]
    trend_ml = None
    if len(hydration_daily_values) >= 2:
        edge = min(3, len(hydration_daily_values) // 2)
        trend_ml = round(
            sum(hydration_daily_values[-edge:]) / edge - sum(hydration_daily_values[:edge]) / edge,
            1,
        )
    hydration_summary = (
        {
            "total_ml": sum(hydration_daily_values),
            "average_ml": (
                round(sum(hydration_daily_values) / len(hydration_daily_values), 1)
                if hydration_daily_values
                else None
            ),
            "logged_days": len(hydration_daily_values),
            "eligible_days": len(daily),
            "coverage_percent": round(len(hydration_daily_values) * 100 / len(daily), 1),
            "days_meeting_goal": sum(
                point["hydration_ml"] >= point["hydration_target_ml"]
                for point in hydration_comparable
            ),
            "goal_evaluated_days": len(hydration_comparable),
            "trend_ml": trend_ml,
        }
        if hydration_visible
        else None
    )
    return {
        "period": bounds.period,
        "period_start": bounds.start,
        "period_end": bounds.end,
        "timezone": user.profile.timezone
        if user.profile and user.profile.timezone
        else "Europe/Moscow",
        "summary": summary,
        "daily": daily,
        "target_changes": target_changes,
        "hydration": hydration_summary,
    }


def statuses_set() -> tuple[str, ...]:
    return "complete", "incomplete", "fasted", "missing"


def _safe_csv_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def nutrition_report_csv(report: dict) -> str:
    columns = [
        "row_type",
        "period_start",
        "period_end",
        "diary_date",
        "day_status",
        "is_current_day",
        "calories_kcal",
        "protein_g",
        "fat_g",
        "carbs_g",
        "target_calories_kcal",
        "target_protein_g",
        "target_fat_g",
        "target_carbs_g",
        "calorie_deviation_kcal",
        "protein_deviation_g",
        "fat_deviation_g",
        "carbs_deviation_g",
        "within_calorie_tolerance",
        "meets_protein_target",
        "target_changed",
        "hydration_ml",
        "hydration_target_ml",
        "hydration_progress_percent",
        "summary_logged_days",
        "summary_eligible_days",
        "summary_coverage_percent",
        "summary_hydration_total_ml",
        "summary_hydration_average_ml",
        "summary_hydration_coverage_percent",
        "summary_hydration_trend_ml",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    summary = report["summary"]
    hydration = report.get("hydration")
    writer.writerow(
        {
            "row_type": "summary",
            "period_start": report["period_start"],
            "period_end": report["period_end"],
            "summary_logged_days": summary["logged_days"],
            "summary_eligible_days": summary["eligible_days"],
            "summary_coverage_percent": summary["coverage_percent"],
            "summary_hydration_total_ml": hydration["total_ml"] if hydration else None,
            "summary_hydration_average_ml": hydration["average_ml"] if hydration else None,
            "summary_hydration_coverage_percent": (
                hydration["coverage_percent"] if hydration else None
            ),
            "summary_hydration_trend_ml": hydration["trend_ml"] if hydration else None,
        }
    )
    for point in report["daily"]:
        row = {
            "row_type": "daily",
            "period_start": report["period_start"],
            "period_end": report["period_end"],
            "diary_date": point["diary_date"],
            "day_status": point["status"],
            "is_current_day": point["is_current_day"],
            "calories_kcal": point["calories"],
            "protein_g": point["protein_g"],
            "fat_g": point["fat_g"],
            "carbs_g": point["carbs_g"],
            "target_calories_kcal": point["target_calories"],
            "target_protein_g": point["target_protein_g"],
            "target_fat_g": point["target_fat_g"],
            "target_carbs_g": point["target_carbs_g"],
            "calorie_deviation_kcal": point["calorie_deviation"],
            "protein_deviation_g": point["protein_deviation_g"],
            "fat_deviation_g": point["fat_deviation_g"],
            "carbs_deviation_g": point["carbs_deviation_g"],
            "within_calorie_tolerance": point["within_calorie_tolerance"],
            "meets_protein_target": point["meets_protein_target"],
            "target_changed": point["target_changed"],
            "hydration_ml": point["hydration_ml"],
            "hydration_target_ml": point["hydration_target_ml"],
            "hydration_progress_percent": point["hydration_progress_percent"],
        }
        writer.writerow({key: _safe_csv_value(value) for key, value in row.items()})
    return output.getvalue()
