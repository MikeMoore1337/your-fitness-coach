from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, cast

from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_for_user_naive, today_for_user
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.nutrition import EnergyCalibration, NutritionTarget
from fitminiapp_api.models.user import BodyMeasurement, User
from fitminiapp_api.schemas.nutrition import (
    EnergyCalibrationResponse,
    EnergyCalibrationStatus,
    EnergyCalibrationSufficiency,
)
from fitminiapp_api.services.diary_nutrition import aggregate_diary_entries
from fitminiapp_api.services.nutrition import (
    NutritionMacros,
    calculate_macros,
    create_nutrition_target_version,
    get_current_nutrition_target,
    nutrition_target_context,
)

RULESET_VERSION = "adaptive-energy-v1"
LOOKBACK_DAYS = 28
SMOOTHING_WINDOW_DAYS = 7
LIMITED_LOGGED_DAYS = 14
SUFFICIENT_LOGGED_DAYS = 21
LIMITED_WINDOW_WEIGHT_POINTS = 2
SUFFICIENT_WINDOW_WEIGHT_POINTS = 3
MAX_INTAKE_VARIATION = 0.35
MAX_WINDOW_WEIGHT_RANGE_PERCENT = 2.0
ENERGY_DENSITY_KCAL_PER_KG = 7700
BASE_UNCERTAINTY_KCAL = 250
MIN_SUPPORTED_EXPENDITURE_KCAL = 800
MAX_SUPPORTED_EXPENDITURE_KCAL = 6000
MIN_PROPOSAL_DIFFERENCE_KCAL = 100
MAX_PROPOSAL_STEP_KCAL = 200
HISTORY_LIMIT = 20

GOAL_MULTIPLIERS = {
    "fat_loss": 0.85,
    "recomposition": 1.0,
    "maintenance": 1.0,
    "muscle_gain": 1.05,
}


class EnergyCalibrationError(Exception):
    pass


class EnergyCalibrationNotFoundError(EnergyCalibrationError):
    pass


class EnergyCalibrationConflictError(EnergyCalibrationError):
    pass


@dataclass(frozen=True)
class CalibrationEvaluation:
    status: EnergyCalibrationStatus
    period_start: date
    period_end: date
    sufficiency_status: Literal["insufficient", "limited", "sufficient"]
    counters: dict[str, int | float]
    reason_keys: list[str]
    average_intake_kcal: int | None
    smoothed_start_weight_kg: float | None
    smoothed_end_weight_kg: float | None
    estimated_expenditure_kcal: int | None
    estimate_low_kcal: int | None
    estimate_high_kcal: int | None
    current_target_calories: int | None
    current_target_protein_g: int | None
    current_target_fat_g: int | None
    current_target_carbs_g: int | None
    target_saved_at: datetime | None
    proposed_target_calories: int | None
    proposed_target_protein_g: int | None
    proposed_target_fat_g: int | None
    proposed_target_carbs_g: int | None
    proposed_effective_from: date | None
    goal: str
    rationale_keys: list[str]


def _round_number(value: float) -> int:
    return max(0, math.floor(value + 0.5))


def _round_to_ten(value: float) -> int:
    return max(0, math.floor(value / 10 + 0.5) * 10)


def _round_to_fifty(value: float) -> int:
    return max(0, math.floor(value / 50 + 0.5) * 50)


def _median(values: Sequence[float]) -> float:
    return round(float(statistics.median(values)), 2)


def _variation(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean = statistics.fmean(values)
    return statistics.pstdev(values) / mean if len(values) > 1 and mean > 0 else 0.0


def _weight_range_percent(values: Sequence[float]) -> float:
    center = statistics.median(values)
    return (max(values) - min(values)) * 100 / center if center > 0 else 0.0


def _sufficiency(
    *,
    day_totals: Mapping[date, float],
    weights: Sequence[tuple[date, float]],
    period_start: date,
    period_end: date,
) -> tuple[str, dict[str, int | float], list[str], list[float], list[float]]:
    first_window_end = period_start + timedelta(days=SMOOTHING_WINDOW_DAYS - 1)
    last_window_start = period_end - timedelta(days=SMOOTHING_WINDOW_DAYS - 1)
    first_weights = [value for measured_on, value in weights if measured_on <= first_window_end]
    last_weights = [value for measured_on, value in weights if measured_on >= last_window_start]
    span_days = (weights[-1][0] - weights[0][0]).days if len(weights) > 1 else 0
    intake_values = list(day_totals.values())
    intake_variation = _variation(intake_values)
    first_range = _weight_range_percent(first_weights) if first_weights else 0.0
    last_range = _weight_range_percent(last_weights) if last_weights else 0.0
    counters: dict[str, int | float] = {
        "logged_day_count": len(day_totals),
        "eligible_day_count": LOOKBACK_DAYS,
        "required_logged_day_count": SUFFICIENT_LOGGED_DAYS,
        "weight_point_count": len(weights),
        "first_window_weight_point_count": len(first_weights),
        "last_window_weight_point_count": len(last_weights),
        "required_window_weight_point_count": SUFFICIENT_WINDOW_WEIGHT_POINTS,
        "weight_span_days": span_days,
        "intake_variation_percent": round(intake_variation * 100, 1),
        "first_window_weight_range_percent": round(first_range, 1),
        "last_window_weight_range_percent": round(last_range, 1),
    }

    essential_reasons: list[str] = []
    if len(day_totals) < LIMITED_LOGGED_DAYS:
        essential_reasons.append("too_few_logged_days")
    if len(first_weights) < LIMITED_WINDOW_WEIGHT_POINTS:
        essential_reasons.append("too_few_start_weight_points")
    if len(last_weights) < LIMITED_WINDOW_WEIGHT_POINTS:
        essential_reasons.append("too_few_end_weight_points")
    if essential_reasons:
        return "insufficient", counters, essential_reasons, first_weights, last_weights

    limited_reasons: list[str] = []
    if len(day_totals) < SUFFICIENT_LOGGED_DAYS:
        limited_reasons.append("logged_day_coverage_limited")
    if len(first_weights) < SUFFICIENT_WINDOW_WEIGHT_POINTS:
        limited_reasons.append("start_weight_coverage_limited")
    if len(last_weights) < SUFFICIENT_WINDOW_WEIGHT_POINTS:
        limited_reasons.append("end_weight_coverage_limited")
    if intake_variation > MAX_INTAKE_VARIATION:
        limited_reasons.append("intake_is_highly_variable")
    if max(first_range, last_range) > MAX_WINDOW_WEIGHT_RANGE_PERCENT:
        limited_reasons.append("weight_is_highly_variable")
    if limited_reasons:
        return "limited", counters, limited_reasons, first_weights, last_weights
    return "sufficient", counters, ["thresholds_met"], first_weights, last_weights


def evaluate_energy_calibration(
    *,
    target: NutritionTarget | None,
    day_totals: Mapping[date, float],
    weights: Sequence[tuple[date, float]],
    today: date,
) -> CalibrationEvaluation:
    period_end = today - timedelta(days=1)
    period_start = period_end - timedelta(days=LOOKBACK_DAYS - 1)
    filtered_days = {
        logged_on: float(total)
        for logged_on, total in day_totals.items()
        if period_start <= logged_on <= period_end and total >= 0
    }
    filtered_weights = sorted(
        (measured_on, float(value))
        for measured_on, value in weights
        if period_start <= measured_on <= period_end and value > 0
    )
    if target is None:
        return CalibrationEvaluation(
            status="insufficient",
            period_start=period_start,
            period_end=period_end,
            sufficiency_status="insufficient",
            counters={
                "logged_day_count": len(filtered_days),
                "eligible_day_count": LOOKBACK_DAYS,
                "weight_point_count": len(filtered_weights),
            },
            reason_keys=["nutrition_target_missing"],
            average_intake_kcal=None,
            smoothed_start_weight_kg=None,
            smoothed_end_weight_kg=None,
            estimated_expenditure_kcal=None,
            estimate_low_kcal=None,
            estimate_high_kcal=None,
            current_target_calories=None,
            current_target_protein_g=None,
            current_target_fat_g=None,
            current_target_carbs_g=None,
            target_saved_at=None,
            proposed_target_calories=None,
            proposed_target_protein_g=None,
            proposed_target_fat_g=None,
            proposed_target_carbs_g=None,
            proposed_effective_from=None,
            goal="maintenance",
            rationale_keys=["nutrition_target_missing"],
        )

    if target.goal not in GOAL_MULTIPLIERS or target.weight_kg is None:
        return CalibrationEvaluation(
            status="insufficient",
            period_start=period_start,
            period_end=period_end,
            sufficiency_status="insufficient",
            counters={
                "logged_day_count": len(filtered_days),
                "eligible_day_count": LOOKBACK_DAYS,
                "weight_point_count": len(filtered_weights),
            },
            reason_keys=["nutrition_target_context_missing"],
            average_intake_kcal=None,
            smoothed_start_weight_kg=None,
            smoothed_end_weight_kg=None,
            estimated_expenditure_kcal=None,
            estimate_low_kcal=None,
            estimate_high_kcal=None,
            current_target_calories=target.calories,
            current_target_protein_g=target.protein_g,
            current_target_fat_g=target.fat_g,
            current_target_carbs_g=target.carbs_g,
            target_saved_at=target.saved_at,
            proposed_target_calories=None,
            proposed_target_protein_g=None,
            proposed_target_fat_g=None,
            proposed_target_carbs_g=None,
            proposed_effective_from=None,
            goal=target.goal or "maintenance",
            rationale_keys=["nutrition_target_context_missing"],
        )

    sufficiency, counters, reason_keys, first_weights, last_weights = _sufficiency(
        day_totals=filtered_days,
        weights=filtered_weights,
        period_start=period_start,
        period_end=period_end,
    )
    if sufficiency == "insufficient":
        return CalibrationEvaluation(
            status="insufficient",
            period_start=period_start,
            period_end=period_end,
            sufficiency_status=cast(Literal["insufficient", "limited", "sufficient"], sufficiency),
            counters=counters,
            reason_keys=reason_keys,
            average_intake_kcal=None,
            smoothed_start_weight_kg=None,
            smoothed_end_weight_kg=None,
            estimated_expenditure_kcal=None,
            estimate_low_kcal=None,
            estimate_high_kcal=None,
            current_target_calories=target.calories,
            current_target_protein_g=target.protein_g,
            current_target_fat_g=target.fat_g,
            current_target_carbs_g=target.carbs_g,
            target_saved_at=target.saved_at,
            proposed_target_calories=None,
            proposed_target_protein_g=None,
            proposed_target_fat_g=None,
            proposed_target_carbs_g=None,
            proposed_effective_from=None,
            goal=target.goal,
            rationale_keys=reason_keys,
        )

    average_intake = _round_number(statistics.fmean(filtered_days.values()))
    start_weight = _median(first_weights)
    end_weight = _median(last_weights)
    trend_days = LOOKBACK_DAYS - SMOOTHING_WINDOW_DAYS
    daily_energy_store_change = (
        (end_weight - start_weight) * ENERGY_DENSITY_KCAL_PER_KG / trend_days
    )
    raw_estimated_expenditure = _round_to_ten(average_intake - daily_energy_store_change)
    estimate_outside_supported_range = not (
        MIN_SUPPORTED_EXPENDITURE_KCAL
        <= raw_estimated_expenditure
        <= MAX_SUPPORTED_EXPENDITURE_KCAL
    )
    estimated_expenditure = max(
        MIN_SUPPORTED_EXPENDITURE_KCAL,
        min(MAX_SUPPORTED_EXPENDITURE_KCAL, raw_estimated_expenditure),
    )
    if estimate_outside_supported_range:
        sufficiency = "limited"
        reason_keys = [*reason_keys, "estimate_outside_supported_range"]
    observed_variation = statistics.pstdev(filtered_days.values()) / math.sqrt(len(filtered_days))
    uncertainty = _round_to_ten(
        max(
            BASE_UNCERTAINTY_KCAL,
            average_intake * 0.10,
            observed_variation,
        )
    )
    estimate_low = max(MIN_SUPPORTED_EXPENDITURE_KCAL, estimated_expenditure - uncertainty)
    estimate_high = estimated_expenditure + uncertainty

    rationale_keys = ["logged_intake_average", "seven_day_weight_medians"]
    weight_change = end_weight - start_weight
    if abs(weight_change) < 0.1:
        rationale_keys.append("smoothed_weight_stable")
    elif weight_change < 0:
        rationale_keys.append("smoothed_weight_decreased")
    else:
        rationale_keys.append("smoothed_weight_increased")
    rationale_keys.extend(["energy_balance_estimate", f"goal_{target.goal}"])

    proposed_target: int | None = None
    proposed_macros: NutritionMacros | None = None
    status = "limited" if sufficiency == "limited" else "no_change"
    if sufficiency == "limited":
        rationale_keys.append("limited_data_no_proposal")
    else:
        goal_multiplier = GOAL_MULTIPLIERS[target.goal]
        target_range_low = _round_to_ten(estimate_low * goal_multiplier)
        target_range_high = _round_to_ten(estimate_high * goal_multiplier)
        desired_target = _round_to_fifty(estimated_expenditure * goal_multiplier)
        outside_range = (
            target.calories < target_range_low - MIN_PROPOSAL_DIFFERENCE_KCAL
            or target.calories > target_range_high + MIN_PROPOSAL_DIFFERENCE_KCAL
        )
        if outside_range:
            delta = max(
                -MAX_PROPOSAL_STEP_KCAL,
                min(MAX_PROPOSAL_STEP_KCAL, desired_target - target.calories),
            )
            proposed_target = _round_to_fifty(target.calories + delta)
            proposed_macros = calculate_macros(target.weight_kg, proposed_target, target.goal)
            if proposed_macros["macro_warning"]:
                macro_floor = proposed_macros["protein_g"] * 4 + proposed_macros["fat_g"] * 9
                proposed_target = math.ceil(macro_floor / 50) * 50
            if proposed_target != target.calories:
                proposed_macros = calculate_macros(target.weight_kg, proposed_target, target.goal)
                status = "pending"
                rationale_keys.append("gradual_target_change_proposed")
            else:
                proposed_target = None
                proposed_macros = None
        if proposed_target is None:
            rationale_keys.append("current_target_within_range")

    return CalibrationEvaluation(
        status=cast(EnergyCalibrationStatus, status),
        period_start=period_start,
        period_end=period_end,
        sufficiency_status=cast(Literal["insufficient", "limited", "sufficient"], sufficiency),
        counters=counters,
        reason_keys=reason_keys,
        average_intake_kcal=average_intake,
        smoothed_start_weight_kg=start_weight,
        smoothed_end_weight_kg=end_weight,
        estimated_expenditure_kcal=estimated_expenditure,
        estimate_low_kcal=estimate_low,
        estimate_high_kcal=estimate_high,
        current_target_calories=target.calories,
        current_target_protein_g=target.protein_g,
        current_target_fat_g=target.fat_g,
        current_target_carbs_g=target.carbs_g,
        target_saved_at=target.saved_at,
        proposed_target_calories=proposed_target,
        proposed_target_protein_g=(
            proposed_macros["protein_g"] if proposed_macros is not None else None
        ),
        proposed_target_fat_g=(proposed_macros["fat_g"] if proposed_macros is not None else None),
        proposed_target_carbs_g=(
            proposed_macros["carbs_g"] if proposed_macros is not None else None
        ),
        proposed_effective_from=today if proposed_target is not None else None,
        goal=target.goal,
        rationale_keys=rationale_keys,
    )


def _rationale(
    *,
    average_intake_kcal: int | None,
    start_weight: float | None,
    end_weight: float | None,
    goal: str,
    proposed_target: int | None,
    sufficiency_status: str,
) -> list[str]:
    if average_intake_kcal is None or start_weight is None or end_weight is None:
        return ["Пока недостаточно заполненных дней питания и регулярных замеров массы для оценки."]
    goal_text = {
        "fat_loss": "снижение жира",
        "muscle_gain": "набор мышечной массы",
        "maintenance": "поддержание",
        "recomposition": "рекомпозиция",
    }[goal]
    result = [
        f"Среднее потребление по заполненным дням: {average_intake_kcal} ккал.",
        (
            "Для тренда использованы медианы массы за первую и последнюю семидневки: "
            f"{start_weight:.2f} → {end_weight:.2f} кг."
        ),
        (
            "Оценка расхода рассчитана из потребления и сглаженного изменения массы; "
            "калории смарт-часов не используются."
        ),
        f"Предложение учитывает текущую цель: {goal_text}.",
    ]
    if sufficiency_status == "limited":
        result.append("Данные пока нестабильны: показываем ориентир, но не предлагаем менять цель.")
    elif proposed_target is None:
        result.append("Текущая калорийность находится в осторожном расчётном диапазоне.")
    else:
        result.append(
            "Изменение ограничено шагом 200 ккал и применяется только после подтверждения."
        )
    return result


def _response_from_evaluation(evaluation: CalibrationEvaluation) -> EnergyCalibrationResponse:
    return EnergyCalibrationResponse(
        status=evaluation.status,
        ruleset_version=RULESET_VERSION,
        period_start=evaluation.period_start,
        period_end=evaluation.period_end,
        sufficiency=EnergyCalibrationSufficiency(
            status=evaluation.sufficiency_status,
            counters=evaluation.counters,
            reason_keys=evaluation.reason_keys,
        ),
        average_intake_kcal=evaluation.average_intake_kcal,
        smoothed_start_weight_kg=evaluation.smoothed_start_weight_kg,
        smoothed_end_weight_kg=evaluation.smoothed_end_weight_kg,
        estimated_expenditure_kcal=evaluation.estimated_expenditure_kcal,
        estimate_low_kcal=evaluation.estimate_low_kcal,
        estimate_high_kcal=evaluation.estimate_high_kcal,
        goal=evaluation.goal,
        current_target_calories=evaluation.current_target_calories,
        current_target_protein_g=evaluation.current_target_protein_g,
        current_target_fat_g=evaluation.current_target_fat_g,
        current_target_carbs_g=evaluation.current_target_carbs_g,
        proposed_target_calories=evaluation.proposed_target_calories,
        proposed_target_protein_g=evaluation.proposed_target_protein_g,
        proposed_target_fat_g=evaluation.proposed_target_fat_g,
        proposed_target_carbs_g=evaluation.proposed_target_carbs_g,
        proposed_effective_from=evaluation.proposed_effective_from,
        rationale=_rationale(
            average_intake_kcal=evaluation.average_intake_kcal,
            start_weight=evaluation.smoothed_start_weight_kg,
            end_weight=evaluation.smoothed_end_weight_kg,
            goal=evaluation.goal,
            proposed_target=evaluation.proposed_target_calories,
            sufficiency_status=evaluation.sufficiency_status,
        ),
    )


def _response_from_record(
    record: EnergyCalibration,
    *,
    target: NutritionTarget | None = None,
    proposed_effective_from: date | None = None,
) -> EnergyCalibrationResponse:
    current_macros: NutritionMacros | None = None
    proposed_macros: NutritionMacros | None = None
    if target is not None and target.weight_kg is not None and record.goal in GOAL_MULTIPLIERS:
        current_macros = calculate_macros(
            target.weight_kg,
            record.previous_target_calories,
            record.goal,
        )
        if record.proposed_target_calories is not None:
            proposed_macros = calculate_macros(
                target.weight_kg,
                record.proposed_target_calories,
                record.goal,
            )
    return EnergyCalibrationResponse(
        id=record.id,
        status=cast(EnergyCalibrationStatus, record.status),
        ruleset_version=record.ruleset_version,
        period_start=record.period_start,
        period_end=record.period_end,
        sufficiency=EnergyCalibrationSufficiency(
            status=cast(
                Literal["insufficient", "limited", "sufficient"],
                record.sufficiency_status,
            ),
            counters=record.sufficiency_counters,
            reason_keys=record.sufficiency_reason_keys,
        ),
        average_intake_kcal=record.average_intake_kcal,
        smoothed_start_weight_kg=float(record.smoothed_start_weight_kg),
        smoothed_end_weight_kg=float(record.smoothed_end_weight_kg),
        estimated_expenditure_kcal=record.estimated_expenditure_kcal,
        estimate_low_kcal=record.estimate_low_kcal,
        estimate_high_kcal=record.estimate_high_kcal,
        goal=record.goal,
        current_target_calories=record.previous_target_calories,
        current_target_protein_g=(
            current_macros["protein_g"] if current_macros is not None else None
        ),
        current_target_fat_g=(current_macros["fat_g"] if current_macros is not None else None),
        current_target_carbs_g=(current_macros["carbs_g"] if current_macros is not None else None),
        proposed_target_calories=record.proposed_target_calories,
        proposed_target_protein_g=(
            proposed_macros["protein_g"] if proposed_macros is not None else None
        ),
        proposed_target_fat_g=(proposed_macros["fat_g"] if proposed_macros is not None else None),
        proposed_target_carbs_g=(
            proposed_macros["carbs_g"] if proposed_macros is not None else None
        ),
        proposed_effective_from=proposed_effective_from,
        rationale=_rationale(
            average_intake_kcal=record.average_intake_kcal,
            start_weight=float(record.smoothed_start_weight_kg),
            end_weight=float(record.smoothed_end_weight_kg),
            goal=record.goal,
            proposed_target=record.proposed_target_calories,
            sufficiency_status=record.sufficiency_status,
        ),
        created_at=record.created_at,
        decided_at=record.decided_at,
    )


def _load_inputs(
    db: Session,
    user: User,
    period_start: date,
    period_end: date,
) -> tuple[dict[date, float], list[tuple[date, float]]]:
    diary_entries = (
        db.query(FoodDiaryEntry)
        .join(
            FoodDiaryDayStatus,
            (FoodDiaryDayStatus.user_id == FoodDiaryEntry.user_id)
            & (FoodDiaryDayStatus.diary_date == FoodDiaryEntry.diary_date),
        )
        .filter(
            FoodDiaryEntry.user_id == user.id,
            FoodDiaryEntry.diary_date.between(period_start, period_end),
            FoodDiaryDayStatus.status == "complete",
        )
        .order_by(FoodDiaryEntry.diary_date.asc(), FoodDiaryEntry.id.asc())
        .all()
    )
    diary_totals = aggregate_diary_entries(diary_entries)
    fasted_dates = (
        db.query(FoodDiaryDayStatus.diary_date)
        .filter(
            FoodDiaryDayStatus.user_id == user.id,
            FoodDiaryDayStatus.diary_date.between(period_start, period_end),
            FoodDiaryDayStatus.status == "fasted",
        )
        .all()
    )
    weight_rows = (
        db.query(BodyMeasurement.measured_on, BodyMeasurement.weight_kg)
        .filter(
            BodyMeasurement.user_id == user.id,
            BodyMeasurement.weight_kg.is_not(None),
            BodyMeasurement.measured_on.between(period_start, period_end),
        )
        .order_by(BodyMeasurement.measured_on.asc(), BodyMeasurement.id.asc())
        .all()
    )
    return (
        {
            **{
                diary_date: float(total.calories)
                for (entry_user_id, diary_date), total in diary_totals.items()
                if entry_user_id == user.id and total.calories is not None
            },
            **{logged_on: 0.0 for (logged_on,) in fasted_dates},
        },
        [(measured_on, float(weight)) for measured_on, weight in weight_rows if weight is not None],
    )


def preview_energy_calibration(db: Session, user: User) -> EnergyCalibrationResponse:
    today = today_for_user(user)
    period_end = today - timedelta(days=1)
    period_start = period_end - timedelta(days=LOOKBACK_DAYS - 1)
    target = get_current_nutrition_target(db, user.id)
    day_totals, weights = _load_inputs(db, user, period_start, period_end)
    evaluation = evaluate_energy_calibration(
        target=target,
        day_totals=day_totals,
        weights=weights,
        today=today,
    )
    if evaluation.estimated_expenditure_kcal is None:
        return _response_from_evaluation(evaluation)
    if evaluation.target_saved_at is None:
        raise EnergyCalibrationError("У цели питания отсутствует время последнего изменения")

    db.query(EnergyCalibration).filter(
        EnergyCalibration.user_id == user.id,
        EnergyCalibration.status == "pending",
    ).update(
        {
            EnergyCalibration.status: "superseded",
            EnergyCalibration.decided_at: now_for_user_naive(user),
        },
        synchronize_session=False,
    )
    record = EnergyCalibration(
        user_id=user.id,
        ruleset_version=RULESET_VERSION,
        status=evaluation.status,
        sufficiency_status=evaluation.sufficiency_status,
        period_start=evaluation.period_start,
        period_end=evaluation.period_end,
        goal=evaluation.goal,
        logged_day_count=int(evaluation.counters["logged_day_count"]),
        eligible_day_count=int(evaluation.counters["eligible_day_count"]),
        weight_point_count=int(evaluation.counters["weight_point_count"]),
        weight_span_days=int(evaluation.counters["weight_span_days"]),
        average_intake_kcal=evaluation.average_intake_kcal,
        smoothed_start_weight_kg=evaluation.smoothed_start_weight_kg,
        smoothed_end_weight_kg=evaluation.smoothed_end_weight_kg,
        estimated_expenditure_kcal=evaluation.estimated_expenditure_kcal,
        estimate_low_kcal=evaluation.estimate_low_kcal,
        estimate_high_kcal=evaluation.estimate_high_kcal,
        previous_target_calories=evaluation.current_target_calories,
        previous_target_saved_at=evaluation.target_saved_at,
        proposed_target_calories=evaluation.proposed_target_calories,
        sufficiency_counters=evaluation.counters,
        sufficiency_reason_keys=evaluation.reason_keys,
        rationale_keys=evaluation.rationale_keys,
        created_at=now_for_user_naive(user),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _response_from_record(record, target=target, proposed_effective_from=today)


def decide_energy_calibration(
    db: Session,
    user: User,
    calibration_id: int,
    decision: str,
) -> EnergyCalibrationResponse:
    record = (
        db.query(EnergyCalibration)
        .filter(
            EnergyCalibration.id == calibration_id,
            EnergyCalibration.user_id == user.id,
        )
        .with_for_update()
        .first()
    )
    if record is None:
        raise EnergyCalibrationNotFoundError("Калибровка не найдена")
    resolved_status = "accepted" if decision == "accept" else "rejected"
    if record.status == resolved_status:
        return _response_from_record(
            record,
            target=get_current_nutrition_target(db, user.id),
            proposed_effective_from=(
                record.decided_at.date() if record.decided_at is not None else today_for_user(user)
            ),
        )
    if record.status != "pending" or record.proposed_target_calories is None:
        raise EnergyCalibrationConflictError("Это предложение уже не ожидает решения")

    decided_at = now_for_user_naive(user)
    if decision == "reject":
        record.status = "rejected"
        record.decided_at = decided_at
        db.commit()
        db.refresh(record)
        return _response_from_record(
            record,
            target=get_current_nutrition_target(db, user.id),
            proposed_effective_from=today_for_user(user),
        )

    target = get_current_nutrition_target(db, user.id, for_update=True)
    if (
        target is None
        or target.calories != record.previous_target_calories
        or target.goal != record.goal
        or target.saved_at != record.previous_target_saved_at
    ):
        record.status = "superseded"
        record.decided_at = decided_at
        db.commit()
        raise EnergyCalibrationConflictError(
            "Цель питания уже изменилась; выполните новую проверку по истории"
        )

    if target.weight_kg is None or target.goal not in GOAL_MULTIPLIERS:
        record.status = "superseded"
        record.decided_at = decided_at
        db.commit()
        raise EnergyCalibrationConflictError(
            "Для текущей цели больше нет данных калькулятора; выполните новую проверку"
        )
    macros = calculate_macros(target.weight_kg, record.proposed_target_calories, target.goal)
    context = nutrition_target_context(target)
    context.update(
        tdee=record.estimated_expenditure_kcal,
        calories=record.proposed_target_calories,
        protein_g=macros["protein_g"],
        fat_g=macros["fat_g"],
        carbs_g=macros["carbs_g"],
    )
    create_nutrition_target_version(
        db,
        target_user=user,
        changed_by=user,
        source="adaptive",
        effective_from=today_for_user(user),
        values=context,
        note="Принято предложение адаптивной калибровки",
    )
    record.status = "accepted"
    record.decided_at = decided_at
    db.commit()
    db.refresh(record)
    return _response_from_record(
        record,
        target=target,
        proposed_effective_from=today_for_user(user),
    )


def list_energy_calibrations(db: Session, user: User) -> list[EnergyCalibrationResponse]:
    rows = (
        db.query(EnergyCalibration)
        .filter(EnergyCalibration.user_id == user.id)
        .order_by(EnergyCalibration.created_at.desc(), EnergyCalibration.id.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    return [_response_from_record(row) for row in rows]


def inspect_energy_calibration(db: Session, user: User) -> EnergyCalibrationResponse:
    """Build the current deterministic result without creating history."""
    today = today_for_user(user)
    period_end = today - timedelta(days=1)
    period_start = period_end - timedelta(days=LOOKBACK_DAYS - 1)
    target = get_current_nutrition_target(db, user.id)
    day_totals, weights = _load_inputs(db, user, period_start, period_end)
    evaluation = evaluate_energy_calibration(
        target=target,
        day_totals=day_totals,
        weights=weights,
        today=today,
    )
    return _response_from_evaluation(evaluation)


def get_energy_calibration_snapshot(
    db: Session,
    user: User,
    calibration_id: int,
) -> EnergyCalibrationResponse:
    record = (
        db.query(EnergyCalibration)
        .filter(
            EnergyCalibration.id == calibration_id,
            EnergyCalibration.user_id == user.id,
        )
        .first()
    )
    if record is None:
        raise EnergyCalibrationNotFoundError("Калибровка не найдена")
    target = get_current_nutrition_target(db, user.id)
    effective_from = (
        record.decided_at.date()
        if record.status == "accepted" and record.decided_at is not None
        else today_for_user(user)
    )
    return _response_from_record(
        record,
        target=target,
        proposed_effective_from=effective_from,
    )
