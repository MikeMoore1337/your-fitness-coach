from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from fitminiapp_api.models.program import ProgramRevision


def mode_changes(db: Session, program_ids: set[int]) -> dict[int, list[tuple[date, str]]]:
    changes: dict[int, list[tuple[date, str]]] = defaultdict(list)
    if not program_ids:
        return changes
    revisions = (
        db.query(ProgramRevision.user_program_id, ProgramRevision.changed_fields)
        .filter(
            ProgramRevision.user_program_id.in_(program_ids),
            ProgramRevision.change_kind == "plan_updated",
        )
        .order_by(ProgramRevision.user_program_id, ProgramRevision.revision_number)
    )
    for revision in revisions:
        fields = revision.changed_fields
        if fields.get("operation") != "session_rotation_mode":
            continue
        effective = date.fromisoformat(fields["rotation_effective_date"])
        changes[revision.user_program_id] = [
            change for change in changes[revision.user_program_id] if change[0] < effective
        ]
        changes[revision.user_program_id].append((effective, fields["mode"]))
    return changes


def calendar_segments(
    changes: list[tuple[date, str]], start: date, end: date
) -> list[tuple[date, date]]:
    if end < start:
        return []
    mode = "calendar"
    cursor = start
    result = []
    for effective, next_mode in changes:
        if effective <= start:
            mode = next_mode
        elif effective <= end:
            if mode == "calendar" and cursor < effective:
                result.append((cursor, effective - timedelta(days=1)))
            cursor = effective
            mode = next_mode
    if mode == "calendar" and cursor <= end:
        result.append((cursor, end))
    return result


def calendar_active_on(changes: list[tuple[date, str]], day: date) -> bool:
    mode = "calendar"
    for effective, next_mode in changes:
        if effective <= day:
            mode = next_mode
    return mode == "calendar"
