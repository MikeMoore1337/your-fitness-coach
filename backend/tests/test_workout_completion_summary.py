from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

from fitminiapp_api.api.v1 import workouts as workout_routes
from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import (
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services import programs
from fitminiapp_api.services.accounts import build_account_export


def _load_migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0053_workout_completion_feedback.py"
    )
    spec = importlib.util.spec_from_file_location("workout_completion_feedback_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


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


def _assigned_workout(client, headers: dict[str, str], *, sets: int = 2) -> dict:
    exercises = client.get("/api/v1/programs/exercises", headers=headers).json()
    exercise_id = next(item["id"] for item in exercises if item["metric_type"] == "strength")
    template = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Итог тренировки",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": False,
            "days": [
                {
                    "title": "Силовая тренировка",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": sets,
                            "prescribed_reps": "6-10",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert template.status_code == 200, template.text
    today = today_msk()
    assigned = client.post(
        f"/api/v1/programs/templates/{template.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={
            "start_date": today.isoformat(),
            "duration_weeks": 2,
            "schedule_weekdays": [today.weekday()],
        },
    )
    assert assigned.status_code == 200, assigned.text
    workout = client.get("/api/v1/workouts/today", headers=headers)
    assert workout.status_code == 200, workout.text
    return workout.json()


def _add_previous_result(
    workout_id: int,
    *,
    weight: float = 40,
    reps: int = 8,
    days_before: int = 7,
    completed_at: datetime | None = None,
) -> None:
    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout_id).one()
        current_exercise = current.exercises[0]
        previous = UserWorkout(
            user_program_id=current.user_program_id,
            scheduled_date=current.scheduled_date - timedelta(days=days_before),
            day_number=0,
            week_number=0,
            title="Предыдущая тренировка",
            status="completed",
            started_at=datetime(2026, 8, 1, 10, 0),
            completed_at=completed_at or datetime(2026, 8, 1, 11, 0),
        )
        db.add(previous)
        db.flush()
        previous_exercise = UserWorkoutExercise(
            workout_id=previous.id,
            exercise_id=current_exercise.exercise_id,
            sort_order=1,
            prescribed_sets=1,
            prescribed_reps="8",
            rest_seconds=90,
        )
        db.add(previous_exercise)
        db.flush()
        db.add(
            UserWorkoutSet(
                workout_exercise_id=previous_exercise.id,
                set_number=1,
                actual_reps=reps,
                actual_weight=weight,
                set_kind="working",
                is_completed=True,
            )
        )


def _start_and_log(client, headers: dict[str, str], workout: dict, values: list[tuple[int, float]]):
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    for workout_set, (reps, weight) in zip(
        started.json()["exercises"][0]["sets"], values, strict=False
    ):
        saved = client.patch(
            f"/api/v1/workouts/sets/{workout_set['id']}",
            headers=headers,
            json={"actual_reps": reps, "actual_weight": weight, "is_completed": True},
        )
        assert saved.status_code == 200, saved.text
    return started.json()


def test_completion_summary_is_factual_stable_and_exposes_feedback_to_trainer(
    client,
    monkeypatch,
) -> None:
    headers = _auth(client, 53_001)
    trainer_headers = _auth(client, 53_002, is_coach=True)
    workout = _assigned_workout(client, headers)
    _add_previous_result(workout["id"])
    started = _start_and_log(client, headers, workout, [(6, 50), (10, 45)])
    finished_at = datetime(2026, 8, 23, 13, 30)
    with get_session_context() as db:
        row = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        row.started_at = finished_at - timedelta(hours=1, minutes=30)
    monkeypatch.setattr(workout_routes, "now_for_user_naive", lambda _user: finished_at)

    finished = client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    payload = finished.json()
    summary = payload["completion_summary"]
    assert summary["duration_seconds"] == 5400
    assert summary["performed_exercises"] == 1
    assert summary["completed_sets"] == 2
    assert summary["total_sets"] == 2
    assert summary["reps_total"] == 16
    assert summary["reps_recorded_sets"] == 2
    assert summary["load_recorded_sets"] == 2
    assert summary["exercises"] == [
        {
            "workout_exercise_id": started["exercises"][0]["id"],
            "exercise_id": started["exercises"][0]["exercise_id"],
            "exercise_title": started["exercises"][0]["exercise_title"],
            "metric_type": "strength",
            "completed_sets": 2,
            "reps_total": 16,
            "reps_recorded_sets": 2,
            "max_load_kg": 50.0,
            "load_recorded_sets": 2,
            "duration_minutes": None,
            "distance_km": None,
            "average_heart_rate_bpm": None,
            "heart_rate_zone": None,
        }
    ]
    assert summary["personal_records"] == [
        {
            "exercise_id": started["exercises"][0]["exercise_id"],
            "exercise_title": started["exercises"][0]["exercise_title"],
            "kinds": ["max_load", "best_set_volume"],
            "max_load_kg": 50.0,
            "best_set_volume_kg": 450.0,
        }
    ]
    assert summary["next_workout"]["scheduled_date"] > workout["scheduled_date"]

    replay = client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=headers)
    assert replay.status_code == 200
    assert replay.json() == payload
    reloaded = client.get("/api/v1/workouts/today", headers=headers)
    assert reloaded.status_code == 200
    assert reloaded.json() == payload

    feedback = client.put(
        f"/api/v1/workouts/{workout['id']}/completion-feedback",
        headers=headers,
        json={"feedback": "as_expected", "note": "  Уверенный темп.  "},
    )
    assert feedback.status_code == 200, feedback.text
    assert feedback.json()["completion_summary"]["feedback"] == "as_expected"
    assert feedback.json()["completion_summary"]["note"] == "Уверенный темп."
    repeated_feedback = client.put(
        f"/api/v1/workouts/{workout['id']}/completion-feedback",
        headers=headers,
        json={"feedback": "as_expected", "note": "Уверенный темп."},
    )
    assert repeated_feedback.status_code == 200
    assert repeated_feedback.json() == feedback.json()

    client_id = _user_id(53_001)
    trainer_id = _user_id(53_002)
    with get_session_context() as db:
        db.add(CoachClient(coach_user_id=trainer_id, client_user_id=client_id))
    timeline = client.get(
        f"/api/v1/coach/clients/{client_id}/workouts",
        headers=trainer_headers,
    )
    assert timeline.status_code == 200, timeline.text
    current = next(item for item in timeline.json() if item["id"] == workout["id"])
    assert current["completion_feedback"] == "as_expected"
    assert current["completion_note"] == "Уверенный темп."

    with get_session_context() as db:
        export = build_account_export(db, db.get(User, client_id))
    exported = next(
        item
        for program in export["programs"]
        for item in program["workouts"]
        if item["id"] == workout["id"]
    )
    assert exported["completion_feedback"] == "as_expected"
    assert exported["completion_note"] == "Уверенный темп."


def test_incomplete_finish_requires_confirmation_and_no_record_is_invented(client) -> None:
    headers = _auth(client, 53_101)
    other_headers = _auth(client, 53_102)
    workout = _assigned_workout(client, headers, sets=2)
    _add_previous_result(workout["id"], weight=40, reps=8)
    _start_and_log(client, headers, workout, [(8, 40)])

    refused = client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=headers)
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Есть незаполненные подходы. Подтвердите досрочное завершение"
    )
    finished = client.post(
        f"/api/v1/workouts/{workout['id']}/finish",
        headers=headers,
        json={"confirm_incomplete": True},
    )
    assert finished.status_code == 200, finished.text
    summary = finished.json()["completion_summary"]
    assert summary["completed_sets"] == 1
    assert summary["total_sets"] == 2
    assert summary["personal_records"] == []

    assert (
        client.put(
            f"/api/v1/workouts/{workout['id']}/completion-feedback",
            headers=other_headers,
            json={"feedback": "harder_than_expected", "note": "Чужая заметка"},
        ).status_code
        == 404
    )
    too_long = client.put(
        f"/api/v1/workouts/{workout['id']}/completion-feedback",
        headers=headers,
        json={"feedback": "harder_than_expected", "note": "a" * 501},
    )
    assert too_long.status_code == 422


def test_feedback_is_rejected_before_workout_completion(client) -> None:
    headers = _auth(client, 53_201)
    workout = _assigned_workout(client, headers, sets=1)
    _start_and_log(client, headers, workout, [(8, 30)])

    response = client.put(
        f"/api/v1/workouts/{workout['id']}/completion-feedback",
        headers=headers,
        json={"feedback": "easier_than_expected", "note": None},
    )
    assert response.status_code == 409


def test_today_returns_most_recent_completed_workout(client, monkeypatch) -> None:
    headers = _auth(client, 53_301)
    first = _assigned_workout(client, headers, sets=1)
    _start_and_log(client, headers, first, [(8, 30)])
    first_completed_at = datetime(2026, 8, 23, 10, 0)
    monkeypatch.setattr(workout_routes, "now_for_user_naive", lambda _user: first_completed_at)
    assert client.post(f"/api/v1/workouts/{first['id']}/finish", headers=headers).status_code == 200

    with get_session_context() as db:
        first_row = db.query(UserWorkout).filter(UserWorkout.id == first["id"]).one()
        second = UserWorkout(
            user_program_id=first_row.user_program_id,
            scheduled_date=first_row.scheduled_date,
            day_number=2,
            week_number=first_row.week_number,
            title="Вторая завершённая тренировка",
            status="completed",
            started_at=first_completed_at + timedelta(hours=1),
            completed_at=first_completed_at + timedelta(hours=2),
        )
        db.add(second)
        db.flush()
        second_id = second.id

    reloaded = client.get("/api/v1/workouts/today", headers=headers)
    assert reloaded.status_code == 200, reloaded.text
    assert reloaded.json()["id"] == second_id


def test_personal_records_include_earlier_same_day(
    client,
    monkeypatch,
) -> None:
    fixed_today = datetime(2026, 8, 23).date()
    monkeypatch.setattr("test_workout_completion_summary.today_msk", lambda: fixed_today)
    monkeypatch.setattr(programs, "today_for_user", lambda _user: fixed_today)
    monkeypatch.setattr(workout_routes, "recovery_today_for_user", lambda _user: fixed_today)
    headers = _auth(client, 53_401)
    workout = _assigned_workout(client, headers, sets=1)
    current_completed_at = datetime(2026, 8, 23, 13, 0)
    _add_previous_result(
        workout["id"],
        weight=70,
        reps=8,
        days_before=0,
        completed_at=current_completed_at - timedelta(hours=2),
    )
    _start_and_log(client, headers, workout, [(8, 50)])
    monkeypatch.setattr(workout_routes, "now_for_user_naive", lambda _user: current_completed_at)

    finished = client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    assert finished.json()["completion_summary"]["personal_records"] == []


def test_personal_records_aggregate_duplicate_exercises(client, monkeypatch) -> None:
    headers = _auth(client, 53_402)
    workout = _assigned_workout(client, headers, sets=1)
    _add_previous_result(workout["id"], weight=55, reps=8)
    started = _start_and_log(client, headers, workout, [(8, 50)])
    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        duplicate = UserWorkoutExercise(
            workout_id=current.id,
            exercise_id=current.exercises[0].exercise_id,
            sort_order=2,
            prescribed_sets=1,
            prescribed_reps="8",
            rest_seconds=90,
        )
        db.add(duplicate)
        db.flush()
        db.add(
            UserWorkoutSet(
                workout_exercise_id=duplicate.id,
                set_number=1,
                actual_reps=8,
                actual_weight=60,
                set_kind="working",
                is_completed=True,
            )
        )
    current_completed_at = datetime(2026, 8, 23, 13, 0)
    monkeypatch.setattr(workout_routes, "now_for_user_naive", lambda _user: current_completed_at)

    finished = client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    summary = finished.json()["completion_summary"]
    assert len(summary["exercises"]) == 2
    assert summary["exercises"][0]["exercise_id"] == started["exercises"][0]["exercise_id"]
    assert summary["exercises"][1]["exercise_id"] == started["exercises"][0]["exercise_id"]
    assert summary["personal_records"] == [
        {
            "exercise_id": started["exercises"][0]["exercise_id"],
            "exercise_title": started["exercises"][0]["exercise_title"],
            "kinds": ["max_load", "best_set_volume"],
            "max_load_kg": 60.0,
            "best_set_volume_kg": 480.0,
        }
    ]


def test_completion_feedback_migration_enforces_values_and_rolls_back(tmp_path: Path) -> None:
    migration = _load_migration()
    assert migration.down_revision == "0052_fast_nutrition_logging"
    engine = sa.create_engine(f"sqlite:///{(tmp_path / 'completion-feedback.db').as_posix()}")
    metadata = sa.MetaData()
    sa.Table("user_workouts", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        columns = {column["name"] for column in sa.inspect(connection).get_columns("user_workouts")}
        assert {
            "completion_feedback",
            "completion_note",
            "completion_feedback_updated_at",
        }.issubset(columns)
        connection.execute(
            sa.text(
                "INSERT INTO user_workouts (id, completion_feedback, completion_note) "
                "VALUES (1, 'as_expected', 'Нормально')"
            )
        )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                sa.text(
                    "INSERT INTO user_workouts (id, completion_feedback) VALUES (2, 'diagnosis')"
                )
            )
        migration.downgrade()
        downgraded = {
            column["name"] for column in sa.inspect(connection).get_columns("user_workouts")
        }
        assert "completion_feedback" not in downgraded
        assert "completion_note" not in downgraded

    engine.dispose()
