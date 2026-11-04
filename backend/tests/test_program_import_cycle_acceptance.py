"""Exercise the canonical XLSX import through template assignment and future cycle projection."""

from __future__ import annotations

import pytest
from test_program_import import _auth, _upload, _weekly_matrix_xlsx

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserProgram, UserWorkout
from fitminiapp_api.models.user import User
from fitminiapp_api.services.program_versioning import _cycle_workout_plans


def _prescription_signature(plans: list[dict]) -> list[tuple]:
    return [
        (
            plan["day_number"],
            tuple(
                (
                    exercise["exercise_id"],
                    exercise["prescribed_sets"],
                    exercise["prescribed_reps"],
                    exercise["prescription"],
                )
                for exercise in plan["exercises"]
            ),
        )
        for plan in sorted(plans, key=lambda item: item["day_number"])
    ]


@pytest.mark.parametrize(
    ("k", "n", "repeat", "types"),
    [
        (1, 16, True, None),
        (3, 16, True, ["light", None, "heavy"]),
        (3, 2, False, None),
    ],
)
def test_xlsx_confirm_then_assign_preserves_source_weeks_and_real_workout_facts(
    client, k: int, n: int, repeat: bool, types: list[str | None] | None
):
    uid = 931_300 + k * 100 + n
    headers = _auth(client, uid)
    upload = _upload(
        client,
        headers,
        "cycle.xlsx",
        _weekly_matrix_xlsx(weeks=k),
    )
    assert upload.status_code == 201, upload.text
    draft = upload.json()
    assert draft["duration_weeks"] == k
    assert draft["week_types"] == [None] * k

    row_resolutions = []
    if k == 1:
        weighted_row = next(row for row in draft["rows"] if row["source_auxiliary"])
        row_resolutions.append({"row_number": weighted_row["row_number"], "planned_loads": "32.5"})
    resolved = client.post(
        f"/api/v1/programs/imports/{draft['id']}/resolve",
        headers=headers,
        json={
            "expected_draft_version": draft["draft_version"],
            "title": f"План {k}/{n}",
            "goal": "maintenance",
            "level": "intermediate",
            "assignment_duration_weeks": n,
            "repeat": repeat,
            "week_types": types if types is not None else [None] * k,
            "rows": row_resolutions,
        },
    )
    assert resolved.status_code == 200, resolved.text
    ready = resolved.json()
    assert ready["summary"]["blocking_issue_count"] == 0

    confirmed = client.post(
        f"/api/v1/programs/imports/{draft['id']}/confirm",
        headers=headers,
        json={"expected_draft_version": ready["draft_version"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    template = confirmed.json()["template"]
    assert template["default_duration_weeks"] == n
    assert template["program_metadata"]["week_cycle"] == {
        "schema_version": 1,
        "length_weeks": k,
        "week_types": types,
        "repeat": repeat,
    }

    with get_session_context() as db:
        owner = db.query(User).filter_by(telegram_user_id=uid).one()
        assert db.query(UserProgram).filter_by(user_id=owner.id).count() == 0

    assigned = client.post(
        f"/api/v1/programs/templates/{template['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": n},
    )
    assert assigned.status_code == 200, assigned.text
    assigned_id = assigned.json()["user_program_id"]

    with get_session_context() as db:
        program = db.get(UserProgram, assigned_id)
        assert program is not None and program.duration_weeks == n
        source_signatures = {
            week: _prescription_signature(_cycle_workout_plans(db, program, week))
            for week in range(1, k + 1)
        }
        sampled_weeks = sorted({1, n, min(n, 2), min(n, 3), min(n, 4)})
        for week in sampled_weeks:
            plans = _cycle_workout_plans(db, program, week)
            assert len(plans) == 4
            source_week = ((week - 1) % k) + 1
            assert {item["source_cycle_week"] for item in plans} == {source_week}
            assert {item["cycle_iteration"] for item in plans} == {((week - 1) // k) + 1}
            assert _prescription_signature(plans) == source_signatures[source_week]
        if k == 1:
            assert any(
                segment["load_target"] == {"kind": "absolute", "value": 32.5}
                for plan in _cycle_workout_plans(db, program, n)
                for exercise in plan["exercises"]
                for segment in exercise["prescription"]["segments"]
            )
        actual = db.query(UserWorkout).filter_by(user_program_id=assigned_id).all()
        assert all(item.status != "completed" for item in actual)
        assert not any(
            item.is_completed
            for workout in actual
            for exercise in workout.exercises
            for item in exercise.sets
        )
