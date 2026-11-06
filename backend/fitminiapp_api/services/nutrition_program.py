from datetime import date, timedelta
from typing import Literal, cast

from sqlalchemy.orm import Session

from fitminiapp_api.models.program import ProgramRevision, UserProgram
from fitminiapp_api.services.program_versioning import (
    _cycle_occurrence_overrides,
    _cycle_plan_at,
    _cycle_type_for_date,
)
from fitminiapp_api.services.schedule_modes import calendar_active_on

DayType = Literal["training", "rest"]
WeekType = Literal["light", "medium", "heavy"]


def program_nutrition_day(
    db: Session,
    program: UserProgram,
    revisions: list[ProgramRevision],
    revision_number: int,
    day: date,
) -> tuple[DayType | None, WeekType | None]:
    """Read the planned calendar at an exact program revision without materializing workouts."""
    available = sorted(
        (
            item
            for item in revisions
            if item.user_program_id == program.id and item.revision_number <= revision_number
        ),
        key=lambda item: item.revision_number,
    )
    if not available or available[-1].revision_number != revision_number:
        return None, None
    try:
        snapshot = available[-1].snapshot
        details = snapshot["program"]
        if details.get("id") != program.id or details.get("status") in {
            "paused",
            "completed",
            "terminated",
            "archived",
        }:
            return None, None
        start = date.fromisoformat(details["start_date"])
        week = (day - start).days // 7 + 1
        if not 1 <= week <= details["duration_weeks"]:
            return None, None

        changes: list[tuple[date, str]] = []
        for revision in available:
            fields = revision.changed_fields
            if fields.get("operation") == "session_rotation_mode":
                effective = date.fromisoformat(fields["rotation_effective_date"])
                changes = [change for change in changes if change[0] < effective]
                changes.append((effective, fields["mode"]))
        if (not changes and details.get("schedule_mode") == "rotation") or not calendar_active_on(
            changes, day
        ):
            return None, None

        config = _cycle_plan_at(db, program, week, revisions=available)
        if config is None:
            workouts = snapshot["workouts"]
            if not workouts:
                return None, None
            planned = any(
                item["scheduled_date"] == day.isoformat() and item.get("rotation_epoch") is None
                for item in workouts
            )
            return ("training" if planned else "rest"), None

        cycle, source, boundary = config
        length = cycle["length_weeks"]
        repeat = cycle["repeat"]
        if (
            cycle.get("schema_version") != 1
            or type(length) is not int
            or length < 1
            or type(repeat) is not bool
            or week < boundary
            or (not repeat and week - boundary >= length)
        ):
            return None, None
        source_week = (week - boundary) % length + 1
        types = cycle.get("week_types")
        if types is not None and (
            not isinstance(types, list)
            or len(types) != length
            or any(item is not None and item not in {"light", "medium", "heavy"} for item in types)
        ):
            return None, None
        week_type = _cycle_type_for_date(
            cycle,
            _cycle_occurrence_overrides(db, program.id, revisions=available),
            week,
            source_week,
            boundary,
            day,
        )
        if week_type not in {None, "light", "medium", "heavy"}:
            return None, None
        pinned_dates = {
            item["day_number"]: date.fromisoformat(item["scheduled_date"])
            for item in snapshot["workouts"]
            if item.get("week_number") == week and item.get("rotation_epoch") is None
        }
        planned = any(
            pinned_dates.get(
                item["day_number"],
                date.fromisoformat(item["scheduled_date"]) + timedelta(weeks=week - source_week),
            )
            == day
            for item in source
            if item["week_number"] == source_week
        )
        return ("training" if planned else "rest"), cast(WeekType | None, week_type)
    except AttributeError, KeyError, OverflowError, TypeError, ValueError, ZeroDivisionError:
        return None, None
