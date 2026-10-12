from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.core.timezone import (
    get_user_timezone_name,
    now_in_timezone,
    to_user_timezone_naive,
)
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.program import UserProgram
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.progress import NutritionReportPeriod, ProgressReportResponse
from fitminiapp_api.services.analytics import build_training_analytics_for_range
from fitminiapp_api.services.daily_wellbeing import build_daily_wellbeing_report
from fitminiapp_api.services.nutrition_reports import build_nutrition_report, resolve_report_bounds
from fitminiapp_api.services.progress import build_progress_summary_for_range

EXERCISE_HISTORY_LIMIT = 20


def _subject_name(user: User) -> str:
    if user.profile and user.profile.full_name:
        return user.profile.full_name
    return user.first_name or user.username or "Пользователь"


def _program_context(
    db: Session,
    user: User,
    *,
    period_start: date,
    period_end: date,
) -> dict | None:
    program = (
        db.query(UserProgram)
        .options(
            joinedload(UserProgram.template),
            joinedload(UserProgram.training_blocks),
            joinedload(UserProgram.revisions),
        )
        .filter(UserProgram.user_id == user.id, UserProgram.is_active.is_(True))
        .order_by(UserProgram.start_date.desc(), UserProgram.id.desc())
        .first()
    )
    if program is None:
        return None

    active_block = next(
        (block for block in program.training_blocks if block.status == "active"),
        None,
    )
    changes = []
    for revision in program.revisions:
        changed_on = to_user_timezone_naive(revision.created_at, user).date()
        if period_start <= changed_on <= period_end:
            changes.append(
                {
                    "changed_on": changed_on,
                    "change_kind": revision.change_kind,
                }
            )

    return {
        "title": program.template.title if program.template else "Текущая программа",
        "status": program.status,
        "start_date": program.start_date,
        "duration_weeks": program.duration_weeks,
        "active_block": (
            {
                "title": active_block.title,
                "start_date": active_block.start_date,
                "end_date": active_block.end_date,
                "purpose": active_block.purpose,
                "is_deload": active_block.is_deload,
                "status": active_block.status,
            }
            if active_block
            else None
        ),
        "changes": sorted(changes, key=lambda item: item["changed_on"]),
    }


def _check_ins(
    db: Session,
    user: User,
    *,
    period_start: date,
    period_end: date,
) -> list[dict]:
    rows = (
        db.query(WeeklyCheckIn)
        .filter(
            WeeklyCheckIn.user_id == user.id,
            WeeklyCheckIn.submitted_on.between(period_start, period_end),
        )
        .order_by(WeeklyCheckIn.submitted_on.desc(), WeeklyCheckIn.id.desc())
        .all()
    )
    return [
        {
            "week_start": row.week_start,
            "week_end": row.week_end,
            "submitted_on": row.submitted_on,
            "status": row.status,
            "training_load": row.training_load,
            "recovery": row.recovery,
            "hunger": row.hunger,
            "adherence_difficulty": row.adherence_difficulty,
        }
        for row in rows
    ]


def build_progress_report(
    db: Session,
    user: User,
    period: NutritionReportPeriod,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    subject_role: str = "self",
) -> dict:
    bounds = resolve_report_bounds(user, period, date_from=date_from, date_to=date_to)
    summary = build_progress_summary_for_range(db, user, bounds.start, bounds.end)
    analytics = build_training_analytics_for_range(
        db,
        user,
        bounds.start,
        bounds.end,
        exercise_history_limit=EXERCISE_HISTORY_LIMIT,
    )
    nutrition = build_nutrition_report(
        db,
        user,
        period,
        date_from=date_from,
        date_to=date_to,
    )
    exercises = [
        {
            "exercise_title": exercise["exercise_title"],
            "performed_session_count": exercise["performed_session_count"],
            "completed_set_count": exercise["completed_set_count"],
            "first_performed_on": exercise["first_performed_on"],
            "last_performed_on": exercise["last_performed_on"],
            "reps_total": exercise["reps_total"],
            "max_external_load_kg": exercise["max_external_load_kg"],
            "external_load_volume_kg": exercise["external_load_volume_kg"],
            "volume_recorded_sets": exercise["volume_recorded_sets"],
            "sessions": [
                {
                    "performed_on": session["performed_on"],
                    "completed_set_count": session["completed_set_count"],
                    "max_external_load_kg": session["max_external_load_kg"],
                    "external_load_volume_kg": session["external_load_volume_kg"],
                }
                for session in exercise["sessions"]
            ],
        }
        for exercise in analytics["exercises"]
    ]
    payload = {
        "generated_at": now_in_timezone(get_user_timezone_name(user)),
        "period": period,
        "period_start": bounds.start,
        "period_end": bounds.end,
        "timezone": get_user_timezone_name(user),
        "subject": {
            "name": _subject_name(user),
            "role": subject_role,
            "goal": user.profile.goal if user.profile else None,
        },
        "training": {
            "planned_workouts": summary["training"]["planned_workouts"],
            "completed_workouts": summary["training"]["completed_workouts"],
            "skipped_workouts": summary["training"]["skipped_workouts"],
            "frequency_per_week": summary["training"]["frequency_per_week"],
            "completed_working_sets": analytics["completed_set_count"],
            "external_load_volume_kg": analytics["external_load_volume_kg"],
            "volume_recorded_sets": analytics["volume_recorded_sets"],
            "new_personal_records": summary["training"]["new_personal_records"],
            "exercises": exercises,
        },
        "cardio": summary["cardio"],
        "body": summary["body"],
        "nutrition": nutrition,
        "adherence": summary["adherence"],
        "data_sufficiency": summary["data_sufficiency"],
        "program": _program_context(
            db,
            user,
            period_start=bounds.start,
            period_end=bounds.end,
        ),
        "check_ins": _check_ins(
            db,
            user,
            period_start=bounds.start,
            period_end=bounds.end,
        ),
        "wellbeing": build_daily_wellbeing_report(
            db,
            user,
            period_start=bounds.start,
            period_end=bounds.end,
        ),
    }
    return ProgressReportResponse.model_validate(payload).model_dump(mode="json")
