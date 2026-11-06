from datetime import date, timedelta
from unittest.mock import Mock

import pytest
from test_program_week_cycle import _auth, _payload

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import ProgramRevision, UserProgram, UserWorkout
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services.nutrition_program import program_nutrition_day
from fitminiapp_api.services.program_versioning import _cycle_workout_plans


def _cycle_revisions(length: int) -> tuple[UserProgram, list[ProgramRevision]]:
    start = date(2026, 1, 5)
    week_types = ["light", "medium", "heavy"]
    cycle = {
        "schema_version": 1,
        "length_weeks": length,
        "repeat": True,
        "week_types": [week_types[index % 3] for index in range(length)],
    }
    source = [
        {
            "week_number": week,
            "day_number": 1,
            "scheduled_date": (start + timedelta(weeks=week - 1)).isoformat(),
            "exercises": [],
        }
        for week in range(1, length + 1)
    ]
    program = UserProgram(id=1, user_id=1, start_date=start, duration_weeks=200)
    revision = ProgramRevision(
        user_program_id=1,
        revision_number=1,
        change_kind="assigned",
        changed_fields={"week_cycle": cycle, "logical_cycle": source},
        snapshot={
            "program": {
                "id": 1,
                "start_date": start.isoformat(),
                "duration_weeks": 200,
                "schedule_mode": "calendar",
            },
            "workouts": [],
        },
    )
    return program, [revision]


@pytest.mark.parametrize("length", [1, 3, 5, 10, 12, 14])
def test_cycle_projection_uses_calendar_plan_and_repeats_without_materializing(length: int) -> None:
    program, revisions = _cycle_revisions(length)
    db = Mock()
    week = 99
    day = program.start_date + timedelta(weeks=week - 1)
    expected_type = ["light", "medium", "heavy"][((week - 1) % length) % 3]
    assert program_nutrition_day(db, program, revisions, 1, day) == ("training", expected_type)
    assert program_nutrition_day(db, program, revisions, 1, day + timedelta(days=1)) == (
        "rest",
        expected_type,
    )
    assert db.mock_calls == []


def test_projection_pins_revision_and_applies_future_cycle_change() -> None:
    program, revisions = _cycle_revisions(3)
    start = program.start_date
    changed_cycle = {
        "schema_version": 1,
        "length_weeks": 1,
        "repeat": True,
        "week_types": ["heavy"],
    }
    changed_source = [
        {
            "week_number": 1,
            "day_number": 1,
            "scheduled_date": (start + timedelta(days=2)).isoformat(),
            "exercises": [],
        }
    ]
    revisions.append(
        ProgramRevision(
            user_program_id=1,
            revision_number=2,
            change_kind="plan_updated",
            changed_fields={
                "cycle_configuration": {
                    "effective_from_week": 5,
                    "week_cycle": changed_cycle,
                    "logical_cycle": changed_source,
                }
            },
            snapshot=revisions[0].snapshot,
        )
    )
    monday = start + timedelta(weeks=5)
    assert program_nutrition_day(Mock(), program, revisions, 1, monday) == ("training", "heavy")
    assert program_nutrition_day(Mock(), program, revisions, 2, monday) == ("rest", "heavy")
    assert program_nutrition_day(Mock(), program, revisions, 2, monday + timedelta(days=2)) == (
        "training",
        "heavy",
    )
    assert program_nutrition_day(Mock(), program, revisions, 2, start) == ("training", "light")


def test_projection_does_not_guess_for_rotation_or_outside_program() -> None:
    program, revisions = _cycle_revisions(3)
    revisions.append(
        ProgramRevision(
            user_program_id=1,
            revision_number=2,
            change_kind="plan_updated",
            changed_fields={
                "operation": "session_rotation_mode",
                "rotation_effective_date": "2026-01-12",
                "mode": "rotation",
            },
            snapshot=revisions[0].snapshot,
        )
    )
    assert program_nutrition_day(Mock(), program, revisions, 2, date(2026, 1, 12)) == (None, None)
    assert program_nutrition_day(Mock(), program, revisions, 1, date(2026, 1, 4)) == (None, None)


def test_projection_uses_real_program_revisions_without_creating_workouts(client) -> None:
    headers = _auth(client, 952200)
    payload = _payload(client, headers)
    payload["week_cycle"] = {
        "length_weeks": 3,
        "repeat": True,
        "week_types": ["light", "medium", "heavy"],
    }
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 50},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        selected = date.fromisoformat(_cycle_workout_plans(db, program, 5)[0]["scheduled_date"])

    changed = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_from_week": 5,
            "source_week_order": [3, 2, 1],
            "repeat": True,
        },
    )
    assert changed.status_code == 200, changed.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
        before = db.query(UserWorkout).filter_by(user_program_id=program_id).count()
        assert program_nutrition_day(db, program, revisions, 1, selected) == ("training", "medium")
        assert program_nutrition_day(db, program, revisions, 2, selected) == ("training", "heavy")
        assert db.query(UserWorkout).filter_by(user_program_id=program_id).count() == before
    for revision_number, week_type in [(1, "medium"), (2, "heavy")]:
        response = client.get(
            "/api/v1/nutrition/targets/program-day",
            headers=headers,
            params={
                "program_id": program_id,
                "revision_number": revision_number,
                "target_date": selected.isoformat(),
            },
        )
        assert response.status_code == 200, response.text
        assert (response.json()["day_type"], response.json()["week_type"]) == (
            "training",
            week_type,
        )
    other = _auth(client, 952201)
    denied = client.get(
        "/api/v1/nutrition/targets/program-day",
        headers=other,
        params={
            "program_id": program_id,
            "revision_number": 1,
            "target_date": selected.isoformat(),
        },
    )
    assert denied.status_code == 404
    coach = _auth(client, 952202, is_coach=True)
    with get_session_context() as db:
        owner_id = db.query(User.id).filter_by(telegram_user_id=952200).scalar()
        coach_id = db.query(User.id).filter_by(telegram_user_id=952202).scalar()
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=owner_id, status="active"))
    params = {
        "program_id": program_id,
        "revision_number": 1,
        "target_date": selected.isoformat(),
        "target_telegram_user_id": 952200,
    }
    assert (
        client.get(
            "/api/v1/nutrition/targets/program-day", headers=coach, params=params
        ).status_code
        == 200
    )
    with get_session_context() as db:
        db.query(CoachClient).filter_by(
            coach_user_id=coach_id, client_user_id=owner_id
        ).one().status = "ended"
    assert (
        client.get(
            "/api/v1/nutrition/targets/program-day", headers=coach, params=params
        ).status_code
        == 403
    )
