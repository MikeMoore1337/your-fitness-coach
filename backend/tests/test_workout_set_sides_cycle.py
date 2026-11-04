from datetime import timedelta

from test_program_cycle_domain import TODAY, assigned_cycle, schedule
from test_program_cycle_domain import fixed_calendar as fixed_calendar

from fitminiapp_api.api.v1 import workouts as workout_routes
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserWorkout, UserWorkoutSet


def test_cycle_repeats_without_rewriting_side_facts(client, monkeypatch):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16)
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    original = started.json()["exercises"][0]["sets"][0]
    saved = client.patch(
        f"/api/v1/workouts/sets/{original['id']}",
        headers=headers,
        json={
            "execution_mode": "per_side",
            "sides": {
                "left": {"actual_reps": 10, "actual_weight": 18, "is_completed": True},
                "right": {"actual_reps": 8, "actual_weight": 16, "is_completed": True},
            },
            "is_completed": "sides-v1",
            "side_is_completed": True,
            "expected_version": original["version"],
            "mutation_id": "cycle-sides-832-0001",
        },
    )
    assert saved.status_code == 200, saved.text
    finished = client.post(
        f"/api/v1/workouts/{workout['id']}/finish",
        headers=headers,
        json={"confirm_incomplete": True},
    )
    assert finished.status_code == 200, finished.text
    for week in (4, 16):
        day = TODAY + timedelta(weeks=week - 1)
        rows = schedule(client, headers, day, 1)
        assert len(rows) == 1
        assert rows[0]["week_number"] == week
        monkeypatch.setattr(workout_routes, "recovery_today_for_user", lambda _user, day=day: day)
        repeated = client.get("/api/v1/workouts/today", headers=headers)
        assert repeated.status_code == 200, repeated.text
        assert (
            repeated.json()["week_number"],
            repeated.json()["source_cycle_week"],
            repeated.json()["cycle_iteration"],
        ) == (
            week,
            1,
            (week - 1) // 3 + 1,
        )
    with get_session_context() as db:
        recorded = db.get(UserWorkoutSet, original["id"])
        assert recorded.version == saved.json()["version"]
        assert recorded.execution_mode == "per_side"
        assert {
            side.side: (side.actual_weight, side.actual_reps) for side in recorded.side_results
        } == {
            "left": (18, 10),
            "right": (16, 8),
        }
        assert db.get(UserWorkout, workout["id"]).user_program_id == program_id
