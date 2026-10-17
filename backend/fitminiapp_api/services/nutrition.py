import math
from datetime import date
from typing import Literal, TypedDict, cast

from pydantic import ValidationError
from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.core.timezone import (
    now_for_user_naive,
    today_for_user,
)
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.schemas.nutrition import (
    CardioIntensity,
    CardioTraining,
    NutritionAssignedByResponse,
    NutritionManualTargetSave,
    NutritionTargetResponse,
    NutritionTargetSave,
)
from fitminiapp_api.services.notifications import queue_notification
from fitminiapp_api.services.profile import ensure_profile

VALID_SEXES = {"male", "female"}
VALID_GOALS = {"fat_loss", "muscle_gain", "maintenance", "recomposition"}
LEGACY_ACTIVITY_COEFFICIENTS = {
    "sedentary": 1.2,
    "low": 1.3,
    "moderate": 1.4,
    "high": 1.5,
}
ACTIVITY_COEFFICIENTS = {
    "mostly_sitting": {
        "up_to_4000": 1.2,
        "from_4000_to_7000": 1.25,
        "from_7000_to_10000": 1.3,
        "from_10000_to_14000": 1.35,
        "over_14000": 1.4,
        "unknown": 1.2,
    },
    "mixed": {
        "up_to_4000": 1.25,
        "from_4000_to_7000": 1.3,
        "from_7000_to_10000": 1.35,
        "from_10000_to_14000": 1.4,
        "over_14000": 1.45,
        "unknown": 1.3,
    },
    "mostly_on_feet": {
        "up_to_4000": 1.3,
        "from_4000_to_7000": 1.35,
        "from_7000_to_10000": 1.4,
        "from_10000_to_14000": 1.45,
        "over_14000": 1.5,
        "unknown": 1.4,
    },
    "physical_work": {
        "up_to_4000": 1.4,
        "from_4000_to_7000": 1.45,
        "from_7000_to_10000": 1.5,
        "from_10000_to_14000": 1.55,
        "over_14000": 1.6,
        "unknown": 1.5,
    },
}
LEGACY_DAILY_ROUTINES = {
    "sedentary": "mostly_sitting",
    "low": "mixed",
    "moderate": "mostly_on_feet",
    "high": "physical_work",
}
STRENGTH_MET_VALUES = {
    "calm": 3.5,
    "regular": 5.0,
    "heavy": 5.0,
    "dense": 6.0,
    "circuit": 7.0,
}
STRENGTH_REST_ADJUSTMENTS = {
    "under_60": 0.5,
    "one_to_two": 0.25,
    "two_to_three": 0.0,
    "over_three": -0.5,
    "varied": 0.0,
}
CARDIO_BASE_MET_VALUES = {
    "walking": 3.5,
    "running": 8.0,
    "elliptical": 5.0,
    "stationary_bike": 5.5,
    "cycling": 6.0,
    "rowing": 6.0,
    "stepper": 6.0,
    "swimming": 6.0,
    "other": 5.0,
}
CARDIO_INTENSITY_MULTIPLIERS = {
    "very_light": 0.7,
    "light": 0.85,
    "moderate": 1.0,
    "hard": 1.2,
    "very_hard": 1.4,
}
LEGACY_CARDIO_INTENSITIES = {"low": "light", "moderate": "moderate", "high": "hard"}
GOAL_MULTIPLIERS = {
    "fat_loss": 0.85,
    "recomposition": 0.95,
    "maintenance": 1.0,
    "muscle_gain": 1.05,
}
NUTRITION_INPUT_FIELDS = (
    "sex",
    "weight_kg",
    "height_cm",
    "age",
    "daily_routine",
    "steps_range",
    "strength_trainings_per_week",
    "strength_training_duration_minutes",
    "strength_training_type",
    "strength_rest",
    "cardio_trainings",
    "goal",
)
NUTRITION_REQUIRED_INPUT_FIELDS = tuple(
    field for field in NUTRITION_INPUT_FIELDS if field != "strength_rest"
)
NUTRITION_CONTEXT_FIELDS = (
    "sex",
    "weight_kg",
    "height_cm",
    "age",
    "daily_activity_level",
    "daily_routine",
    "steps_range",
    "strength_trainings_per_week",
    "strength_training_duration_minutes",
    "strength_training_type",
    "strength_rest",
    "cardio_trainings_per_week",
    "cardio_training_duration_minutes",
    "cardio_intensity",
    "cardio_trainings",
    "goal",
    "bmr",
    "tdee",
)
MANUAL_ENERGY_MISMATCH_MIN_KCAL = 100
MANUAL_ENERGY_MISMATCH_RATIO = 0.10


class NutritionError(Exception):
    pass


class NutritionConflictError(NutritionError):
    pass


class NutritionEnergyMismatchError(NutritionConflictError):
    def __init__(self, *, implied_energy_kcal: int, difference_kcal: int) -> None:
        super().__init__(
            "Калорийность заметно отличается от энергии по БЖУ. "
            "Подтвердите сохранение или исправьте значения."
        )
        self.implied_energy_kcal = implied_energy_kcal
        self.difference_kcal = difference_kcal


class NutritionMacros(TypedDict):
    protein_g: int
    fat_g: int
    carbs_g: int
    macro_warning: bool


class NutritionCalculation(NutritionMacros):
    bmr: int
    base_tdee: int
    strength_daily_calories: int
    cardio_daily_calories: int
    tdee: int
    goal_multiplier: float
    calories: int


def _round_number(value: float) -> int:
    return max(0, math.floor(value + 0.5))


def _round_to_ten(value: float) -> int:
    return max(0, math.floor(value / 10 + 0.5) * 10)


def _round_up_to_ten(value: float) -> int:
    return max(0, math.ceil(value / 10) * 10)


def _target_calories(maintenance_calories: float, goal: str) -> int:
    return _round_to_ten(maintenance_calories * GOAL_MULTIPLIERS[goal])


def calculate_macros(weight_kg: float, target_calories: int, goal: str) -> NutritionMacros:
    protein_per_kg = {
        "fat_loss": 2.2,
        "muscle_gain": 1.8,
        "maintenance": 1.8,
        "recomposition": 2,
    }.get(goal, 1.8)
    fat_per_kg = 0.9 if goal in {"maintenance", "muscle_gain"} else 0.8
    protein = _round_number(weight_kg * protein_per_kg)
    fat = _round_number(weight_kg * fat_per_kg)
    remaining_calories = target_calories - protein * 4 - fat * 9
    carbs = _round_number(remaining_calories / 4)
    return {
        "protein_g": protein,
        "fat_g": fat,
        "carbs_g": carbs,
        "macro_warning": remaining_calories < 0,
    }


def _daily_activity(payload: NutritionTargetSave) -> tuple[str, str, float]:
    if payload.daily_routine is not None and payload.steps_range is not None:
        return (
            payload.daily_routine,
            payload.steps_range,
            ACTIVITY_COEFFICIENTS[payload.daily_routine][payload.steps_range],
        )
    legacy_level = payload.daily_activity_level or "sedentary"
    routine = LEGACY_DAILY_ROUTINES[legacy_level]
    return routine, "unknown", LEGACY_ACTIVITY_COEFFICIENTS[legacy_level]


def _cardio_trainings(payload: NutritionTargetSave) -> list[CardioTraining]:
    if payload.cardio_trainings is not None:
        return payload.cardio_trainings
    trainings_per_week = payload.cardio_trainings_per_week or 0
    if trainings_per_week == 0:
        return []
    legacy_intensity = payload.cardio_intensity or "moderate"
    return [
        CardioTraining(
            kind="other",
            trainings_per_week=trainings_per_week,
            duration_minutes=payload.cardio_training_duration_minutes or 30,
            intensity=cast(
                CardioIntensity,
                LEGACY_CARDIO_INTENSITIES[legacy_intensity],
            ),
        )
    ]


def _net_exercise_kcal(
    met_value: float,
    weight_kg: float,
    duration_minutes: int,
) -> float:
    return max(0, (met_value - 1) * 3.5 * weight_kg / 200 * duration_minutes)


def calculate_nutrition(payload: NutritionTargetSave) -> NutritionCalculation:
    sex = payload.sex.strip().lower()
    goal = payload.goal.strip()
    if sex not in VALID_SEXES:
        raise NutritionError("Invalid sex")
    if goal not in VALID_GOALS:
        raise NutritionError("Invalid goal")
    sex_constant = -161 if sex == "female" else 5
    bmr = 10 * payload.weight_kg + 6.25 * payload.height_cm - 5 * payload.age + sex_constant
    _, _, activity_coefficient = _daily_activity(payload)
    base_tdee = bmr * activity_coefficient
    strength_met = STRENGTH_MET_VALUES[payload.strength_training_type or "regular"]
    strength_met += STRENGTH_REST_ADJUSTMENTS.get(payload.strength_rest or "varied", 0)
    strength_weekly_calories = (
        _net_exercise_kcal(
            strength_met,
            payload.weight_kg,
            payload.strength_training_duration_minutes,
        )
        * payload.strength_trainings_per_week
    )
    cardio_weekly_calories = sum(
        _net_exercise_kcal(
            CARDIO_BASE_MET_VALUES[training.kind]
            * CARDIO_INTENSITY_MULTIPLIERS[training.intensity],
            payload.weight_kg,
            training.duration_minutes,
        )
        * training.trainings_per_week
        for training in _cardio_trainings(payload)
    )
    strength_daily_calories = strength_weekly_calories / 7
    cardio_daily_calories = cardio_weekly_calories / 7
    maintenance_calories = base_tdee + strength_daily_calories + cardio_daily_calories
    calories = _target_calories(maintenance_calories, goal)
    macros = calculate_macros(payload.weight_kg, calories, goal)
    if macros["macro_warning"]:
        # A calorie target below its own protein/fat allocation is internally
        # inconsistent and could previously become zero for accepted edge
        # inputs. Raise it only as far as needed to make every macro nonnegative.
        calories = _round_up_to_ten(macros["protein_g"] * 4 + macros["fat_g"] * 9)
        macros = calculate_macros(payload.weight_kg, calories, goal)
        macros["macro_warning"] = True

    return {
        "bmr": _round_number(bmr),
        "base_tdee": _round_number(base_tdee),
        "strength_daily_calories": _round_number(strength_daily_calories),
        "cardio_daily_calories": _round_number(cardio_daily_calories),
        "tdee": _round_number(maintenance_calories),
        "goal_multiplier": GOAL_MULTIPLIERS[goal],
        "calories": calories,
        **macros,
    }


def _resolve_target_user(
    db: Session,
    current_user: User,
    target_telegram_user_id: int | None,
) -> User:
    if not target_telegram_user_id or target_telegram_user_id == current_user.telegram_user_id:
        return current_user

    target_user = db.query(User).filter(User.telegram_user_id == target_telegram_user_id).first()
    if not target_user:
        raise NutritionError("Target user not found")

    if current_user.is_coach:
        link = (
            db.query(CoachClient)
            .filter(
                CoachClient.coach_user_id == current_user.id,
                CoachClient.client_user_id == target_user.id,
                CoachClient.status == "active",
            )
            .first()
        )
        if link:
            return target_user

    raise NutritionError("No permission to manage this user")


def _assigned_by_response(user: User | None) -> NutritionAssignedByResponse | None:
    if not user:
        return None
    return NutritionAssignedByResponse(
        id=user.id,
        telegram_user_id=user.telegram_user_id,
        username=user.username,
        full_name=user.profile.full_name if user.profile else None,
    )


def build_nutrition_target_response_from_users(
    target: NutritionTarget,
    user: User,
    assigned_by: User | None,
) -> NutritionTargetResponse:
    """Serialize a target when its related users were loaded by the caller."""
    author = _assigned_by_response(assigned_by)
    return NutritionTargetResponse(
        id=target.id,
        user_id=target.user_id,
        telegram_user_id=user.telegram_user_id,
        effective_from=target.effective_from,
        effective_to=target.effective_to,
        source=cast(
            Literal["calculated", "manual", "trainer", "adaptive"],
            target.source,
        ),
        created_at=target.saved_at,
        note=target.note,
        superseded_by_id=target.superseded_by_id,
        sex=target.sex,
        weight_kg=target.weight_kg,
        height_cm=target.height_cm,
        age=target.age,
        daily_routine=target.daily_routine,
        steps_range=target.steps_range,
        daily_activity_level=target.daily_activity_level,
        strength_trainings_per_week=target.strength_trainings_per_week,
        strength_training_duration_minutes=target.strength_training_duration_minutes,
        strength_training_type=target.strength_training_type,
        strength_rest=target.strength_rest,
        cardio_trainings=[
            CardioTraining.model_validate(row) for row in (target.cardio_trainings or [])
        ],
        cardio_trainings_per_week=target.cardio_trainings_per_week,
        cardio_training_duration_minutes=target.cardio_training_duration_minutes,
        cardio_intensity=target.cardio_intensity,
        goal=target.goal,
        bmr=target.bmr,
        tdee=target.tdee,
        calories=target.calories,
        protein_g=target.protein_g,
        fat_g=target.fat_g,
        carbs_g=target.carbs_g,
        saved_at=target.saved_at,
        created_by=author,
        assigned_by=author,
    )


def build_nutrition_target_response(
    db: Session,
    target: NutritionTarget | None,
) -> NutritionTargetResponse | None:
    if not target:
        return None

    user = db.query(User).filter(User.id == target.user_id).first()
    if not user:
        return None

    assigned_by = None
    if target.assigned_by_user_id:
        assigned_by = (
            db.query(User)
            .options(joinedload(User.profile))
            .filter(User.id == target.assigned_by_user_id)
            .first()
        )

    return build_nutrition_target_response_from_users(target, user, assigned_by)


def get_nutrition_target_for_user(
    db: Session,
    user: User,
) -> NutritionTargetResponse | None:
    target = get_current_nutrition_target(db, user.id)
    return build_nutrition_target_response_for_user(db, target, user)


def get_current_nutrition_target(
    db: Session,
    user_id: int,
    *,
    for_update: bool = False,
) -> NutritionTarget | None:
    query = db.query(NutritionTarget).filter(
        NutritionTarget.user_id == user_id,
        NutritionTarget.effective_to.is_(None),
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def get_nutrition_target_for_date(
    db: Session,
    user_id: int,
    target_date: date,
) -> NutritionTarget | None:
    return (
        db.query(NutritionTarget)
        .filter(
            NutritionTarget.user_id == user_id,
            NutritionTarget.effective_from <= target_date,
            (NutritionTarget.effective_to.is_(None)) | (NutritionTarget.effective_to > target_date),
        )
        .order_by(NutritionTarget.effective_from.desc(), NutritionTarget.id.desc())
        .first()
    )


def build_nutrition_target_response_for_user(
    db: Session,
    target: NutritionTarget | None,
    user: User,
) -> NutritionTargetResponse | None:
    if not target:
        return None
    assigned_by = None
    if target.assigned_by_user_id:
        assigned_by = (
            db.query(User)
            .options(joinedload(User.profile))
            .filter(User.id == target.assigned_by_user_id)
            .first()
        )
    return build_nutrition_target_response_from_users(target, user, assigned_by)


def _target_payload(target: NutritionTarget) -> NutritionTargetSave:
    if any(getattr(target, field) is None for field in NUTRITION_REQUIRED_INPUT_FIELDS):
        raise NutritionError("Nutrition calculator context is incomplete")
    return NutritionTargetSave.model_validate(
        {
            "sex": target.sex,
            "weight_kg": target.weight_kg,
            "height_cm": target.height_cm,
            "age": target.age,
            "daily_routine": target.daily_routine,
            "steps_range": target.steps_range,
            "strength_trainings_per_week": target.strength_trainings_per_week,
            "strength_training_duration_minutes": (target.strength_training_duration_minutes),
            "strength_training_type": target.strength_training_type,
            "strength_rest": target.strength_rest,
            "cardio_trainings": target.cardio_trainings,
            "goal": target.goal,
        }
    )


def _apply_calculation(target: NutritionTarget, calculations: NutritionCalculation) -> None:
    target.bmr = calculations["bmr"]
    target.tdee = calculations["tdee"]
    target.calories = calculations["calories"]
    target.protein_g = calculations["protein_g"]
    target.fat_g = calculations["fat_g"]
    target.carbs_g = calculations["carbs_g"]


def _queue_nutrition_updated_notification(
    db: Session,
    target_user: User,
    target: NutritionTarget,
    changed_by: User,
) -> None:
    actor_text = (
        "Тренер обновил ориентиры питания."
        if changed_by.id != target_user.id
        else "Ваши ориентиры питания изменились."
    )
    title = "КБЖУ пересчитаны" if target.source == "calculated" else "Ориентиры КБЖУ обновлены"
    queue_notification(
        db,
        target_user,
        category="nutrition_update",
        title=title,
        body=(
            f"{actor_text} Новые ориентиры: {target.calories} ккал · "
            f"Б {target.protein_g} г · Ж {target.fat_g} г · У {target.carbs_g} г. "
            "Проверьте раздел «КБЖУ»."
        ),
        action_url="/app?section=nutrition",
    )


def nutrition_target_context(target: NutritionTarget | None) -> dict[str, object | None]:
    return {
        field: getattr(target, field) if target is not None else None
        for field in NUTRITION_CONTEXT_FIELDS
    }


def _normalized_note(note: str | None) -> str | None:
    normalized = note.strip() if note else ""
    return normalized or None


def _same_target_version(
    target: NutritionTarget,
    *,
    source: str,
    effective_from: date,
    changed_by_user_id: int,
    note: str | None,
    values: dict[str, object | None],
) -> bool:
    return (
        target.source == source
        and target.effective_from == effective_from
        and target.assigned_by_user_id == changed_by_user_id
        and target.note == note
        and all(getattr(target, field) == value for field, value in values.items())
    )


def create_nutrition_target_version(
    db: Session,
    *,
    target_user: User,
    changed_by: User,
    source: str,
    effective_from: date,
    values: dict[str, object | None],
    note: str | None = None,
) -> tuple[NutritionTarget, bool]:
    """Create one canonical half-open target period while serializing per user."""
    db.query(User.id).filter(User.id == target_user.id).with_for_update().one()
    current = get_current_nutrition_target(db, target_user.id, for_update=True)
    current_day = today_for_user(target_user)
    if effective_from > current_day:
        raise NutritionConflictError("Дата начала цели не может быть в будущем")
    if current is not None and effective_from < current.effective_from:
        raise NutritionConflictError(
            "Дата начала не может быть раньше начала текущей цели; "
            "исторические периоды не переписываются"
        )

    normalized_note = _normalized_note(note)
    if current is not None and _same_target_version(
        current,
        source=source,
        effective_from=effective_from,
        changed_by_user_id=changed_by.id,
        note=normalized_note,
        values=values,
    ):
        return current, False

    target = NutritionTarget(
        user_id=target_user.id,
        assigned_by_user_id=changed_by.id,
        effective_from=effective_from,
        effective_to=None,
        source=source,
        note=normalized_note,
        saved_at=now_for_user_naive(target_user),
        **values,
    )
    if current is not None:
        # effective_to is exclusive. A same-day replacement therefore creates a
        # zero-length audit period without making two targets effective that day.
        current.effective_to = effective_from
    db.add(target)
    db.flush()
    if current is not None:
        current.superseded_by_id = target.id
    return target, True


def recalculate_nutrition_target(
    db: Session,
    target_user: User,
    updates: dict[str, object],
    changed_by: User,
) -> bool:
    """Version a calculated target; never silently rewrite manual/trainer values."""
    target = get_current_nutrition_target(db, target_user.id)
    if target is None or target.source != "calculated":
        return False

    context = nutrition_target_context(target)

    # The profile stores total cardio sessions, while the calculator stores
    # per-activity details. A single activity can be updated without guessing.
    # With multiple activities, keep their explicit split intact.
    requested_cardio = updates.get("cardio_trainings_per_week")
    if isinstance(requested_cardio, int):
        existing_cardio = context.get("cardio_trainings") or []
        if isinstance(existing_cardio, list) and (
            len(existing_cardio) == 1 or requested_cardio == 0
        ):
            if requested_cardio == 0:
                updates = {**updates, "cardio_trainings": []}
            elif len(existing_cardio) == 1:
                updates = {
                    **updates,
                    "cardio_trainings": [
                        {**existing_cardio[0], "trainings_per_week": requested_cardio}
                    ],
                }

    changed = False
    for field in NUTRITION_INPUT_FIELDS:
        value = updates.get(field)
        if value is None or context[field] == value:
            continue
        context[field] = value
        changed = True

    if not changed:
        return False

    try:
        candidate = NutritionTarget(**context)
        payload = _target_payload(candidate)
    except ValidationError as exc:
        raise NutritionError("Nutrition inputs are outside supported ranges") from exc
    calculations = calculate_nutrition(payload)
    context.update(
        bmr=calculations["bmr"],
        tdee=calculations["tdee"],
        calories=calculations["calories"],
        protein_g=calculations["protein_g"],
        fat_g=calculations["fat_g"],
        carbs_g=calculations["carbs_g"],
    )
    version, created = create_nutrition_target_version(
        db,
        target_user=target_user,
        changed_by=changed_by,
        source="calculated" if changed_by.id == target_user.id else "trainer",
        effective_from=today_for_user(target_user),
        values=context,
    )
    if created:
        _queue_nutrition_updated_notification(db, target_user, version, changed_by)
    return created


def save_nutrition_target(
    db: Session,
    current_user: User,
    payload: NutritionTargetSave,
) -> NutritionTargetResponse:
    target_user = _resolve_target_user(db, current_user, payload.target_telegram_user_id)
    calculations = calculate_nutrition(payload)
    ensure_profile(db, target_user)
    daily_routine, steps_range, _ = _daily_activity(payload)
    cardio_trainings = _cardio_trainings(payload)
    context: dict[str, object | None] = {
        "sex": payload.sex.strip().lower(),
        "weight_kg": payload.weight_kg,
        "height_cm": payload.height_cm,
        "age": payload.age,
        "daily_routine": daily_routine,
        "steps_range": steps_range,
        "daily_activity_level": payload.daily_activity_level or "sedentary",
        "strength_trainings_per_week": payload.strength_trainings_per_week,
        "strength_training_duration_minutes": payload.strength_training_duration_minutes,
        "strength_training_type": payload.strength_training_type or "regular",
        "strength_rest": payload.strength_rest,
        "cardio_trainings": [training.model_dump() for training in cardio_trainings],
        "cardio_trainings_per_week": sum(
            training.trainings_per_week for training in cardio_trainings
        ),
    }
    first_cardio = cardio_trainings[0] if cardio_trainings else None
    context["cardio_training_duration_minutes"] = (
        first_cardio.duration_minutes
        if first_cardio
        else (payload.cardio_training_duration_minutes or 30)
    )
    context.update(
        cardio_intensity=payload.cardio_intensity or "moderate",
        goal=payload.goal.strip(),
        bmr=calculations["bmr"],
        tdee=calculations["tdee"],
        calories=calculations["calories"],
        protein_g=calculations["protein_g"],
        fat_g=calculations["fat_g"],
        carbs_g=calculations["carbs_g"],
    )
    target, created = create_nutrition_target_version(
        db,
        target_user=target_user,
        changed_by=current_user,
        source="calculated" if current_user.id == target_user.id else "trainer",
        effective_from=payload.effective_from or today_for_user(target_user),
        values=context,
        note=payload.note,
    )
    if created:
        _queue_nutrition_updated_notification(db, target_user, target, current_user)

    if current_user.id == target_user.id:
        # Explicitly saved calculator inputs become the shared profile facts.
        # Trainer targets must never overwrite the client's personal profile.
        profile = target_user.profile
        if profile is not None:
            profile.sex = payload.sex
            profile.weight_kg = payload.weight_kg
            profile.height_cm = round(payload.height_cm)
            profile.goal = payload.goal
            profile.workouts_per_week = payload.strength_trainings_per_week
            profile.cardio_trainings_per_week = sum(
                item.trainings_per_week for item in cardio_trainings
            )
            from fitminiapp_api.services.measurements import sync_current_weight_to_diary

            sync_current_weight_to_diary(db, target_user, payload.weight_kg)

    db.commit()
    db.refresh(target)
    response = build_nutrition_target_response(db, target)
    if response is None:
        raise NutritionError("Nutrition target not found")
    return response


def save_manual_nutrition_target(
    db: Session,
    current_user: User,
    payload: NutritionManualTargetSave,
) -> NutritionTargetResponse:
    target_user = _resolve_target_user(db, current_user, payload.target_telegram_user_id)
    implied_energy = payload.protein_g * 4 + payload.fat_g * 9 + payload.carbs_g * 4
    difference = abs(implied_energy - payload.calories)
    allowed_difference = max(
        MANUAL_ENERGY_MISMATCH_MIN_KCAL,
        round(payload.calories * MANUAL_ENERGY_MISMATCH_RATIO),
    )
    if difference > allowed_difference and not payload.confirm_energy_mismatch:
        raise NutritionEnergyMismatchError(
            implied_energy_kcal=implied_energy,
            difference_kcal=difference,
        )

    ensure_profile(db, target_user)
    # Build the retry snapshot under the same per-user lock used for versioning.
    # Otherwise a concurrent request can commit between this read and
    # create_nutrition_target_version(), making ORM-populated defaults look like
    # a real target change and creating a duplicate same-day audit version.
    db.query(User.id).filter(User.id == target_user.id).with_for_update().one()
    current = get_current_nutrition_target(db, target_user.id)
    context = nutrition_target_context(current)
    if current is None and target_user.profile is not None:
        context["weight_kg"] = target_user.profile.weight_kg
        context["height_cm"] = target_user.profile.height_cm
        context["goal"] = (
            target_user.profile.goal if target_user.profile.goal in VALID_GOALS else None
        )
    context.update(
        calories=payload.calories,
        protein_g=payload.protein_g,
        fat_g=payload.fat_g,
        carbs_g=payload.carbs_g,
    )
    target, created = create_nutrition_target_version(
        db,
        target_user=target_user,
        changed_by=current_user,
        source="manual" if current_user.id == target_user.id else "trainer",
        effective_from=payload.effective_from or today_for_user(target_user),
        values=context,
        note=payload.note,
    )
    if created:
        _queue_nutrition_updated_notification(db, target_user, target, current_user)
    db.commit()
    db.refresh(target)
    response = build_nutrition_target_response(db, target)
    if response is None:
        raise NutritionError("Nutrition target not found")
    return response


def list_nutrition_target_history(
    db: Session,
    current_user: User,
    target_telegram_user_id: int | None = None,
) -> list[NutritionTargetResponse]:
    target_user = _resolve_target_user(db, current_user, target_telegram_user_id)
    rows = (
        db.query(NutritionTarget)
        .filter(NutritionTarget.user_id == target_user.id)
        .order_by(NutritionTarget.effective_from.desc(), NutritionTarget.id.desc())
        .limit(100)
        .all()
    )
    return [
        response
        for row in rows
        if (response := build_nutrition_target_response_for_user(db, row, target_user)) is not None
    ]
