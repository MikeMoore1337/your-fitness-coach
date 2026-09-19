from __future__ import annotations

from datetime import date, datetime, timedelta
from math import isfinite
from typing import Any
from urllib.parse import parse_qs, urlsplit

from fitminiapp_api.services.demo_sessions import (
    DemoActionForbiddenError,
    DemoSessionStore,
    DemoTransitionError,
    _DemoSession,
)

DEMO_WORKOUT_ID = 50_001
DEMO_CLIENT_IDS = {"alexey": 51_001, "maria": 51_002, "ivan": 51_003}


def _now(session: _DemoSession) -> datetime:
    return session.created_at.replace(microsecond=0)


def _today(session: _DemoSession) -> date:
    return _now(session).date()


def _iso(value: date | datetime) -> str:
    return value.isoformat()


def _query(path: str, key: str, default: str | None = None) -> str | None:
    value = parse_qs(urlsplit(path).query).get(key, [default])[0]
    return value


def _period_days(raw_value: str | None) -> int:
    if raw_value is None:
        return 30
    if not raw_value.isascii() or not raw_value.isdigit() or len(raw_value) > 3:
        raise DemoActionForbiddenError
    value = int(raw_value)
    if not 1 <= value <= 366:
        raise DemoActionForbiddenError
    return value


def _user(session: _DemoSession) -> dict[str, Any]:
    created = _iso(_now(session))
    user_id = session.user_id
    target = _nutrition_target(user_id, _today(session), session)
    coach = session.scenario == "trainer"
    return {
        "id": user_id,
        "telegram_user_id": None,
        "username": "demo_user",
        "first_name": "Демо",
        "last_name": None,
        "photo_url": None,
        "custom_avatar": None,
        "is_coach": coach,
        "is_admin": False,
        "is_root": False,
        "has_active_program": True,
        "has_workout_history": True,
        "has_food_history": True,
        "auth_providers": [],
        "onboarding": {"status": "complete", "required_fields": [], "missing_fields": []},
        "profile": {
            "full_name": "Демо-профиль",
            "birth_date": None,
            "sex": "male",
            "goal": "muscle_gain",
            "level": "intermediate",
            "height_cm": 180,
            "weight_kg": 77.1,
            "workouts_per_week": 4,
            "cardio_trainings_per_week": 2,
            "resting_heart_rate": None,
            "body_priority": {"mode": "balanced", "muscle_group_ids": []},
            "training_preferences": {
                "preferred_duration_min": 45,
                "preferred_duration_max": 70,
                "preferred_weekdays": [0, 2, 4, 5],
                "preferred_time": "19:00:00",
                "location_profiles": [{"location": "gym", "equipment_ids": ["dumbbell", "bench"]}],
                "preferred_exercise_ids": [],
                "avoided_exercises": [],
                "note": None,
                "updated_at": created,
                "updated_by": None,
                "conflict": {"status": "none", "active_program_id": None, "reasons": []},
            },
            "timezone": "Europe/Moscow",
            "estimated_max_heart_rate": None,
            "heart_rate_reserve": None,
            "heart_rate_calculation_method": None,
            "heart_rate_zones": [],
            "recommended_cardio_range": None,
            "kbju": target,
        },
        "trainer": None,
    }


def _nutrition_target(user_id: int, today: date, session: _DemoSession) -> dict[str, Any]:
    return {
        "id": 70_001,
        "user_id": user_id,
        "telegram_user_id": None,
        "effective_from": _iso(today - timedelta(days=20)),
        "effective_to": None,
        "source": "calculated",
        "created_at": _iso(_now(session) - timedelta(days=20)),
        "note": None,
        "superseded_by_id": None,
        "sex": "male",
        "weight_kg": 77.1,
        "height_cm": 180,
        "age": 31,
        "daily_routine": "mixed",
        "steps_range": "from_7000_to_10000",
        "strength_trainings_per_week": 4,
        "strength_training_duration_minutes": 60,
        "strength_training_type": "regular",
        "strength_rest": "one_to_two",
        "cardio_trainings": [],
        "goal": "muscle_gain",
        "bmr": 1740,
        "tdee": 2420,
        "calories": 2150,
        "protein_g": 145,
        "fat_g": 70,
        "carbs_g": 245,
        "saved_at": _iso(_now(session) - timedelta(days=20)),
        "created_by": None,
        "assigned_by": None,
        "daily_activity_level": "moderate",
        "cardio_trainings_per_week": 2,
        "cardio_training_duration_minutes": 30,
        "cardio_intensity": "moderate",
    }


def _schedule(session: _DemoSession) -> list[dict[str, Any]]:
    today = _today(session)
    current_index = today.weekday()
    completed = session.scenario == "self_training" and session.state["screen"] in {
        "summary",
        "progress",
    }
    in_progress = (
        session.scenario == "self_training" and session.state["screen"] == "active_workout"
    )
    start = today - timedelta(days=current_index)
    titles = ["Верх тела", "Кардио", "Ноги и корпус", "Отдых", "Верх тела", "Кардио", "Отдых"]
    statuses = ["completed", "completed", "planned", "rest", "planned", "planned", "rest"]
    if titles[current_index] != "Отдых":
        titles[current_index] = session.state.get("workout_title", "Верх тела · уверенный старт")
        statuses[current_index] = (
            "completed" if completed else "in_progress" if in_progress else "planned"
        )
    return [
        {
            "id": DEMO_WORKOUT_ID if index == current_index else DEMO_WORKOUT_ID + 100 + index,
            "scheduled_date": _iso(start + timedelta(days=index)),
            "scheduled_time": "19:00:00" if status != "rest" else None,
            "title": title,
            "status": status,
            "day_number": index + 1,
            "week_number": 4,
        }
        for index, (title, status) in enumerate(zip(titles, statuses, strict=True))
    ]


def _workout_set(session: _DemoSession, number: int) -> dict[str, Any]:
    state = session.state
    completed_numbers = state.setdefault(
        "workout_completed_sets",
        list(range(1, int(state.get("completed_sets", 0)) + 1)),
    )
    completed = number in completed_numbers
    details = state.get("workout_set_details", {}).get(str(number), {})
    return {
        "id": 60_001 + number,
        "set_number": number,
        "actual_reps": details.get("actual_reps", 10 if completed else None),
        "actual_weight": details.get("actual_weight", 18.0 if completed else None),
        "duration_minutes": details.get("duration_minutes"),
        "distance_km": details.get("distance_km"),
        "average_heart_rate_bpm": details.get("average_heart_rate_bpm"),
        "heart_rate_zone": details.get("heart_rate_zone"),
        "rir": details.get("rir", "2" if completed else None),
        "set_kind": details.get("set_kind", "working"),
        "reached_failure": details.get("reached_failure", False if completed else None),
        "is_completed": completed,
        "version": int(details.get("version", 1)),
    }


def _workout(session: _DemoSession) -> dict[str, Any]:
    state = session.state
    screen = state["screen"] if session.scenario == "self_training" else "today"
    status = (
        "in_progress"
        if screen == "active_workout"
        else "completed"
        if screen in {"summary", "progress"}
        else "planned"
    )
    started_at = _iso(_now(session) - timedelta(minutes=46)) if status != "planned" else None
    completed_at = _iso(_now(session)) if status == "completed" else None
    sets = [_workout_set(session, number) for number in range(1, 4)]
    result = {
        "id": DEMO_WORKOUT_ID,
        "scheduled_date": _iso(_today(session)),
        "scheduled_time": "19:00:00",
        "title": state.get("workout_title", "Верх тела · уверенный старт"),
        "status": status,
        "day_number": 3,
        "week_number": 4,
        "started_at": started_at,
        "completed_at": completed_at,
        "exercises": [
            {
                "id": 61_001,
                "exercise_id": 1_001,
                "exercise_title": "Жим гантелей лёжа с контролируемой паузой",
                "metric_type": "strength",
                "sort_order": 1,
                "prescribed_sets": 3,
                "prescribed_reps": "10",
                "prescribed_duration_minutes": None,
                "rest_seconds": 90,
                "notes": "Сохраняйте контроль в нижней точке.",
                "superset_group": None,
                "superset_order": None,
                "has_guide": False,
                "progression_guidance": None,
                "sets": sets,
            },
            {
                "id": 61_002,
                "exercise_id": 1_002,
                "exercise_title": "Тяга верхнего блока нейтральным хватом",
                "metric_type": "strength",
                "sort_order": 2,
                "prescribed_sets": 3,
                "prescribed_reps": "12",
                "prescribed_duration_minutes": None,
                "rest_seconds": 75,
                "notes": None,
                "superset_group": None,
                "superset_order": None,
                "has_guide": False,
                "progression_guidance": None,
                "sets": [],
            },
        ],
        "completion_summary": None,
    }
    if status == "completed":
        completed_sets = [item for item in sets if item["is_completed"]]
        reps = [item["actual_reps"] for item in completed_sets if item["actual_reps"] is not None]
        weights = [
            item["actual_weight"] for item in completed_sets if item["actual_weight"] is not None
        ]
        result["completion_summary"] = {
            "duration_seconds": 2_760,
            "performed_exercises": 1 if completed_sets else 0,
            "completed_sets": len(completed_sets),
            "total_sets": len(sets),
            "reps_total": sum(reps) if reps else None,
            "reps_recorded_sets": len(reps),
            "load_recorded_sets": len(weights),
            "exercises": [
                {
                    "workout_exercise_id": 61_001,
                    "exercise_id": 1_001,
                    "exercise_title": "Жим гантелей лёжа с контролируемой паузой",
                    "metric_type": "strength",
                    "completed_sets": len(completed_sets),
                    "reps_total": sum(reps) if reps else None,
                    "reps_recorded_sets": len(reps),
                    "max_load_kg": max(weights) if weights else None,
                    "load_recorded_sets": len(weights),
                    "duration_minutes": None,
                    "distance_km": None,
                    "average_heart_rate_bpm": None,
                    "heart_rate_zone": None,
                }
            ],
            "personal_records": [],
            "next_workout": None,
            "feedback": None,
            "note": None,
        }
    return result


def _nutrition_item(session: _DemoSession) -> dict[str, Any]:
    item = _recent_item(session)
    now = _iso(_now(session))
    return {
        "id": 80_001,
        "name": item["name"],
        "brand": None,
        "barcode": None,
        "energy_kcal_per_100g": 134,
        "protein_g_per_100g": 7.5,
        "fat_g_per_100g": 3.2,
        "carbs_g_per_100g": 18.1,
        "fiber_g_per_100g": 2.4,
        "nutrition_basis_kind": "per_100_g",
        "nutrition_basis_amount": 100,
        "nutrition_basis_unit": "g",
        "canonical_facts": None,
        "nutrition_provenance": None,
        "catalog_quality": "verified",
        "provenance": "internal",
        "trust_level": "verified",
        "canonical_complete": True,
        "standard_serving_amount": 320,
        "standard_serving_unit": "g",
        "standard_serving_weight_g": 320,
        "food_type": "system",
        "is_favorite": False,
        "last_used_at": now,
        "created_at": now,
        "updated_at": now,
    }


def _nutrition_entry(session: _DemoSession, diary_date: str, meal_type: str) -> dict[str, Any]:
    item = _recent_item(session)
    now = _iso(_now(session))
    return {
        "id": 80_101,
        "diary_date": diary_date,
        "meal_type": meal_type,
        "food_id": None,
        "recipe_id": None,
        "entry_kind": "quick_add",
        "logged_at": _now(session).strftime("%H:%M:%S"),
        "food_name": item["name"],
        "food_brand": None,
        "amount": 1,
        "amount_unit": "serving",
        "weight_g": None,
        "nutrition_basis_kind": None,
        "nutrition_basis_amount": None,
        "nutrition_basis_unit": None,
        "serving_amount": 1,
        "serving_unit": "порция",
        "serving_weight_g": 320,
        "nutrition": {
            "energy_kcal": item["calories"],
            "protein_g": item["protein_g"],
            "fat_g": 10,
            "carbs_g": 56,
            "fiber_g": 8,
        },
        "created_at": now,
        "updated_at": now,
    }


def _recent_item(session: _DemoSession) -> dict[str, Any]:
    return session.state.get(
        "recent_item",
        {
            "name": "Творог с ягодами",
            "serving": "220 г · подготовленная запись",
            "calories": 286,
            "protein_g": 31.0,
        },
    )


def _nutrition_day(session: _DemoSession, diary_date: str | None = None) -> dict[str, Any]:
    selected = diary_date or _iso(_today(session))
    state = session.state
    added = session.scenario == "nutrition" and bool(state.get("item_added"))
    base_entry = _nutrition_entry(session, selected, "breakfast")
    entries = [base_entry] if added else []
    totals = {
        "energy_kcal": state.get("calories", 1_160) if session.scenario == "nutrition" else 1_580,
        "protein_g": state.get("protein_g", 82.0) if session.scenario == "nutrition" else 104.0,
        "fat_g": 48,
        "carbs_g": 180,
        "fiber_g": 22,
    }
    target = {"energy_kcal": 2_150, "protein_g": 145, "fat_g": 70, "carbs_g": 245}
    remaining = {
        key: max(0, target[key] - totals[key]) if totals[key] is not None else None
        for key in target
    }
    meals = []
    for meal_type in ("breakfast", "lunch", "dinner", "snacks"):
        meal_entries = entries if meal_type == "breakfast" else []
        meals.append(
            {
                "meal_type": meal_type,
                "entries": meal_entries,
                "totals": {
                    "energy_kcal": sum(
                        float(item["nutrition"]["energy_kcal"]) for item in meal_entries
                    ),
                    "protein_g": sum(
                        float(item["nutrition"]["protein_g"]) for item in meal_entries
                    ),
                    "fat_g": sum(float(item["nutrition"]["fat_g"]) for item in meal_entries),
                    "carbs_g": sum(float(item["nutrition"]["carbs_g"]) for item in meal_entries),
                    "fiber_g": sum(float(item["nutrition"]["fiber_g"]) for item in meal_entries),
                },
            }
        )
    return {
        "diary_date": selected,
        "timezone": "Europe/Moscow",
        "meals": meals,
        "totals": totals,
        "targets": target,
        "remaining": remaining,
        "status": "complete" if added else "incomplete",
        "status_is_explicit": False,
    }


def _hydration_day(session: _DemoSession, diary_date: str | None = None) -> dict[str, Any]:
    selected = diary_date or _iso(_today(session))
    now = _iso(_now(session))
    state = session.state
    raw_entries = [
        item for item in state.setdefault("hydration_entries", []) if item["diary_date"] == selected
    ]
    entries = [_hydration_entry(session, item) for item in raw_entries]
    goal_enabled = bool(state.setdefault("hydration_goal_enabled", True))
    target_ml = int(state.setdefault("hydration_goal_ml", 2_200))
    goal = (
        {
            "id": 90_001,
            "enabled": True,
            "target_ml": target_ml,
            "source": "manual",
            "method_version": "demo-v1",
            "reference_scope": "demo",
            "sex": "male",
            "adult_confirmed": True,
            "effective_from": _iso(_today(session) - timedelta(days=20)),
            "effective_to": None,
            "created_at": _iso(_now(session) - timedelta(days=20)),
        }
        if goal_enabled
        else None
    )
    total_ml = 1_350 + sum(int(item["volume_ml"]) for item in entries)
    last_logged_at = max((item["occurred_at"] for item in raw_entries), default=None)
    presets = [
        {
            "id": 90_101,
            "label": "Стакан",
            "volume_ml": 250,
            "beverage_type": "water",
            "is_default": True,
        },
        {
            "id": 90_102,
            "label": "Бутылка",
            "volume_ml": 500,
            "beverage_type": "water",
            "is_default": False,
        },
        *state.setdefault("hydration_presets", []),
    ]
    return {
        "diary_date": selected,
        "timezone": "Europe/Moscow",
        "total_ml": total_ml,
        "goal": goal,
        "progress_percent": round(total_ml / target_ml * 100, 1) if goal_enabled else None,
        "entries": entries,
        "presets": presets,
        "last_logged_at": last_logged_at or now,
        "reminder_suppression_key": None,
        "action_url": "/api/v1/nutrition/hydration/entries",
        "original_estimated_minutes": 0,
        "adapted_estimated_minutes": 0,
        "time_budget_minutes": None,
        "changes": [],
        "original_exercises": [],
        "adapted_exercises": [],
        "warnings": [],
        "message": "Данные гидратации доступны только в текущей демо-сессии.",
        "preview_token": None,
    }


def _hydration_date(value: Any, default: date) -> str:
    if value is None:
        return _iso(default)
    if not isinstance(value, str):
        raise DemoActionForbiddenError
    try:
        return _iso(date.fromisoformat(value))
    except ValueError as exc:
        raise DemoActionForbiddenError from exc


def _hydration_entry(session: _DemoSession, payload: dict[str, Any]) -> dict[str, Any]:
    now = _iso(_now(session))
    return {
        "id": int(payload["id"]),
        "volume_ml": int(payload["volume_ml"]),
        "beverage_type": payload["beverage_type"],
        "occurred_at": payload["occurred_at"],
        "diary_date": payload["diary_date"],
        "timezone": "Europe/Moscow",
        "source": payload.get("source", "manual"),
        "created_at": payload.get("created_at", now),
        "updated_at": payload.get("updated_at", now),
    }


def _validate_hydration_payload(payload: dict[str, Any], *, update: bool = False) -> None:
    allowed = {"volume_ml", "beverage_type", "occurred_at", "diary_date", "source"}
    if set(payload) - allowed:
        raise DemoActionForbiddenError
    volume = payload.get("volume_ml")
    if isinstance(volume, bool) or not isinstance(volume, int) or not 1 <= volume <= 5_000:
        raise DemoActionForbiddenError
    if payload.get("beverage_type") not in {"water", "tea", "coffee", "milk", "juice", "other"}:
        raise DemoActionForbiddenError
    if update and not isinstance(payload.get("occurred_at"), str):
        raise DemoActionForbiddenError
    if not update and payload.get("source", "manual") not in {"quick_preset", "manual"}:
        raise DemoActionForbiddenError


def _add_hydration_entry(session: _DemoSession, payload: dict[str, Any]) -> dict[str, Any]:
    _validate_hydration_payload(payload)
    occurred_at = payload.get("occurred_at") or _iso(_now(session))
    if not isinstance(occurred_at, str):
        raise DemoActionForbiddenError
    try:
        datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DemoActionForbiddenError from exc
    stored = {
        "id": max(
            (int(item["id"]) for item in session.state.setdefault("hydration_entries", [])),
            default=90_199,
        )
        + 1,
        "volume_ml": payload["volume_ml"],
        "beverage_type": payload["beverage_type"],
        "occurred_at": occurred_at,
        "diary_date": _hydration_date(payload.get("diary_date"), _today(session)),
        "timezone": "Europe/Moscow",
        "source": payload.get("source", "manual"),
        "created_at": _iso(_now(session)),
        "updated_at": _iso(_now(session)),
    }
    session.state["hydration_entries"].append(stored)
    session.revision += 1
    return _hydration_entry(session, stored)


def _update_hydration_entry(
    session: _DemoSession,
    entry_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    _validate_hydration_payload(payload, update=True)
    entries = session.state.setdefault("hydration_entries", [])
    stored = next((item for item in entries if int(item["id"]) == entry_id), None)
    if stored is None:
        raise DemoActionForbiddenError
    try:
        datetime.fromisoformat(payload["occurred_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise DemoActionForbiddenError from exc
    changed = any(
        stored.get(key) != payload[key] for key in ("volume_ml", "beverage_type", "occurred_at")
    )
    if changed:
        for key in ("volume_ml", "beverage_type", "occurred_at"):
            stored[key] = payload[key]
        stored["updated_at"] = _iso(_now(session))
        session.revision += 1
    return _hydration_entry(session, stored)


def _hydration_goal(session: _DemoSession, payload: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {"enabled", "target_ml", "source", "sex", "adult_confirmed", "save_sex_to_profile"}
    if set(payload) - allowed or payload.get("source") not in {
        "manual",
        "national_academies_beverages",
    }:
        raise DemoActionForbiddenError
    enabled = payload.get("enabled", True)
    if not isinstance(enabled, bool):
        raise DemoActionForbiddenError
    if not enabled:
        if session.state.get("hydration_goal_enabled", True):
            session.state["hydration_goal_enabled"] = False
            session.revision += 1
        return None
    target = payload.get("target_ml")
    if payload["source"] == "manual":
        if isinstance(target, bool) or not isinstance(target, int) or not 250 <= target <= 10_000:
            raise DemoActionForbiddenError
    else:
        if (
            payload.get("sex") not in {"male", "female"}
            or payload.get("adult_confirmed") is not True
        ):
            raise DemoActionForbiddenError
        target = 2_200 if payload["sex"] == "male" else 1_800
    changed = (
        not session.state.get("hydration_goal_enabled", True)
        or session.state.get("hydration_goal_ml") != target
    )
    session.state["hydration_goal_enabled"] = True
    session.state["hydration_goal_ml"] = target
    if changed:
        session.revision += 1
    return _hydration_day(session)["goal"]


def _hydration_preset(session: _DemoSession, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"label", "volume_ml", "beverage_type"}
    if set(payload) - allowed:
        raise DemoActionForbiddenError
    label = payload.get("label")
    volume = payload.get("volume_ml")
    if not isinstance(label, str) or not 1 <= len(label.strip()) <= 40:
        raise DemoActionForbiddenError
    if isinstance(volume, bool) or not isinstance(volume, int) or not 1 <= volume <= 5_000:
        raise DemoActionForbiddenError
    if payload.get("beverage_type", "water") not in {
        "water",
        "tea",
        "coffee",
        "milk",
        "juice",
        "other",
    }:
        raise DemoActionForbiddenError
    stored = {
        "id": max(
            [
                90_102,
                *(int(item["id"]) for item in session.state.setdefault("hydration_presets", [])),
            ]
        )
        + 1,
        "label": label.strip(),
        "volume_ml": volume,
        "beverage_type": payload.get("beverage_type", "water"),
        "is_default": False,
    }
    session.state["hydration_presets"].append(stored)
    session.revision += 1
    return stored


def _signal(status: str = "sufficient", reasons: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "counters": {"available": 1},
        "reason_keys": reasons or ["thresholds_met"],
    }


def _progress_summary(
    session: _DemoSession, period_days: int | None = None, user_id: int | None = None
) -> dict[str, Any]:
    days = period_days or 30
    end = _today(session)
    start = end - timedelta(days=days - 1)
    completed = session.scenario == "self_training" and session.state["screen"] in {
        "summary",
        "progress",
    }
    nutrition_added = session.scenario == "nutrition" and session.state.get("item_added", False)
    return {
        "user_id": user_id or session.user_id,
        "period_days": days,
        "period_start": _iso(start),
        "period_end": _iso(end),
        "training": {
            "planned_workouts": 12,
            "completed_workouts": 12 if completed else 11,
            "skipped_workouts": 0,
            "frequency_per_week": 3.2,
            "volume_kg": 6840 if completed else 6220,
            "new_personal_records": 1 if completed else 0,
            "last_completed_workout_on": _iso(end - timedelta(days=2)),
            "next_workout": {
                "id": DEMO_WORKOUT_ID + 4,
                "scheduled_date": _iso(end + timedelta(days=2)),
                "scheduled_time": "19:00:00",
                "title": "Верх тела",
                "status": "planned",
            },
        },
        "cardio": {
            "completed_sessions": 6,
            "planned_sessions": 8,
            "frequency_per_week": 1.5,
            "duration_minutes": 210,
            "distance_km": 22.4,
            "zone_duration": [{"zone": 2, "duration_minutes": 142}],
        },
        "nutrition": {
            "visible": True,
            "logged_days": 6 if nutrition_added else 5,
            "complete_days": 5 if nutrition_added else 4,
            "incomplete_days": 1,
            "fasted_days": 0,
            "unlogged_days": days - 6,
            "adherence_evaluated_days": 6,
            "average_calories": 2_010,
            "target_calories": 2_150,
            "average_protein_g": 132,
            "target_protein_g": 145,
            "target_effective_on": _iso(end - timedelta(days=20)),
        },
        "body": {
            "latest_measurement": {
                "measured_on": _iso(end),
                "weight_kg": 77.1,
                "chest_cm": None,
                "waist_cm": None,
                "hips_cm": None,
                "biceps_cm": None,
                "thigh_cm": None,
                "custom_measurements": [
                    {
                        "definition_id": 93_001,
                        "label": "Пользовательский показатель",
                        "unit": "cm",
                        "value": 84.0,
                        "measured_on": _iso(end),
                        "archived": False,
                    }
                ],
            },
            "trends": [
                {
                    "metric": "weight_kg",
                    "label": "Вес",
                    "unit": "kg",
                    "definition_id": None,
                    "first_value": 77.8,
                    "latest_value": 77.1,
                    "change": -0.7,
                    "first_measured_on": _iso(end - timedelta(days=28)),
                    "latest_measured_on": _iso(end),
                    "point_count": 2,
                    "span_days": 28,
                    "interpretation_status": "available",
                    "points": [
                        {"measured_on": _iso(end - timedelta(days=28)), "value": 77.8},
                        {"measured_on": _iso(end), "value": 77.1},
                    ],
                },
                {
                    "metric": "custom:93001",
                    "label": "Пользовательский показатель",
                    "unit": "cm",
                    "definition_id": 93_001,
                    "first_value": 86.0,
                    "latest_value": 84.0,
                    "change": -2.0,
                    "first_measured_on": _iso(end - timedelta(days=28)),
                    "latest_measured_on": _iso(end),
                    "point_count": 3,
                    "span_days": 28,
                    "interpretation_status": "available",
                    "points": [
                        {"measured_on": _iso(end - timedelta(days=28)), "value": 86.0},
                        {"measured_on": _iso(end - timedelta(days=14)), "value": 85.0},
                        {"measured_on": _iso(end), "value": 84.0},
                    ],
                },
            ],
            "priority": {"mode": "balanced", "muscle_group_ids": []},
            "guidance": {
                "comparison_basis": "self",
                "minimum_points_for_interpretation": 2,
                "minimum_span_days_for_interpretation": 14,
                "consistency_tips": ["Измеряйте вес в похожих условиях."],
                "circumference_limitations": ["Одна точка не образует тренд."],
            },
        },
        "adherence": {
            "formula_version": "adherence-v1",
            "overall_percent": 82,
            "included_components": ["workouts", "cardio", "calories", "protein"],
            "workouts": {
                "status": "available",
                "percent": 92,
                "achieved": 11,
                "evaluated": 12,
                "weight": 0.4,
                "reason": None,
            },
            "cardio": {
                "status": "available",
                "percent": 75,
                "achieved": 6,
                "evaluated": 8,
                "weight": 0.2,
                "reason": None,
            },
            "calories": {
                "status": "available",
                "percent": 78,
                "achieved": 5,
                "evaluated": 6,
                "weight": 0.2,
                "reason": None,
            },
            "protein": {
                "status": "available",
                "percent": 81,
                "achieved": 5,
                "evaluated": 6,
                "weight": 0.2,
                "reason": None,
            },
        },
        "data_sufficiency": {
            "ruleset_version": "data-sufficiency-v1",
            "workout_logging": _signal(),
            "working_sets": _signal(),
            "rir_coverage": _signal("limited", ["too_few_rir_observations"]),
            "nutrition_coverage": _signal(),
            "weight_trend": _signal(),
            "anthropometry": _signal("insufficient", ["no_anthropometry_measurements"]),
            "schedule_adherence": _signal(),
            "confirm_energy_mismatch": False,
        },
    }


def _nutrition_report(session: _DemoSession, client_id: int | None = None) -> dict[str, Any]:
    end = _today(session)
    start = end - timedelta(days=29)
    nutrition_added = session.scenario == "nutrition" and bool(session.state.get("item_added"))
    daily = []
    for offset in range(5):
        current = end - timedelta(days=offset)
        calories = (
            int(session.state.get("calories", 2_010))
            if nutrition_added and offset == 0
            else 1_160
            if offset == 2
            else 2_010
        )
        protein = (
            float(session.state.get("protein_g", 132))
            if nutrition_added and offset == 0
            else 82.0
            if offset == 2
            else 132.0
        )
        daily.append(
            {
                "diary_date": _iso(current),
                "status": "complete" if offset != 2 else "incomplete",
                "is_current_day": offset == 0,
                "calories": calories,
                "protein_g": protein,
                "fat_g": 68,
                "carbs_g": 230,
                "target_calories": 2_150,
                "target_protein_g": 145,
                "target_fat_g": 70,
                "target_carbs_g": 245,
                "calorie_deviation": -140,
                "protein_deviation_g": -13,
                "fat_deviation_g": -2,
                "carbs_deviation_g": -15,
                "within_calorie_tolerance": True,
                "meets_protein_target": False,
                "target_changed": False,
                "hydration_ml": 1_800,
                "hydration_target_ml": 2_200,
                "hydration_progress_percent": 81.8,
            }
        )

    def metric(average: int) -> dict[str, Any]:
        return {
            "average": average,
            "minimum": average - 100,
            "maximum": average + 100,
            "sample_days": 5,
        }

    def comparison(average: int, target: int) -> dict[str, Any]:
        return {
            "average_actual": average,
            "average_target": target,
            "average_deviation": average - target,
            "evaluated_days": 5,
        }

    return {
        "period": "days_30",
        "period_start": _iso(start),
        "period_end": _iso(end),
        "timezone": "Europe/Moscow",
        "summary": {
            "logged_days": 5,
            "eligible_days": 30,
            "coverage_percent": 16.7,
            "complete_days": 5 if nutrition_added else 4,
            "incomplete_days": 0 if nutrition_added else 1,
            "fasted_days": 0,
            "missing_days": 25,
            "current_day_status": "complete" if nutrition_added else "incomplete",
            "calories": metric(2_010),
            "protein_g": metric(132),
            "fat_g": metric(68),
            "carbs_g": metric(230),
            "calorie_comparison": comparison(2_010, 2_150),
            "protein_comparison": comparison(132, 145),
            "fat_comparison": comparison(68, 70),
            "carbs_comparison": comparison(230, 245),
            "days_within_calorie_tolerance": 4,
            "calorie_tolerance_evaluated_days": 5,
            "days_meeting_protein_target": 2,
            "protein_target_evaluated_days": 5,
        },
        "daily": daily,
        "target_changes": [],
        "hydration": {
            "total_ml": 10_800,
            "average_ml": 2_160,
            "logged_days": 5,
            "eligible_days": 5,
            "coverage_percent": 100,
            "days_meeting_goal": 3,
            "goal_evaluated_days": 5,
            "trend_ml": 120,
        },
    }


def _training_analytics(session: _DemoSession) -> dict[str, Any]:
    end = _today(session)
    start = end - timedelta(days=29)
    return {
        "period_days": 30,
        "period_start": _iso(start),
        "period_end": _iso(end),
        "exercise_history_limit": 20,
        "completed_set_count": 54,
        "reps_total": 620,
        "reps_recorded_sets": 54,
        "external_load_volume_kg": 24_680,
        "volume_recorded_sets": 54,
        "exercises": [],
        "rir": {
            "completed_set_count": 54,
            "recorded_set_count": 42,
            "missing_set_count": 12,
            "distribution": [
                {"value": "2", "completed_set_count": 20},
                {"value": "3", "completed_set_count": 22},
            ],
        },
        "primary_muscle_exposure": [
            {"muscle_id": "legs", "muscle_name": "Ноги", "completed_set_count": 18}
        ],
        "secondary_muscle_exposure": [],
        "completed_sets_without_muscle_metadata": 0,
        "data_sufficiency": {
            "ruleset_version": "data-sufficiency-v1",
            "workout_logging": _signal(),
            "working_sets": _signal(),
            "rir_coverage": _signal("limited", ["too_few_rir_observations"]),
        },
    }


def _exercise_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": 1_001,
            "title": "Жим гантелей лёжа",
            "primary_muscle": "Грудь",
            "equipment": "Гантели",
            "metric_type": "strength",
            "primary_muscle_ids": ["chest"],
            "secondary_muscle_ids": ["triceps", "shoulders"],
            "equipment_ids": ["dumbbell", "bench"],
            "aliases": [],
            "movement_pattern": "horizontal_push",
            "machine_variant_tags": [],
            "execution_variant_tags": [],
            "alternatives": [],
            "difficulty_level": "beginner",
            "edit_target_id": None,
            "slug": "dumbbell-bench-press",
            "canonical_slug": "dumbbell-bench-press",
            "is_custom": False,
            "is_personalized": False,
            "created_by_user_id": None,
            "source_exercise_id": None,
            "has_guide": False,
            "guide": None,
        },
        {
            "id": 1_002,
            "title": "Тяга верхнего блока",
            "primary_muscle": "Спина",
            "equipment": "Тросовый блок",
            "metric_type": "strength",
            "primary_muscle_ids": ["back"],
            "secondary_muscle_ids": ["biceps"],
            "equipment_ids": ["cable"],
            "aliases": [],
            "movement_pattern": "vertical_pull",
            "machine_variant_tags": [],
            "execution_variant_tags": [],
            "alternatives": [],
            "difficulty_level": "beginner",
            "edit_target_id": None,
            "slug": "lat-pulldown",
            "canonical_slug": "lat-pulldown",
            "is_custom": False,
            "is_personalized": False,
            "created_by_user_id": None,
            "source_exercise_id": None,
            "has_guide": False,
            "guide": None,
        },
    ]


def _program_template(session: _DemoSession) -> dict[str, Any]:
    exercise = {
        "id": 40_001,
        "exercise_id": 1_001,
        "exercise_title": "Жим гантелей лёжа",
        "metric_type": "strength",
        "prescribed_sets": 3,
        "prescribed_reps": "10",
        "prescribed_duration_minutes": None,
        "rest_seconds": 90,
        "notes": None,
        "superset_group": None,
        "superset_order": None,
        "has_guide": False,
        "weekly_prescriptions": [],
    }
    return {
        "id": 40_001,
        "title": "Силовая база",
        "slug": "demo-strength-base",
        "goal": "muscle_gain",
        "level": "intermediate",
        "split_type": "upper_lower",
        "owner_user_id": session.user_id,
        "owner_telegram_user_id": None,
        "owner_full_name": "Демо-профиль",
        "created_by_user_id": session.user_id,
        "is_public": False,
        "is_example": False,
        "is_assigned_to_current_user": True,
        "is_active_for_current_user": True,
        "can_edit": False,
        "assigned_by_user_id": None,
        "assigned_by_full_name": None,
        "assigned_program_id": 41_001,
        "assigned_program_status": "active",
        "assigned_program_start_date": _iso(_today(session) - timedelta(days=21)),
        "assigned_program_duration_weeks": 8,
        "current_revision_number": 1,
        "default_duration_weeks": 8,
        "days": [
            {"id": 42_001, "day_number": 1, "title": "Верх тела", "exercises": [exercise]},
            {"id": 42_002, "day_number": 2, "title": "Ноги и корпус", "exercises": [exercise]},
        ],
    }


def _client(session: _DemoSession, slug: str) -> dict[str, Any]:
    names = {"alexey": "Алексей", "maria": "Мария", "ivan": "Иван"}
    return {
        "id": DEMO_CLIENT_IDS[slug],
        "invite_id": None,
        "telegram_user_id": None,
        "username": slug,
        "full_name": names[slug],
        "birth_date": None,
        "goal": "muscle_gain",
        "level": "intermediate",
        "height_cm": 180,
        "weight_kg": 77,
        "workouts_per_week": 4,
        "cardio_trainings_per_week": 2,
        "resting_heart_rate": None,
        "body_priority": {"mode": "balanced", "muscle_group_ids": []},
        "training_preferences": None,
        "timezone": "Europe/Moscow",
        "kbju": _nutrition_target(DEMO_CLIENT_IDS[slug], _today(session), session),
        "status": "active",
        "operational_status": session.state.setdefault("crm_operational_status", {}).get(
            slug, "active"
        ),
    }


def _pending_client() -> dict[str, Any]:
    return {
        "id": None,
        "invite_id": 54_001,
        "telegram_user_id": None,
        "username": None,
        "full_name": "Елена · ожидает подтверждения",
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


def _assigned_program(session: _DemoSession, slug: str) -> dict[str, Any]:
    names = {"alexey": "Алексей", "maria": "Мария", "ivan": "Иван"}
    return {
        "id": 43_000 + DEMO_CLIENT_IDS[slug] - 51_000,
        "client_id": DEMO_CLIENT_IDS[slug],
        "client_telegram_user_id": None,
        "client_username": slug,
        "client_full_name": names[slug],
        "template_id": 40_001,
        "title": "Силовая база",
        "goal": "muscle_gain",
        "level": "intermediate",
        "assigned_at": _iso(_now(session) - timedelta(days=21)),
        "is_active": True,
        "status": "active",
        "start_date": _iso(_today(session) - timedelta(days=21)),
        "duration_weeks": 8,
        "schedule_weekdays": [0, 2, 4, 5],
        "completed_at": None,
        "workouts_total": 32,
        "workouts_completed": 8,
        "workouts_planned": 24,
        "next_workout_date": _iso(_today(session) + timedelta(days=2)),
        "current_revision_number": 1,
    }


def _crm_client_name(client_id: int) -> str:
    return {
        DEMO_CLIENT_IDS["alexey"]: "Алексей",
        DEMO_CLIENT_IDS["maria"]: "Мария",
        DEMO_CLIENT_IDS["ivan"]: "Иван",
    }.get(client_id, "Демо-клиент")


def _crm_session(
    session: _DemoSession,
    session_id: int,
    client_id: int,
    day_offset: int,
    hour: int,
    *,
    status: str = "scheduled",
    format_name: str = "online",
    location: str | None = "Telegram-звонок",
) -> dict[str, Any]:
    starts_at = datetime.combine(
        _today(session) + timedelta(days=day_offset), datetime.min.time()
    ).replace(hour=hour, minute=0)
    return {
        "id": session_id,
        "client_id": client_id,
        "client_name": _crm_client_name(client_id),
        "starts_at": _iso(starts_at),
        "starts_at_utc": _iso(starts_at - timedelta(hours=3)),
        "timezone": "Europe/Moscow",
        "duration_minutes": 60,
        "format": format_name,
        "location": location,
        "status": status,
        "private_note": "Проверить самочувствие и технику базовых движений.",
        "package_id": 72001 if client_id == DEMO_CLIENT_IDS["alexey"] else None,
        "package_balance": 2 if client_id == DEMO_CLIENT_IDS["alexey"] else None,
        "user_workout_id": DEMO_WORKOUT_ID if client_id == DEMO_CLIENT_IDS["alexey"] else None,
        "series_id": None,
        "occurrence_key": None,
        "created_at": _iso(_now(session)),
        "updated_at": _iso(_now(session)),
    }


def _crm_package(
    session: _DemoSession,
    package_id: int,
    client_id: int,
    *,
    counts: bool = True,
    state: str = "active",
    included_sessions: int | None = None,
    charged_sessions: int | None = None,
) -> dict[str, Any]:
    included = (
        included_sessions if counts and included_sessions is not None else 10 if counts else None
    )
    charged = charged_sessions if counts and charged_sessions is not None else 8 if counts else 0
    return {
        "id": package_id,
        "client_id": client_id,
        "client_name": _crm_client_name(client_id),
        "name": "Сопровождение · 10 встреч" if counts else "Разбор техники",
        "counts_sessions": counts,
        "included_sessions": included,
        "charged_sessions": charged,
        "reversed_sessions": 0,
        "balance": included - charged
        if counts and included is not None and charged is not None
        else None,
        "starts_on": _iso(_today(session) - timedelta(days=14)),
        "expires_on": _iso(_today(session) + timedelta(days=45)),
        "state": state,
        "note": "Демо-данные, не связаны с реальным клиентом.",
        "created_at": _iso(_now(session) - timedelta(days=14)),
        "updated_at": _iso(_now(session)),
    }


def _crm_task(
    session: _DemoSession, task_id: int, client_id: int, day_offset: int, state: str = "open"
) -> dict[str, Any]:
    due_at = datetime.combine(
        _today(session) + timedelta(days=day_offset), datetime.min.time()
    ).replace(hour=12, minute=0)
    return {
        "id": task_id,
        "client_id": client_id,
        "client_name": _crm_client_name(client_id),
        "title": "Отправить короткий комментарий по технике",
        "due_at": _iso(due_at),
        "due_at_utc": _iso(due_at - timedelta(hours=3)),
        "timezone": "Europe/Moscow",
        "state": state,
        "completed_at": _iso(_now(session)) if state == "completed" else None,
        "created_at": _iso(_now(session) - timedelta(days=1)),
        "updated_at": _iso(_now(session)),
    }


def _crm_payment(
    session: _DemoSession,
    payment_id: int,
    client_id: int,
    *,
    expected_amount_minor: int = 35_000,
    paid_amount_minor: int = 15_000,
    package_id: int | None = 72001,
) -> dict[str, Any]:
    status = (
        "paid"
        if paid_amount_minor == expected_amount_minor
        else "partial"
        if paid_amount_minor
        else "expected"
    )
    return {
        "id": payment_id,
        "client_id": client_id,
        "client_name": _crm_client_name(client_id),
        "package_id": package_id,
        "expected_amount_minor": expected_amount_minor,
        "paid_amount_minor": paid_amount_minor,
        "currency": "RUB",
        "payment_date": _iso(_today(session)),
        "method": "перевод",
        "note": "Остаток ожидается до следующей встречи.",
        "status": status,
        "created_at": _iso(_now(session) - timedelta(days=2)),
        "updated_at": _iso(_now(session)),
    }


def _crm_state(session: _DemoSession) -> dict[str, list[dict[str, Any]]]:
    state = session.state
    state.setdefault(
        "crm_sessions",
        [
            _crm_session(session, 71001, DEMO_CLIENT_IDS["alexey"], 0, 19),
            _crm_session(
                session,
                71002,
                DEMO_CLIENT_IDS["maria"],
                0,
                12,
                status="completed",
                format_name="gym",
                location="Зал · Ленинградская",
            ),
            _crm_session(session, 71003, DEMO_CLIENT_IDS["ivan"], 0, 17, status="no_show"),
            _crm_session(
                session,
                71004,
                DEMO_CLIENT_IDS["alexey"],
                1,
                18,
                status="cancelled",
            ),
        ],
    )
    state.setdefault(
        "crm_packages",
        [
            _crm_package(session, 72001, DEMO_CLIENT_IDS["alexey"]),
            _crm_package(session, 72002, DEMO_CLIENT_IDS["maria"], counts=False),
            _crm_package(
                session,
                72003,
                DEMO_CLIENT_IDS["maria"],
                included_sessions=12,
                charged_sessions=12,
                state="finished",
            ),
            _crm_package(
                session,
                72004,
                DEMO_CLIENT_IDS["ivan"],
                included_sessions=6,
                charged_sessions=0,
                state="cancelled",
            ),
        ],
    )
    state.setdefault(
        "crm_payments",
        [
            _crm_payment(session, 73001, DEMO_CLIENT_IDS["alexey"]),
            _crm_payment(
                session,
                73002,
                DEMO_CLIENT_IDS["maria"],
                expected_amount_minor=20_000,
                paid_amount_minor=0,
                package_id=72002,
            ),
            _crm_payment(
                session,
                73003,
                DEMO_CLIENT_IDS["ivan"],
                expected_amount_minor=12_000,
                paid_amount_minor=12_000,
                package_id=72004,
            ),
        ],
    )
    state.setdefault(
        "crm_tasks",
        [
            _crm_task(session, 74001, DEMO_CLIENT_IDS["alexey"], -1),
            _crm_task(session, 74002, DEMO_CLIENT_IDS["maria"], 0),
        ],
    )
    return {
        "sessions": state["crm_sessions"],
        "packages": state["crm_packages"],
        "payments": state["crm_payments"],
        "tasks": state["crm_tasks"],
    }


def _crm_agenda(session: _DemoSession, raw_path: str) -> dict[str, Any]:
    state = _crm_state(session)
    date_from_raw = _query(raw_path, "date_from")
    date_to_raw = _query(raw_path, "date_to")
    try:
        date_from = date.fromisoformat(date_from_raw) if date_from_raw else _today(session)
        date_to = date.fromisoformat(date_to_raw) if date_to_raw else date_from + timedelta(days=6)
    except ValueError as exc:
        raise DemoActionForbiddenError from exc
    items = [
        item
        for item in state["sessions"]
        if date_from <= date.fromisoformat(str(item["starts_at"])[:10]) <= date_to
    ]
    return {
        "date_from": _iso(date_from),
        "date_to": _iso(date_to),
        "timezone": "Europe/Moscow",
        "items": items,
    }


def _crm_operations_today(session: _DemoSession) -> dict[str, Any]:
    state = _crm_state(session)
    today = _today(session)
    return {
        "date": _iso(today),
        "timezone": "Europe/Moscow",
        "sessions": [
            item for item in state["sessions"] if str(item["starts_at"]).startswith(_iso(today))
        ],
        "overdue_tasks": [
            item
            for item in state["tasks"]
            if item["state"] == "open" and date.fromisoformat(str(item["due_at"])[:10]) < today
        ],
        "due_tasks": [
            item
            for item in state["tasks"]
            if item["state"] == "open" and date.fromisoformat(str(item["due_at"])[:10]) == today
        ],
        "low_packages": [
            item
            for item in state["packages"]
            if item["balance"] is not None and item["balance"] <= 2
        ],
        "payment_facts": [
            item for item in state["payments"] if item["status"] in {"expected", "partial"}
        ],
    }


def _client_analytics(session: _DemoSession, client_id: int) -> dict[str, Any]:
    return {
        "workouts_total": 32,
        "workouts_completed": 8,
        "workouts_skipped": 1,
        "workouts_missed": 0,
        "adherence_percent": 88,
        "current_streak": 3,
        "weight_change_kg": -0.7,
        "weights": [
            {"measured_on": _iso(_today(session) - timedelta(days=28)), "weight_kg": 77.8},
            {"measured_on": _iso(_today(session)), "weight_kg": 77.1},
        ],
        "weekly_volume": [
            {
                "week_start": _iso(_today(session) - timedelta(days=21)),
                "completed_workouts": 2,
                "volume_kg": 5_920,
            },
            {
                "week_start": _iso(_today(session) - timedelta(days=14)),
                "completed_workouts": 2,
                "volume_kg": 6_220,
            },
            {
                "week_start": _iso(_today(session) - timedelta(days=7)),
                "completed_workouts": 3,
                "volume_kg": 6_480,
            },
        ],
        "personal_records": [
            {
                "exercise_id": 1_001,
                "exercise_title": "Жим гантелей лёжа",
                "max_weight_kg": 18,
                "best_set_volume_kg": 180,
                "last_performed_on": _iso(_today(session) - timedelta(days=2)),
            }
        ],
    }


def _client_timeline(session: _DemoSession) -> list[dict[str, Any]]:
    sets = [
        {
            "set_number": number,
            "actual_reps": 10,
            "actual_weight": 18.0,
            "rir": "2",
            "set_kind": "working",
            "reached_failure": False,
            "is_completed": True,
        }
        for number in range(1, 4)
    ]
    return [
        {
            "id": DEMO_WORKOUT_ID + 10,
            "scheduled_date": _iso(_today(session) - timedelta(days=2)),
            "scheduled_time": "19:00:00",
            "title": "Ноги и корпус",
            "status": "completed",
            "completed_at": _iso(_now(session) - timedelta(days=2)),
            "completed_sets": 18,
            "volume_kg": 6_480,
            "completion_feedback": "as_expected",
            "completion_note": None,
            "exercises": [
                {
                    "workout_exercise_id": 62_001,
                    "exercise_id": 1_001,
                    "exercise_title": "Присед со штангой",
                    "notes": "Контролируйте глубину и темп.",
                    "superset_group": None,
                    "superset_order": None,
                    "sets": sets,
                }
            ],
        }
    ]


def _comments(session: _DemoSession, workout_id: int, client_slug: str) -> list[dict[str, Any]]:
    comment = next(
        (
            item["comment"]
            for item in session.state.get("clients", [])
            if item["id"] == client_slug and item["comment"]
        ),
        None,
    )
    if not comment:
        return []
    now = _iso(_now(session))
    return [
        {
            "id": 99_001,
            "trainer_author_id": session.user_id,
            "client_user_id": DEMO_CLIENT_IDS[client_slug],
            "workout_id": workout_id,
            "workout_exercise_id": None,
            "body": comment,
            "body_format": "plain_text",
            "created_at": now,
            "updated_at": None,
            "revisions": [],
        }
    ]


def _client_slug(client_id: int) -> str:
    for slug, value in DEMO_CLIENT_IDS.items():
        if value == client_id:
            return slug
    raise DemoActionForbiddenError


def _request_body(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise DemoActionForbiddenError
    return body


def _validate_workout_set_payload(payload: dict[str, Any]) -> None:
    allowed = {
        "actual_reps",
        "actual_weight",
        "duration_minutes",
        "distance_km",
        "average_heart_rate_bpm",
        "heart_rate_zone",
        "rir",
        "set_kind",
        "reached_failure",
        "is_completed",
        "expected_version",
        "mutation_id",
    }
    if set(payload) - allowed:
        raise DemoActionForbiddenError
    integer_ranges = {
        "actual_reps": (0, 5_000),
        "duration_minutes": (1, 600),
        "average_heart_rate_bpm": (30, 250),
        "heart_rate_zone": (1, 5),
        "expected_version": (1, 1_000_000),
    }
    for key, (minimum, maximum) in integer_ranges.items():
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise DemoActionForbiddenError
    for key, minimum, maximum in (("actual_weight", 0, 1_000), ("distance_km", 0, 1_000)):
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise DemoActionForbiddenError
        if value < minimum or value > maximum or (key == "distance_km" and value == 0):
            raise DemoActionForbiddenError
    for key in ("reached_failure", "is_completed"):
        value = payload.get(key)
        if value is not None and not isinstance(value, bool):
            raise DemoActionForbiddenError
    if payload.get("rir") not in {None, "0", "1", "2", "3", "4+"}:
        raise DemoActionForbiddenError
    if payload.get("set_kind") not in {None, "warmup", "working", "drop"}:
        raise DemoActionForbiddenError
    mutation_id = payload.get("mutation_id")
    if mutation_id is not None and (
        not isinstance(mutation_id, str) or not 16 <= len(mutation_id) <= 64
    ):
        raise DemoActionForbiddenError
    if (payload.get("expected_version") is None) != (mutation_id is None):
        raise DemoActionForbiddenError


def _apply_workout_set(
    session: _DemoSession,
    set_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if session.scenario != "self_training" or session.state["screen"] != "active_workout":
        raise DemoTransitionError
    _validate_workout_set_payload(payload)
    number = set_id - 60_001
    total_sets = int(session.state.get("total_sets", 3))
    if number < 1 or number > total_sets:
        raise DemoActionForbiddenError
    mutations = session.state.setdefault("workout_mutations", {})
    mutation_id = payload.get("mutation_id")
    if mutation_id is not None and mutations.get(mutation_id) == set_id:
        return _workout_set(session, number)
    current = _workout_set(session, number)
    expected_version = payload.get("expected_version")
    if expected_version is not None and expected_version != current["version"]:
        raise DemoTransitionError
    details = session.state.setdefault("workout_set_details", {}).setdefault(str(number), {})
    changed = False
    for key in (
        "actual_reps",
        "actual_weight",
        "duration_minutes",
        "distance_km",
        "average_heart_rate_bpm",
        "heart_rate_zone",
        "rir",
        "set_kind",
        "reached_failure",
    ):
        if key in payload and payload[key] != current[key]:
            details[key] = payload[key]
            changed = True
    if "is_completed" in payload and payload["is_completed"] is not None:
        next_completed = payload["is_completed"]
        if next_completed != current["is_completed"]:
            completed_numbers = session.state.setdefault("workout_completed_sets", [])
            if next_completed:
                completed_numbers.append(number)
            else:
                completed_numbers.remove(number)
            session.state["completed_sets"] = len(completed_numbers)
            changed = True
    if changed:
        details["version"] = current["version"] + 1
        session.revision += 1
    if mutation_id is not None:
        mutations[mutation_id] = set_id
        while len(mutations) > 128:
            mutations.pop(next(iter(mutations)))
    return _workout_set(session, number)


def _apply_workout_action(store: DemoSessionStore, session: _DemoSession, action: str) -> None:
    if store._apply_allowed_action(session, action, None, None):
        session.revision += 1


def _finish_workout(
    store: DemoSessionStore,
    session: _DemoSession,
    body: Any,
) -> None:
    if session.scenario != "self_training" or session.state["screen"] != "active_workout":
        if session.state.get("screen") == "summary":
            return
        raise DemoTransitionError
    completed = int(session.state.get("completed_sets", 0))
    total = int(session.state.get("total_sets", 3))
    payload = _request_body(body) if body is not None else {}
    if set(payload) - {"confirm_incomplete"} or not isinstance(
        payload.get("confirm_incomplete", False), bool
    ):
        raise DemoActionForbiddenError
    if completed < total and not payload.get("confirm_incomplete", False):
        raise DemoTransitionError
    if completed < total:
        session.state["screen"] = "summary"
        session.state["duration_minutes"] = 46
        session.state["total_volume_kg"] = round(2_280 * completed / max(total, 1), 1)
        session.revision += 1
        return
    _apply_workout_action(store, session, "finish_workout")


def handle_demo_transport(
    store: DemoSessionStore,
    session: _DemoSession,
    raw_path: str,
    method: str,
    body: Any,
) -> Any:
    parsed = urlsplit(raw_path)
    if parsed.scheme or parsed.netloc or parsed.fragment or not parsed.path.startswith("/api/v1/"):
        raise DemoActionForbiddenError
    path = parsed.path
    parts = path.removeprefix("/api/v1/").strip("/").split("/")
    if not parts or any(not part or len(part) > 96 for part in parts):
        raise DemoActionForbiddenError

    if method == "GET":
        if path == "/api/v1/me":
            return _user(session)
        if path == "/api/v1/workouts/today":
            return _workout(session)
        if path in {"/api/v1/workouts/week", "/api/v1/workouts/schedule"}:
            return _schedule(session)
        if path == "/api/v1/workouts/cardio":
            return []
        if path == "/api/v1/workouts/progress/summary":
            return _progress_summary(session, _period_days(_query(raw_path, "period_days")))
        if path == "/api/v1/workouts/progress/training-analytics":
            return _training_analytics(session)
        if path == "/api/v1/workouts/progress/nutrition-report":
            return _nutrition_report(session)
        if path == "/api/v1/workouts/progress":
            return {
                "workouts_total": 32,
                "workouts_completed": 12,
                "workouts_skipped": 1,
                "workouts_missed": 0,
                "adherence_percent": 82,
                "current_streak": 3,
                "weight_change_kg": -0.7,
                "weights": [],
                "weekly_volume": [],
                "personal_records": [],
            }
        if path == "/api/v1/workouts/diary/custom-definitions":
            return [
                {
                    "id": 93_001,
                    "label": "Пользовательский показатель",
                    "unit": "cm",
                    "archived": False,
                    "created_at": _iso(_now(session) - timedelta(days=60)),
                    "updated_at": _iso(_now(session) - timedelta(days=60)),
                }
            ]
        if path == "/api/v1/workouts/diary":
            return [
                {
                    "id": 91_001,
                    "measured_on": _iso(_today(session) - timedelta(days=28)),
                    "weight_kg": 77.8,
                    "chest_cm": None,
                    "waist_cm": None,
                    "hips_cm": None,
                    "biceps_cm": None,
                    "thigh_cm": None,
                    "note": None,
                    "custom_values": [
                        {
                            "definition_id": 93_001,
                            "label": "Пользовательский показатель",
                            "unit": "cm",
                            "value": 86.0,
                            "archived": False,
                        }
                    ],
                    "created_at": _iso(_now(session) - timedelta(days=28)),
                },
                {
                    "id": 91_002,
                    "measured_on": _iso(_today(session)),
                    "weight_kg": 77.1,
                    "chest_cm": None,
                    "waist_cm": None,
                    "hips_cm": None,
                    "biceps_cm": None,
                    "thigh_cm": None,
                    "note": None,
                    "custom_values": [
                        {
                            "definition_id": 93_001,
                            "label": "Пользовательский показатель",
                            "unit": "cm",
                            "value": 84.0,
                            "archived": False,
                        }
                    ],
                    "created_at": _iso(_now(session)),
                },
            ]
        if (
            len(parts) == 3
            and parts[0] == "workouts"
            and parts[1].isdigit()
            and parts[2] == "comments"
        ):
            return []
        if path == "/api/v1/workouts/history/summary":
            return {"workouts_completed": 12, "completed_sets": 54, "volume_kg": 24_680}
        if path == "/api/v1/workouts/history":
            return _client_timeline(session)
        if path == "/api/v1/check-ins/weekly/current":
            return {
                "status": "not_submitted",
                "week_start": _iso(_today(session) - timedelta(days=_today(session).weekday())),
                "week_end": _iso(_today(session) + timedelta(days=6 - _today(session).weekday())),
                "submitted_on": None,
                "training_load": None,
                "recovery": None,
                "hunger": None,
                "adherence_difficulty": None,
                "note": None,
            }
        if path == "/api/v1/check-ins/daily":
            return {
                "local_date": _iso(_today(session)),
                "status": "not_submitted",
                "energy": None,
                "sleep_quality": None,
                "stress": None,
                "soreness": None,
                "note": None,
            }
        if path == "/api/v1/check-ins/weekly":
            return {"items": [], "total": 0}
        if path == "/api/v1/nutrition/diary":
            return _nutrition_day(session, _query(raw_path, "diary_date"))
        if path == "/api/v1/nutrition/hydration":
            return _hydration_day(session, _query(raw_path, "diary_date"))
        if path in {"/api/v1/nutrition/foods/recent", "/api/v1/nutrition/foods/favorites"}:
            item = _nutrition_item(session)
            return {"items": [item], "total": 1, "limit": 12, "offset": 0}
        if path == "/api/v1/nutrition/foods/search":
            item = _nutrition_item(session)
            return {
                "items": [item],
                "total": 1,
                "limit": 20,
                "offset": 0,
                "external_items": [],
                "provider_status": "not_needed",
                "provider_statuses": [],
            }
        if path == "/api/v1/nutrition/targets/current":
            return _nutrition_target(session.user_id, _today(session), session)
        if path == "/api/v1/nutrition/targets/history":
            return {
                "items": [_nutrition_target(session.user_id, _today(session), session)],
                "total": 1,
                "limit": 20,
                "offset": 0,
            }
        if path == "/api/v1/nutrition/recipes":
            return {"items": [], "total": 0, "limit": 20, "offset": 0}
        if path == "/api/v1/programs/exercises":
            return _exercise_catalog()
        if path in {"/api/v1/programs/templates/mine", "/api/v1/programs/templates/hidden"}:
            return [] if path.endswith("hidden") else [_program_template(session)]
        if path == "/api/v1/coach/clients":
            return [_client(session, slug) for slug in ("alexey", "maria", "ivan")] + [
                _pending_client()
            ]
        if path == "/api/v1/coach/assigned-programs":
            return [_assigned_program(session, slug) for slug in ("alexey", "maria")]
        if path == "/api/v1/coach/client-summaries":
            items = []
            for slug in ("alexey", "maria", "ivan"):
                item = _progress_summary(session, 30, DEMO_CLIENT_IDS[slug])
                item["client_name"] = {"alexey": "Алексей", "maria": "Мария", "ivan": "Иван"}[slug]
                items.append(item)
            return {"items": items, "total": len(items), "limit": 100, "offset": 0}
        if path == "/api/v1/coach/attention":
            return {
                "items": [
                    {
                        "key": "without_program:51003:51003",
                        "kind": "without_program",
                        "client": {"id": DEMO_CLIENT_IDS["ivan"], "name": "Иван"},
                        "title": "Нет активной программы",
                        "reason": "Назначьте следующий рабочий план клиента.",
                        "source_kind": "client",
                        "source_id": DEMO_CLIENT_IDS["ivan"],
                        "source_state": "active",
                        "action": "assign_program",
                        "destination": f"/coach?client_id={DEMO_CLIENT_IDS['ivan']}",
                        "created_at": _iso(_now(session)),
                    }
                ],
                "total": 1,
                "generated_at": _iso(_now(session)),
            }
        if path == "/api/v1/coach/operations/today":
            return _crm_operations_today(session)
        if path == "/api/v1/coach/agenda":
            return _crm_agenda(session, raw_path)
        if path == "/api/v1/coach/packages":
            return _crm_state(session)["packages"]
        if path == "/api/v1/coach/payments":
            return _crm_state(session)["payments"]
        if path == "/api/v1/coach/tasks":
            return _crm_state(session)["tasks"]
        if len(parts) >= 4 and parts[:2] == ["coach", "clients"] and parts[2].isdigit():
            client_id = int(parts[2])
            slug = _client_slug(client_id)
            if len(parts) == 4 and parts[3] == "operations":
                state = _crm_state(session)
                return {
                    key: [item for item in values if int(item["client_id"]) == client_id]
                    for key, values in state.items()
                }
            if len(parts) == 4 and parts[3] == "analytics":
                return _client_analytics(session, client_id)
            if len(parts) == 4 and parts[3] == "workouts":
                return _client_timeline(session)
            if len(parts) == 4 and parts[3] == "weekly-check-ins":
                period_end = _today(session)
                period_start = period_end - timedelta(days=6)
                return {
                    "items": [
                        {
                            "id": 95_001,
                            "user_id": client_id,
                            "week_start": _iso(period_start),
                            "week_end": _iso(period_end),
                            "submitted_on": _iso(period_end),
                            "timezone": "Europe/Moscow",
                            "status": "completed",
                            "summary_version": "weekly-check-in-summary-v1",
                            "summary": {
                                "ruleset_version": "weekly-check-in-summary-v1",
                                "period_start": _iso(period_start),
                                "period_end": _iso(period_end),
                                "goal": "muscle_gain",
                                "training": {
                                    "planned_workouts": 4,
                                    "completed_workouts": 3,
                                    "adherence": {
                                        "status": "available",
                                        "percent": 75,
                                        "achieved": 3,
                                        "evaluated": 4,
                                        "weight": 1,
                                        "reason": None,
                                    },
                                },
                                "nutrition": {
                                    "logged_days": 5,
                                    "complete_days": 4,
                                    "incomplete_days": 1,
                                    "fasted_days": 0,
                                    "unlogged_days": 2,
                                    "average_calories": 2_010,
                                    "target_calories": 2_150,
                                    "average_protein_g": 132,
                                    "target_protein_g": 145,
                                    "calories_adherence": {
                                        "status": "available",
                                        "percent": 78,
                                        "achieved": 4,
                                        "evaluated": 5,
                                        "weight": 1,
                                        "reason": None,
                                    },
                                    "protein_adherence": {
                                        "status": "available",
                                        "percent": 81,
                                        "achieved": 4,
                                        "evaluated": 5,
                                        "weight": 1,
                                        "reason": None,
                                    },
                                    "current_target": None,
                                    "suspicious_low_days": [],
                                },
                                "anthropometry_trends": [],
                                "progression": {
                                    "training_volume_kg": 6_480,
                                    "new_personal_records": 1,
                                },
                                "data_sufficiency": {},
                            },
                            "training_load": 4,
                            "recovery": 3,
                            "hunger": 2,
                            "adherence_difficulty": 2,
                            "note": "На этой неделе восстановление было неровным.",
                            "created_at": _iso(_now(session)),
                        }
                    ],
                    "total": 1,
                    "limit": 12,
                    "offset": 0,
                }
            if (
                len(parts) == 6
                and parts[3] == "workouts"
                and parts[4].isdigit()
                and parts[5] == "comments"
            ):
                if int(parts[4]) == DEMO_WORKOUT_ID + 10:
                    return _comments(session, DEMO_WORKOUT_ID + 10, slug)
                raise DemoActionForbiddenError
            if len(parts) == 4 and parts[3] == "measurements":
                return [
                    {
                        "id": 92_001,
                        "measured_on": _iso(_today(session) - timedelta(days=28)),
                        "weight_kg": 77.8,
                        "chest_cm": None,
                        "waist_cm": None,
                        "hips_cm": None,
                        "biceps_cm": None,
                        "thigh_cm": None,
                        "note": None,
                        "custom_values": [
                            {
                                "definition_id": 93_001,
                                "label": "Пользовательский показатель",
                                "unit": "cm",
                                "value": 86.0,
                                "archived": False,
                            }
                        ],
                        "created_at": _iso(_now(session) - timedelta(days=28)),
                    },
                    {
                        "id": 92_002,
                        "measured_on": _iso(_today(session)),
                        "weight_kg": 77.1,
                        "chest_cm": None,
                        "waist_cm": None,
                        "hips_cm": None,
                        "biceps_cm": None,
                        "thigh_cm": None,
                        "note": None,
                        "custom_values": [
                            {
                                "definition_id": 93_001,
                                "label": "Пользовательский показатель",
                                "unit": "cm",
                                "value": 84.0,
                                "archived": False,
                            }
                        ],
                        "created_at": _iso(_now(session)),
                    },
                ]
            if len(parts) == 5 and parts[3] == "measurements" and parts[4] == "custom-definitions":
                return [
                    {
                        "id": 93_001,
                        "label": "Пользовательский показатель",
                        "unit": "cm",
                        "archived": False,
                        "created_at": _iso(_now(session) - timedelta(days=60)),
                        "updated_at": _iso(_now(session) - timedelta(days=60)),
                    }
                ]
            if len(parts) == 4 and parts[3] == "nutrition-report":
                return _nutrition_report(session, client_id)
            if len(parts) == 4 and parts[3] == "report-handoffs":
                if slug != "alexey":
                    return []
                period_end = _today(session)
                return [
                    {
                        "id": 94_001,
                        "trainer": {
                            "id": session.user_id,
                            "full_name": "Демо-тренер",
                            "username": "demo_trainer",
                        },
                        "period": "days_30",
                        "period_start": _iso(period_end - timedelta(days=29)),
                        "period_end": _iso(period_end),
                        "timezone": "Europe/Moscow",
                        "report_contract_version": "progress-report-v1",
                        "included_section_ids": ["overview", "training", "body", "nutrition"],
                        "created_at": _iso(_now(session) - timedelta(days=1)),
                        "delivery_status": "delivered",
                        "delivery_attempt": 1,
                        "client_comment": "На этой неделе восстановление было сложнее обычного — посмотрите, пожалуйста, объём.",
                        "live": True,
                    }
                ]
            if len(parts) == 4 and parts[3] == "programs":
                return []
            if len(parts) == 4 and parts[3] == "profile":
                return _client(session, slug)
        if path == "/api/v1/me/profile/body-priority-options":
            return {
                "items": [
                    {"id": "chest", "name": "Грудь"},
                    {"id": "back", "name": "Спина"},
                    {"id": "legs", "name": "Ноги"},
                ]
            }
        if path == "/api/v1/me/trainer-capability":
            return {
                "is_active": session.scenario == "trainer",
                "activated_now": False,
                "active_client_count": 3 if session.scenario == "trainer" else 0,
                "pending_invite_count": 0,
                "can_disable": False,
                "terms_version": "demo-v1",
            }
        if path == "/api/v1/me/exports/current":
            return {
                "status": "none",
                "export_id": None,
                "created_at": None,
                "completed_at": None,
                "expires_at": None,
                "filename": None,
                "content_size_bytes": None,
                "error_code": None,
            }
        if path == "/api/v1/notifications/settings":
            return {
                "workout_reminders_enabled": True,
                "weekly_check_in_reminders_enabled": True,
                "measurement_reminders_enabled": True,
                "meal_reminders_enabled": False,
                "hydration_reminders_enabled": True,
                "movement_reminders_enabled": False,
                "telegram_enabled": False,
                "telegram_linked": False,
                "reminder_hour": 19,
                "quiet_hours_start": "23:00:00",
                "quiet_hours_end": "07:00:00",
            }
        if path == "/api/v1/notifications/templates":
            return []
        if path == "/api/v1/notifications":
            return []
        if path == "/api/v1/notifications/web-push/config":
            return {"enabled": False, "application_server_key": None}
        if path == "/api/v1/notifications/web-push/status":
            return {"enabled": False, "registered": False}
        if path == "/api/v1/ai-coach/status":
            return {"ui_enabled": False, "generic_available": False, "personal_available": False}
        raise DemoActionForbiddenError

    if method == "POST":
        if len(parts) == 3 and parts[0] == "workouts" and parts[2] == "start":
            if parts[1] != str(DEMO_WORKOUT_ID):
                raise DemoActionForbiddenError
            _apply_workout_action(store, session, "start_workout")
            return _workout(session)
        if len(parts) == 3 and parts[0] == "workouts" and parts[2] == "finish":
            if parts[1] != str(DEMO_WORKOUT_ID):
                raise DemoActionForbiddenError
            _finish_workout(store, session, body)
            return _workout(session)
        if path == "/api/v1/nutrition/diary/entries":
            payload = _request_body(body)
            if session.scenario != "nutrition":
                raise DemoActionForbiddenError
            changed = store._apply_allowed_action(session, "add_recent", None, None)
            if changed:
                session.revision += 1
            return _nutrition_entry(
                session,
                str(payload.get("diary_date") or _iso(_today(session))),
                str(payload.get("meal_type") or "breakfast"),
            )
        if path == "/api/v1/nutrition/hydration/entries":
            return _add_hydration_entry(session, _request_body(body))
        if path == "/api/v1/nutrition/hydration/goal":
            return _hydration_goal(session, _request_body(body))
        if path == "/api/v1/nutrition/hydration/presets":
            return _hydration_preset(session, _request_body(body))
        if path == "/api/v1/coach/sessions":
            payload = _request_body(body)
            session_client_id = payload.get("client_id")
            starts_at = payload.get("starts_at")
            if (
                isinstance(session_client_id, bool)
                or not isinstance(session_client_id, int)
                or session_client_id not in DEMO_CLIENT_IDS.values()
                or not isinstance(starts_at, str)
            ):
                raise DemoActionForbiddenError
            state = _crm_state(session)
            next_id = max([71000, *(int(item["id"]) for item in state["sessions"])]) + 1
            created = _crm_session(
                session,
                next_id,
                session_client_id,
                0,
                18,
                format_name=str(payload.get("format") or "other"),
                location=payload.get("location"),
            )
            created["starts_at"] = starts_at
            created["starts_at_utc"] = starts_at
            created["duration_minutes"] = int(payload.get("duration_minutes") or 60)
            created["private_note"] = payload.get("private_note")
            created["package_id"] = payload.get("package_id")
            created["user_workout_id"] = payload.get("user_workout_id")
            state["sessions"].append(created)
            session.revision += 1
            return [created]
        if path == "/api/v1/coach/packages":
            payload = _request_body(body)
            package_client_id = payload.get("client_id")
            name = payload.get("name")
            if (
                isinstance(package_client_id, bool)
                or not isinstance(package_client_id, int)
                or package_client_id not in DEMO_CLIENT_IDS.values()
                or not isinstance(name, str)
                or not name.strip()
            ):
                raise DemoActionForbiddenError
            state = _crm_state(session)
            next_id = max([72000, *(int(item["id"]) for item in state["packages"])]) + 1
            created = _crm_package(
                session,
                next_id,
                package_client_id,
                counts=bool(payload.get("counts_sessions", True)),
            )
            created["name"] = name.strip()
            created["included_sessions"] = payload.get("included_sessions")
            created["balance"] = payload.get("included_sessions")
            state["packages"].append(created)
            session.revision += 1
            return created
        if path == "/api/v1/coach/payments":
            payload = _request_body(body)
            payment_client_id = payload.get("client_id")
            expected = payload.get("expected_amount_minor")
            paid = payload.get("paid_amount_minor", 0)
            if (
                isinstance(payment_client_id, bool)
                or not isinstance(payment_client_id, int)
                or payment_client_id not in DEMO_CLIENT_IDS.values()
                or isinstance(expected, bool)
                or not isinstance(expected, int)
                or expected <= 0
                or isinstance(paid, bool)
                or not isinstance(paid, int)
                or paid < 0
                or paid > expected
            ):
                raise DemoActionForbiddenError
            state = _crm_state(session)
            next_id = max([73000, *(int(item["id"]) for item in state["payments"])]) + 1
            payment = _crm_payment(session, next_id, payment_client_id)
            payment.update(
                {
                    "expected_amount_minor": expected,
                    "paid_amount_minor": paid,
                    "currency": str(payload.get("currency") or "RUB").upper(),
                    "method": payload.get("method"),
                    "note": payload.get("note"),
                    "status": "paid" if paid == expected else "partial" if paid else "expected",
                }
            )
            state["payments"].append(payment)
            session.revision += 1
            return payment
        if path == "/api/v1/coach/tasks":
            payload = _request_body(body)
            task_client_id = payload.get("client_id")
            title = payload.get("title")
            due_at = payload.get("due_at")
            if (
                isinstance(task_client_id, bool)
                or not isinstance(task_client_id, int)
                or task_client_id not in DEMO_CLIENT_IDS.values()
                or not isinstance(title, str)
                or not title.strip()
                or not isinstance(due_at, str)
            ):
                raise DemoActionForbiddenError
            state = _crm_state(session)
            next_id = max([74000, *(int(item["id"]) for item in state["tasks"])]) + 1
            task = _crm_task(session, next_id, task_client_id, 0)
            task["title"] = title.strip()
            task["due_at"] = due_at
            task["due_at_utc"] = due_at
            state["tasks"].append(task)
            session.revision += 1
            return task
        if (
            len(parts) == 6
            and parts[0:2] == ["coach", "clients"]
            and parts[2].isdigit()
            and parts[3] == "workouts"
            and parts[4].isdigit()
            and parts[5] == "comments"
        ):
            payload = _request_body(body)
            comment = payload.get("body")
            if not isinstance(comment, str) or not comment.strip():
                raise DemoActionForbiddenError
            comment = " ".join(comment.split())
            slug = _client_slug(int(parts[2]))
            selected_changed = session.state.get("selected_client_id") != slug
            session.state["selected_client_id"] = slug
            comment_changed = store._apply_allowed_action(session, "save_comment", comment, slug)
            if selected_changed or comment_changed:
                session.revision += 1
            now = _iso(_now(session))
            return {
                "id": 99_001,
                "trainer_author_id": session.user_id,
                "client_user_id": DEMO_CLIENT_IDS[slug],
                "workout_id": int(parts[4]),
                "workout_exercise_id": payload.get("workout_exercise_id"),
                "body": " ".join(comment.split()),
                "body_format": "plain_text",
                "created_at": now,
                "updated_at": None,
                "revisions": [],
            }
        if path == "/api/v1/me/profile/heart-rates/preview":
            return {
                "status": "unavailable",
                "message": "Для демо-профиля расчёт не требуется.",
                "zones": [],
            }
        raise DemoActionForbiddenError

    if method == "PATCH" and len(parts) == 3 and parts[0] == "workouts" and parts[1] == "sets":
        set_id = int(parts[2]) if parts[2].isdigit() else 0
        return _apply_workout_set(session, set_id, _request_body(body))

    if (
        method == "PATCH"
        and len(parts) == 3
        and parts[:2] == ["coach", "sessions"]
        and parts[2].isdigit()
    ):
        session_id = int(parts[2])
        state = _crm_state(session)
        stored = next((item for item in state["sessions"] if int(item["id"]) == session_id), None)
        if stored is None:
            raise DemoActionForbiddenError
        payload = _request_body(body)
        for key in ("starts_at", "timezone", "location", "private_note", "status", "format"):
            if key in payload:
                stored[key] = payload[key]
        if "duration_minutes" in payload:
            stored["duration_minutes"] = payload["duration_minutes"]
        stored["updated_at"] = _iso(_now(session))
        session.revision += 1
        return stored

    if (
        method == "PATCH"
        and len(parts) == 4
        and parts[:2] == ["coach", "packages"]
        and parts[2].isdigit()
        and parts[3] == "state"
    ):
        package_id = int(parts[2])
        stored = next(
            (item for item in _crm_state(session)["packages"] if int(item["id"]) == package_id),
            None,
        )
        if stored is None:
            raise DemoActionForbiddenError
        payload = _request_body(body)
        if payload.get("state") not in {"active", "finished", "cancelled"}:
            raise DemoActionForbiddenError
        stored["state"] = payload["state"]
        stored["updated_at"] = _iso(_now(session))
        session.revision += 1
        return stored

    if (
        method == "PATCH"
        and len(parts) == 3
        and parts[:2] == ["coach", "payments"]
        and parts[2].isdigit()
    ):
        payment_id = int(parts[2])
        stored = next(
            (item for item in _crm_state(session)["payments"] if int(item["id"]) == payment_id),
            None,
        )
        if stored is None:
            raise DemoActionForbiddenError
        payload = _request_body(body)
        expected = payload.get("expected_amount_minor", stored["expected_amount_minor"])
        paid = payload.get("paid_amount_minor", stored["paid_amount_minor"])
        if (
            isinstance(expected, bool)
            or not isinstance(expected, int)
            or expected <= 0
            or isinstance(paid, bool)
            or not isinstance(paid, int)
            or paid < 0
            or paid > expected
        ):
            raise DemoActionForbiddenError
        stored["expected_amount_minor"] = expected
        stored["paid_amount_minor"] = paid
        if "currency" in payload:
            stored["currency"] = str(payload["currency"]).upper()
        if "method" in payload:
            stored["method"] = payload["method"]
        if "note" in payload:
            stored["note"] = payload["note"]
        stored["status"] = (
            "cancelled"
            if payload.get("status") == "cancelled"
            else "paid"
            if paid == expected
            else "partial"
            if paid
            else "expected"
        )
        stored["updated_at"] = _iso(_now(session))
        session.revision += 1
        return stored

    if (
        method == "PATCH"
        and len(parts) == 4
        and parts[:2] == ["coach", "tasks"]
        and parts[2].isdigit()
        and parts[3] == "state"
    ):
        task_id = int(parts[2])
        stored = next(
            (item for item in _crm_state(session)["tasks"] if int(item["id"]) == task_id), None
        )
        if stored is None:
            raise DemoActionForbiddenError
        payload = _request_body(body)
        if payload.get("state") not in {"open", "completed"}:
            raise DemoActionForbiddenError
        stored["state"] = payload["state"]
        stored["completed_at"] = _iso(_now(session)) if payload["state"] == "completed" else None
        stored["updated_at"] = _iso(_now(session))
        session.revision += 1
        return stored

    if (
        method == "PATCH"
        and len(parts) == 4
        and parts[:2] == ["coach", "clients"]
        and parts[2].isdigit()
        and parts[3] == "operational-status"
    ):
        client_id = int(parts[2])
        slug = _client_slug(client_id)
        payload = _request_body(body)
        if payload.get("operational_status") not in {"active", "paused", "archived"}:
            raise DemoActionForbiddenError
        session.state.setdefault("crm_operational_status", {})[slug] = payload["operational_status"]
        session.revision += 1
        return {"operational_status": payload["operational_status"]}

    if (
        method in {"PATCH", "DELETE"}
        and len(parts) == 4
        and parts[:3] == ["nutrition", "hydration", "entries"]
        and parts[3].isdigit()
    ):
        entry_id = int(parts[3])
        entries = session.state.setdefault("hydration_entries", [])
        stored = next((item for item in entries if int(item["id"]) == entry_id), None)
        if stored is None:
            raise DemoActionForbiddenError
        if method == "PATCH":
            return _update_hydration_entry(session, entry_id, _request_body(body))
        entries.remove(stored)
        session.revision += 1
        return None

    if (
        method == "DELETE"
        and len(parts) == 4
        and parts[:3] == ["nutrition", "hydration", "presets"]
        and parts[3].isdigit()
    ):
        preset_id = int(parts[3])
        presets = session.state.setdefault("hydration_presets", [])
        stored = next((item for item in presets if int(item["id"]) == preset_id), None)
        if stored is None:
            raise DemoActionForbiddenError
        presets.remove(stored)
        session.revision += 1
        return None

    raise DemoActionForbiddenError
