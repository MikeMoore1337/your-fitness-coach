from __future__ import annotations

from datetime import timedelta

from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _add_session(
    db,
    program: UserProgram,
    exercise_id: int,
    *,
    days_ago: int,
    sets: list[dict],
    metric_type: str | None = None,
) -> UserWorkout:
    workout = UserWorkout(
        user_program_id=program.id,
        scheduled_date=today_msk() - timedelta(days=days_ago),
        day_number=1,
        week_number=1,
        title=f"История {days_ago}",
        status="completed",
        completed_at=now_msk_naive(),
    )
    db.add(workout)
    db.flush()
    workout_exercise = UserWorkoutExercise(
        workout_id=workout.id,
        exercise_id=exercise_id,
        metric_type=metric_type,
        sort_order=1,
        prescribed_sets=len(sets),
        prescribed_reps="6-10",
        rest_seconds=90,
    )
    db.add(workout_exercise)
    db.flush()
    db.add_all(
        [
            UserWorkoutSet(
                workout_exercise_id=workout_exercise.id,
                set_number=index,
                actual_reps=item.get("reps"),
                actual_weight=item.get("weight"),
                set_kind=item.get("set_kind", "working"),
                planned_role=item.get("planned_role"),
                is_completed=True,
            )
            for index, item in enumerate(sets, start=1)
        ]
    )
    return workout


def test_exercise_history_keeps_canonical_facts_and_progression_trace(client) -> None:
    headers = _auth(client, 81_201)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]

    with get_session_context() as db:
        bench = db.query(Exercise).filter(Exercise.slug == "bench-press").one()
        push_up = db.query(Exercise).filter(Exercise.slug == "push-up").one()
        program = UserProgram(
            user_id=user_id,
            start_date=today_msk() - timedelta(days=120),
            duration_weeks=30,
            schedule_weekdays=[0],
            status="active",
            is_active=True,
        )
        db.add(program)
        db.flush()
        bench_id = bench.id
        recent = _add_session(
            db,
            program,
            bench.id,
            days_ago=2,
            sets=[
                {"reps": 12, "weight": 150, "planned_role": "warmup"},
                {"reps": 8, "weight": 80},
                {"reps": 8, "weight": 200, "planned_role": "drop"},
            ],
        )
        recent_id = recent.id
        _add_session(
            db,
            program,
            bench.id,
            days_ago=10,
            sets=[{"reps": 5, "weight": 70}],
        )
        _add_session(
            db,
            program,
            bench.id,
            days_ago=1,
            metric_type="cardio",
            sets=[{"reps": 40, "weight": 400}],
        )
        _add_session(
            db,
            program,
            push_up.id,
            days_ago=1,
            sets=[{"reps": 30, "weight": 300}],
        )
        db.add(
            AuditEvent(
                actor_user_id=user_id,
                target_user_id=user_id,
                action="progression_proposal.confirm",
                resource_type="user_workout",
                resource_id=str(recent_id),
                details={
                    "proposal_id": "a" * 64,
                    "exercise_id": bench_id,
                    "target_workout_id": recent_id,
                    "rule_id": "b" * 64,
                    "rule_kind": "double_progression",
                    "rule_snapshot": {"increment_unit": "kg"},
                    "source_evidence_ids": [f"workout:{recent_id}/set:2"],
                    "reason_codes": ["top_range_repeated"],
                    "proposed_weight": 82.5,
                    "adjusted_weight": None,
                    "result": {
                        "proposal_id": "a" * 64,
                        "decision": "confirm",
                        "applied_set_ids": [],
                        "current_revision_number": 1,
                    },
                },
            )
        )

    response = client.get(
        f"/api/v1/programs/exercises/{bench_id}/history",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["exercise_id"] == bench_id
    assert payload["last_performed"]["workout_id"] == recent_id
    assert payload["best_authoritative_load"]["value_kg"] == 80.0
    assert payload["estimated_1rm"] == {
        "kind": "estimated",
        "formula": "brzycki",
        "value_kg": 99.5,
        "workout": payload["last_performed"],
        "reps": 8,
        "load_kg": 80.0,
    }
    rep_prs = {item["range_key"]: item for item in payload["rep_prs"]}
    assert rep_prs["6-10"]["best_load_kg"] == 80.0
    assert rep_prs["1-5"]["best_load_kg"] == 70.0
    windows = {item["days"]: item for item in payload["windows"]}
    assert windows[7]["performed_session_count"] == 1
    assert windows[30]["performed_session_count"] == 2
    assert windows[90]["performed_session_count"] == 2
    assert len(payload["recent_sessions"]) == 2
    assert [item["set_number"] for item in payload["recent_sessions"][0]["sets"]] == [2, 3]
    assert payload["recent_sessions"][0]["sets"][1]["pr_eligible"] is False
    assert payload["progression_events"][0]["event_kind"] == "confirm"
    assert payload["progression_events"][0]["source_evidence_ids"] == [f"workout:{recent_id}/set:2"]


def test_exercise_history_does_not_expose_another_users_exercise(client) -> None:
    owner_headers = _auth(client, 81_202)
    owner_id = client.get("/api/v1/me", headers=owner_headers).json()["id"]
    viewer_headers = _auth(client, 81_203)
    with get_session_context() as db:
        custom = Exercise(
            slug="private-history-exercise",
            title="Личное упражнение",
            metric_type="strength",
            difficulty_level="beginner",
            created_by_user_id=owner_id,
            is_deleted=False,
        )
        db.add(custom)
        db.flush()
        custom_id = custom.id

    response = client.get(
        f"/api/v1/programs/exercises/{custom_id}/history",
        headers=viewer_headers,
    )

    assert response.status_code == 404
