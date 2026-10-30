from datetime import date, datetime
from decimal import Decimal

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import CoachClient, User


def _login(client, telegram_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_id, "is_coach": is_coach},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _workouts(owner_telegram_id: int, coach_telegram_id: int) -> tuple[int, int]:
    with get_session_context() as db:
        owner = db.query(User).filter_by(telegram_user_id=owner_telegram_id).one()
        coach = db.query(User).filter_by(telegram_user_id=coach_telegram_id).one()
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=owner.id, status="active"))
        program = UserProgram(user_id=owner.id, status="active", is_active=True)
        db.add(program)
        db.flush()
        completed = UserWorkout(
            user_program_id=program.id,
            scheduled_date=date(2026, 10, 29),
            day_number=1,
            title="Силовая и кардио",
            status="completed",
            completed_at=datetime(2026, 10, 30, 8, 15),
            completion_note="ЛИЧНАЯ ЗАМЕТКА",
        )
        planned = UserWorkout(
            user_program_id=program.id,
            scheduled_date=date(2026, 10, 31),
            day_number=2,
            title="Запланированная",
            status="in_progress",
        )
        db.add_all([completed, planned])
        db.flush()
        strength = Exercise(
            slug="copy-personal-strength",
            title="Моё упражнение",
            metric_type="strength",
            created_by_user_id=owner.id,
        )
        cardio = Exercise(
            slug="copy-personal-cardio",
            title="Велотренажёр",
            metric_type="cardio",
            created_by_user_id=owner.id,
        )
        db.add_all([strength, cardio])
        db.flush()
        strength_row = UserWorkoutExercise(
            workout_id=completed.id,
            exercise_id=strength.id,
            sort_order=2,
            prescribed_sets=4,
            prescribed_reps="8",
            notes="ПРИВАТНЫЙ КОММЕНТАРИЙ ТРЕНЕРА",
        )
        cardio_row = UserWorkoutExercise(
            workout_id=completed.id,
            exercise_id=cardio.id,
            sort_order=1,
            prescribed_sets=1,
            prescribed_reps="",
        )
        db.add_all([strength_row, cardio_row])
        db.flush()
        db.add_all(
            [
                UserWorkoutSet(
                    workout_exercise_id=strength_row.id,
                    set_number=3,
                    actual_reps=8,
                    actual_weight=Decimal("25.00"),
                    set_kind="drop",
                    is_completed=True,
                ),
                UserWorkoutSet(
                    workout_exercise_id=strength_row.id,
                    set_number=1,
                    actual_reps=12,
                    actual_weight=Decimal("0.00"),
                    set_kind="warmup",
                    is_completed=True,
                ),
                UserWorkoutSet(
                    workout_exercise_id=strength_row.id,
                    set_number=2,
                    actual_reps=None,
                    actual_weight=Decimal("37.50"),
                    set_kind="working",
                    is_completed=True,
                ),
                UserWorkoutSet(
                    workout_exercise_id=strength_row.id,
                    set_number=4,
                    actual_reps=999,
                    actual_weight=Decimal("999.00"),
                    set_kind="working",
                    is_completed=False,
                ),
                UserWorkoutSet(
                    workout_exercise_id=cardio_row.id,
                    set_number=1,
                    duration_minutes=24,
                    distance_km=Decimal("3.25"),
                    average_heart_rate_bpm=132,
                    heart_rate_zone=2,
                    is_completed=True,
                ),
            ]
        )
        return completed.id, planned.id


def test_completed_workout_copy_is_factual_ordered_and_private(client):
    owner_headers = _login(client, 828_001)
    _login(client, 828_002, is_coach=True)
    workout_id, _ = _workouts(828_001, 828_002)

    response = client.get(f"/api/v1/workouts/{workout_id}/copy", headers=owner_headers)

    assert response.status_code == 200, response.text
    assert {part.strip() for part in response.headers["cache-control"].split(",")} == {
        "private",
        "no-store",
    }
    data = response.json()
    assert set(data) == {"title", "scheduled_date", "completed_at", "exercises"}
    assert data["title"] == "Силовая и кардио"
    assert data["scheduled_date"] == "2026-10-29"
    assert data["completed_at"] == "2026-10-30T08:15:00"
    assert [row["exercise_title"] for row in data["exercises"]] == [
        "Велотренажёр",
        "Моё упражнение",
    ]
    cardio, strength = data["exercises"]
    assert cardio["metric_type"] == "cardio"
    assert cardio["sets"][0]["duration_minutes"] == 24
    assert cardio["sets"][0]["distance_km"] == 3.25
    assert cardio["sets"][0]["average_heart_rate_bpm"] == 132
    assert cardio["sets"][0]["heart_rate_zone"] == 2
    assert [row["set_number"] for row in strength["sets"]] == [1, 2, 3]
    assert [row["set_kind"] for row in strength["sets"]] == ["warmup", "working", "drop"]
    assert strength["sets"][0]["actual_weight"] == 0
    assert strength["sets"][1]["actual_weight"] == 37.5
    assert strength["sets"][1]["actual_reps"] is None
    assert all(
        set(row) == {"exercise_title", "metric_type", "sort_order", "sets"}
        for row in data["exercises"]
    )
    assert all("id" not in item for row in data["exercises"] for item in row["sets"])
    assert "ЛИЧНАЯ ЗАМЕТКА" not in response.text
    assert "ПРИВАТНЫЙ КОММЕНТАРИЙ" not in response.text
    assert "999" not in response.text

    with get_session_context() as db:
        workout = db.query(UserWorkout).filter_by(id=workout_id).one()
        assert workout.completion_note == "ЛИЧНАЯ ЗАМЕТКА"
        assert sum(len(row.sets) for row in workout.exercises) == 5


def test_workout_copy_requires_owner_and_completed_status(client):
    owner_headers = _login(client, 828_101)
    coach_headers = _login(client, 828_102, is_coach=True)
    other_headers = _login(client, 828_103)
    workout_id, planned_id = _workouts(828_101, 828_102)
    path = f"/api/v1/workouts/{workout_id}/copy"

    assert client.get(path).status_code == 401
    assert client.get(path, headers=coach_headers).status_code == 404
    assert client.get(path, headers=other_headers).status_code == 404
    assert (
        client.get(f"/api/v1/workouts/{planned_id}/copy", headers=owner_headers).status_code == 404
    )
    assert client.get("/api/v1/workouts/99999999/copy", headers=owner_headers).status_code == 404
