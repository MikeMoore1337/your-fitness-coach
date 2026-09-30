from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import joinedload

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.performance import (
    begin_sql_metrics,
    current_sql_metrics,
    reset_sql_metrics,
)
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services.analytics import build_training_analytics


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_id(telegram_user_id: int) -> int:
    with get_session_context() as db:
        return db.query(User.id).filter(User.telegram_user_id == telegram_user_id).scalar()


def _program(db, user_id: int) -> UserProgram:
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
    return program


def _add_exercise_session(
    db,
    program: UserProgram,
    exercise_id: int,
    *,
    days_ago: int,
    sets: list[tuple[int | None, float | None, str | None, bool]],
    status: str = "completed",
) -> UserWorkout:
    workout = UserWorkout(
        user_program_id=program.id,
        scheduled_date=today_msk() - timedelta(days=days_ago),
        day_number=1,
        week_number=1,
        title="Аналитическая тренировка",
        status=status,
    )
    db.add(workout)
    db.flush()
    workout_exercise = UserWorkoutExercise(
        workout_id=workout.id,
        exercise_id=exercise_id,
        sort_order=1,
        prescribed_sets=len(sets),
        prescribed_reps="8-12",
        rest_seconds=60,
    )
    db.add(workout_exercise)
    db.flush()
    db.add_all(
        [
            UserWorkoutSet(
                workout_exercise_id=workout_exercise.id,
                set_number=index,
                actual_reps=reps,
                actual_weight=weight,
                rir=rir,
                is_completed=is_completed,
            )
            for index, (reps, weight, rir, is_completed) in enumerate(sets, start=1)
        ]
    )
    return workout


def test_training_analytics_reports_factual_progression_rir_and_muscle_exposure(client) -> None:
    headers = _auth(client, 27_001)
    user_id = _user_id(27_001)
    today = today_msk()

    with get_session_context() as db:
        bench = db.query(Exercise).filter(Exercise.slug == "bench-press").one()
        push_up = db.query(Exercise).filter(Exercise.slug == "push-up").one()
        bench_id = bench.id
        push_up_id = push_up.id
        program = _program(db, user_id)
        _add_exercise_session(
            db,
            program,
            bench.id,
            days_ago=1,
            sets=[
                (8, 20, "2", True),
                (10, 22.5, None, True),
                (5, None, "4+", True),
                (12, 30, "0", False),
            ],
        )
        _add_exercise_session(
            db,
            program,
            bench.id,
            days_ago=5,
            sets=[(12, 15, "3", True)],
        )
        _add_exercise_session(
            db,
            program,
            bench.id,
            days_ago=10,
            sets=[(6, 25, "1", True)],
        )
        _add_exercise_session(
            db,
            program,
            bench.id,
            days_ago=31,
            sets=[(5, 30, "0", True)],
        )
        _add_exercise_session(
            db,
            program,
            push_up.id,
            days_ago=2,
            sets=[(12, None, "0", True)],
        )
        _add_exercise_session(
            db,
            program,
            bench.id,
            days_ago=3,
            sets=[(20, 100, "0", True)],
            status="skipped",
        )

    response = client.get(
        "/api/v1/workouts/progress/training-analytics",
        headers=headers,
        params={"period_days": 7, "exercise_history_limit": 1},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["period_days"] == 7
    assert payload["period_start"] == (today - timedelta(days=6)).isoformat()
    assert payload["period_end"] == today.isoformat()
    assert payload["previous_period_start"] == (today - timedelta(days=13)).isoformat()
    assert payload["previous_period_end"] == (today - timedelta(days=7)).isoformat()
    assert payload["completed_set_count"] == 5
    assert payload["completed_workout_count"] == 3
    assert payload["frequency_per_week"] == 3.0
    assert payload["previous_completed_workout_count"] == 1
    assert payload["previous_frequency_per_week"] == 1.0
    assert payload["reps_total"] == 47
    assert payload["reps_recorded_sets"] == 5
    assert payload["external_load_volume_kg"] == 565.0
    assert payload["volume_recorded_sets"] == 3

    exercises = {item["exercise_id"]: item for item in payload["exercises"]}
    bench_progress = exercises[bench_id]
    assert bench_progress["performed_session_count"] == 2
    assert bench_progress["completed_set_count"] == 4
    assert bench_progress["max_external_load_kg"] == 22.5
    assert bench_progress["best_set_volume_kg"] == 225.0
    assert bench_progress["external_load_volume_kg"] == 565.0
    assert bench_progress["history_truncated"] is True
    assert len(bench_progress["sessions"]) == 1
    latest = bench_progress["sessions"][0]
    assert latest["performed_on"] == (today - timedelta(days=1)).isoformat()
    assert latest["completed_set_count"] == 3
    assert latest["reps_total"] == 23
    assert latest["external_load_volume_kg"] == 385.0
    assert latest["volume_recorded_sets"] == 2
    assert latest["sets"][2] == {
        "set_number": 3,
        "reps": 5,
        "external_load_kg": None,
        "external_load_volume_kg": None,
        "rir": "4+",
        "set_kind": "working",
        "reached_failure": None,
    }

    bodyweight = exercises[push_up_id]
    assert bodyweight["uses_bodyweight_equipment"] is True
    assert bodyweight["external_load_volume_kg"] is None
    assert bodyweight["volume_recorded_sets"] == 0

    rir = payload["rir"]
    assert rir["recorded_set_count"] == 4
    assert rir["missing_set_count"] == 1
    assert {item["value"]: item["completed_set_count"] for item in rir["distribution"]} == {
        "0": 1,
        "1": 0,
        "2": 1,
        "3": 1,
        "4+": 1,
    }
    primary = {
        item["muscle_id"]: item["completed_set_count"]
        for item in payload["primary_muscle_exposure"]
    }
    secondary = {
        item["muscle_id"]: item["completed_set_count"]
        for item in payload["secondary_muscle_exposure"]
    }
    assert primary["chest"] == 5
    assert secondary["triceps"] == 5
    assert payload["completed_sets_without_muscle_metadata"] == 0
    workload = {item["muscle_id"]: item for item in payload["muscle_group_workload"]}
    assert workload["chest"]["current"] == {
        "completed_set_count": 5,
        "primary_completed_set_count": 5,
        "secondary_completed_set_count": 0,
        "completed_session_count": 3,
        "frequency_per_week": 3.0,
    }
    assert workload["chest"]["previous"] == {
        "completed_set_count": 1,
        "primary_completed_set_count": 1,
        "secondary_completed_set_count": 0,
        "completed_session_count": 1,
        "frequency_per_week": 1.0,
    }
    assert workload["chest"]["completed_set_count_change"] == 4
    assert workload["chest"]["trend"] == "increased"
    assert workload["triceps"]["previous"]["completed_set_count"] == 1
    assert workload["triceps"]["trend"] == "increased"
    assert workload["chest"]["contributing_exercises"][0]["exercise_id"] == bench_id
    assert workload["chest"]["contributing_exercises"][0]["performed_session_count"] == 2
    sufficiency = payload["data_sufficiency"]
    assert sufficiency["ruleset_version"] == "data-sufficiency-v1"
    assert sufficiency["workout_logging"]["status"] == "limited"
    assert sufficiency["workout_logging"]["counters"] == {
        "completed_workout_count": 3,
        "prescribed_set_count": 6,
        "logged_set_count": 5,
        "coverage_percent": 83.3,
    }
    assert sufficiency["working_sets"]["status"] == "limited"
    assert sufficiency["rir_coverage"]["status"] == "sufficient"

    days_30 = client.get(
        "/api/v1/workouts/progress/training-analytics?period_days=30",
        headers=headers,
    ).json()
    assert days_30["completed_set_count"] == 6
    assert days_30["period_start"] == (today - timedelta(days=29)).isoformat()
    days_90 = client.get(
        "/api/v1/workouts/progress/training-analytics?period_days=90",
        headers=headers,
    ).json()
    assert days_90["completed_set_count"] == 7

    assert (
        client.get(
            "/api/v1/workouts/progress/training-analytics?period_days=14",
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/workouts/progress/training-analytics?exercise_history_limit=101",
            headers=headers,
        ).status_code
        == 422
    )


def test_training_analytics_handles_empty_data_and_trainer_isolation(client) -> None:
    client_headers = _auth(client, 27_101)
    coach_headers = _auth(client, 27_102, is_coach=True)
    other_coach_headers = _auth(client, 27_103, is_coach=True)
    client_id = _user_id(27_101)
    coach_id = _user_id(27_102)

    empty = client.get(
        "/api/v1/workouts/progress/training-analytics?period_days=90",
        headers=client_headers,
    )
    assert empty.status_code == 200
    assert empty.json()["exercises"] == []
    assert empty.json()["external_load_volume_kg"] is None
    assert empty.json()["rir"]["missing_set_count"] == 0
    assert empty.json()["data_sufficiency"]["workout_logging"]["status"] == "insufficient"

    with get_session_context() as db:
        custom = Exercise(
            slug="analytics-custom-no-metadata",
            title="Пользовательское упражнение",
            primary_muscle=None,
            equipment=None,
            created_by_user_id=client_id,
        )
        db.add(custom)
        db.flush()
        program = _program(db, client_id)
        _add_exercise_session(
            db,
            program,
            custom.id,
            days_ago=1,
            sets=[(None, None, None, True)],
        )
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=client_id, status="active"))

    missing_metadata = client.get(
        "/api/v1/workouts/progress/training-analytics",
        headers=client_headers,
    ).json()
    assert missing_metadata["completed_set_count"] == 1
    assert missing_metadata["reps_total"] is None
    assert missing_metadata["completed_sets_without_muscle_metadata"] == 1
    assert missing_metadata["primary_muscle_exposure"] == []
    assert missing_metadata["muscle_group_workload"] == []
    assert missing_metadata["rir"]["missing_set_count"] == 1
    assert missing_metadata["data_sufficiency"]["workout_logging"]["status"] == "insufficient"
    assert missing_metadata["data_sufficiency"]["rir_coverage"]["status"] == "insufficient"

    detail = client.get(
        f"/api/v1/coach/clients/{client_id}/training-analytics",
        headers=coach_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["data_sufficiency"] == missing_metadata["data_sufficiency"]
    assert detail.json()["muscle_group_workload"] == missing_metadata["muscle_group_workload"]
    assert detail.json()["frequency_per_week"] == missing_metadata["frequency_per_week"]
    denied = client.get(
        f"/api/v1/coach/clients/{client_id}/training-analytics",
        headers=other_coach_headers,
    )
    assert denied.status_code == 404

    with get_session_context() as db:
        relation = db.query(CoachClient).filter(CoachClient.client_user_id == client_id).one()
        relation.status = "ended"

    revoked = client.get(
        f"/api/v1/coach/clients/{client_id}/training-analytics",
        headers=coach_headers,
    )
    assert revoked.status_code == 404


def test_training_analytics_bounds_long_history_with_constant_query_count(client) -> None:
    _auth(client, 27_201)
    user_id = _user_id(27_201)
    with get_session_context() as db:
        bench = db.query(Exercise).filter(Exercise.slug == "bench-press").one()
        program = _program(db, user_id)
        for days_ago in range(25):
            _add_exercise_session(
                db,
                program,
                bench.id,
                days_ago=days_ago,
                sets=[(8 + days_ago, 20 + days_ago, None, True)],
            )
        db.commit()

        user = db.query(User).options(joinedload(User.profile)).filter(User.id == user_id).one()
        token = begin_sql_metrics()
        try:
            result = build_training_analytics(
                db,
                user,
                30,
                exercise_history_limit=2,
            )
            metrics = current_sql_metrics()
        finally:
            reset_sql_metrics(token)

    assert result["completed_set_count"] == 25
    assert result["exercises"][0]["performed_session_count"] == 25
    assert result["exercises"][0]["history_truncated"] is True
    assert len(result["exercises"][0]["sessions"]) == 2
    assert metrics.query_count == 6
