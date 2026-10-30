from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import joinedload
from test_training_analytics import _add_exercise_session, _auth, _program, _user_id

from fitminiapp_api.db.performance import begin_sql_metrics, current_sql_metrics, reset_sql_metrics
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import UserWorkout, UserWorkoutExercise, UserWorkoutSet
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.services.activity_heatmap import build_activity_heatmap


def test_activity_heatmap_uses_confirmed_instants_and_reports_legacy_unknown(client):
    headers = _auth(client, 727_835)
    user_id = _user_id(727_835)
    now = datetime(2026, 3, 9, 12, tzinfo=UTC)
    with get_session_context() as db:
        user = db.query(User).filter_by(id=user_id).one()
        if user.profile is None:
            user.profile = UserProfile(timezone="America/New_York")
        else:
            user.profile.timezone = "America/New_York"
        exercise = db.query(Exercise).filter_by(slug="bench-press").one()
        program = _program(db, user_id)
        completed = _add_exercise_session(
            db,
            program,
            exercise.id,
            days_ago=1,
            sets=[(8, 10, None, True), (8, 10, None, True), (8, 10, None, False)],
        )
        completed.completed_at_utc = datetime(2026, 3, 8, 4, 30)
        db.flush()
        db.expire(completed, ["exercises"])
        completed.exercises[0].sets[1].set_kind = "warmup"
        planned = _add_exercise_session(
            db, program, exercise.id, days_ago=1, sets=[], status="planned"
        )
        planned.completed_at_utc = datetime(2026, 3, 8, 5, 30)
        db.flush()
        result = build_activity_heatmap(db, user, now=now)
        assert len(result["days"]) == 365
        by_day = {row["date"].isoformat(): row for row in result["days"]}
        assert by_day["2026-03-07"]["completed_workouts"] == 1
        assert by_day["2026-03-07"]["working_sets"] == 1
        assert by_day["2026-03-08"]["completed_workouts"] == 0
        legacy = _add_exercise_session(db, program, exercise.id, days_ago=2, sets=[])
        legacy.completed_at = datetime(2026, 3, 8, 9)
        db.flush()
        result = build_activity_heatmap(db, user, now=now)
        assert result["history_complete"] is False
        assert result["undated_workouts"] == 1
        assert result["days"][-1]["completed_workouts"] is None
        assert result["days"][-3]["completed_workouts"] == 1

    response = client.get("/api/v1/workouts/progress/activity-heatmap", headers=headers)
    assert response.status_code == 200
    assert len(response.json()["days"]) == 365
    assert client.get("/api/v1/workouts/progress/activity-heatmap").status_code in (401, 403)


def test_activity_heatmap_bounds_queries_and_isolates_accounts(client):
    _auth(client, 727_836)
    _auth(client, 727_837)
    now = datetime(2026, 3, 9, 12, tzinfo=UTC)
    with get_session_context() as db:
        user = (
            db.query(User).options(joinedload(User.profile)).filter_by(id=_user_id(727_836)).one()
        )
        program = _program(db, user.id)
        other = _program(db, _user_id(727_837))
        exercise_id = db.query(Exercise.id).filter_by(slug="bench-press").scalar()
        assert exercise_id is not None
        for index in range(366):
            workout = UserWorkout(
                user_program_id=program.id,
                scheduled_date=now.date(),
                day_number=1,
                title="Тренировка",
                status="completed",
                completed_at_utc=(now - timedelta(days=index)).replace(tzinfo=None),
            )
            workout.exercises.append(
                UserWorkoutExercise(
                    exercise_id=exercise_id,
                    sort_order=1,
                    prescribed_sets=2,
                    prescribed_reps="8",
                    rest_seconds=60,
                    sets=[
                        UserWorkoutSet(set_number=number, is_completed=True) for number in (1, 2)
                    ],
                )
            )
            db.add(workout)
        db.add(
            UserWorkout(
                user_program_id=other.id,
                scheduled_date=now.date(),
                day_number=1,
                title="Другая",
                status="completed",
                completed_at_utc=now.replace(tzinfo=None),
            )
        )
        for status in ("planned", "skipped", "cancelled"):
            db.add(
                UserWorkout(
                    user_program_id=program.id,
                    scheduled_date=now.date(),
                    day_number=1,
                    title=status,
                    status=status,
                    completed_at_utc=now.replace(tzinfo=None),
                )
            )
        db.flush()
        token = begin_sql_metrics()
        try:
            result = build_activity_heatmap(db, user, now=now)
            metrics = current_sql_metrics()
        finally:
            reset_sql_metrics(token)
        assert metrics.query_count == 2
        assert sum(day["completed_workouts"] for day in result["days"]) == 365
        assert sum(day["working_sets"] for day in result["days"]) == 730
        assert result["history_complete"] is True
        print(f"Activity SQL: {metrics.query_count} queries, {metrics.duration_ms:.1f} ms")


def test_finish_records_utc_instant_without_replacing_legacy_time(client):
    headers = _auth(client, 727_838)
    user_id = _user_id(727_838)
    with get_session_context() as db:
        exercise = db.query(Exercise).filter_by(slug="bench-press").one()
        program = _program(db, user_id)
        workout = _add_exercise_session(
            db, program, exercise.id, days_ago=1, sets=[(8, 10, None, True)], status="in_progress"
        )
        db.flush()
        workout_id = workout.id
    before = datetime.now(UTC).replace(tzinfo=None)
    response = client.post(f"/api/v1/workouts/{workout_id}/finish", headers=headers)
    after = datetime.now(UTC).replace(tzinfo=None)
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        workout = db.get(UserWorkout, workout_id)
        assert workout.completed_at is not None
        assert before <= workout.completed_at_utc <= after


def test_repeated_dst_hour_groups_distinct_instants_on_the_same_local_day(client):
    _auth(client, 727_839)
    with get_session_context() as db:
        user = db.query(User).filter_by(id=_user_id(727_839)).one()
        if user.profile is None:
            user.profile = UserProfile(timezone="America/New_York")
        else:
            user.profile.timezone = "America/New_York"
        program = _program(db, user.id)
        for hour in (5, 6):
            db.add(
                UserWorkout(
                    user_program_id=program.id,
                    scheduled_date=datetime(2026, 10, 31).date(),
                    day_number=1,
                    title="Тренировка",
                    status="completed",
                    completed_at_utc=datetime(2026, 11, 1, hour, 30),
                )
            )
        db.flush()
        result = build_activity_heatmap(db, user, now=datetime(2026, 11, 2, 12, tzinfo=UTC))
        day = next(row for row in result["days"] if row["date"].isoformat() == "2026-11-01")
        assert day["completed_workouts"] == 2


def test_calendar_year_preserves_leap_day_and_marks_future(client):
    headers = _auth(client, 727_840)
    with get_session_context() as db:
        user = db.query(User).filter_by(id=_user_id(727_840)).one()
        result = build_activity_heatmap(
            db, user, year=2024, now=datetime(2024, 3, 1, 12, tzinfo=UTC)
        )
        assert len(result["days"]) == 366
        assert result["days"][59]["date"].isoformat() == "2024-02-29"
        assert result["days"][59]["completed_workouts"] == 0
        assert result["days"][-1]["is_future"] is True
        assert result["days"][-1]["completed_workouts"] is None
        assert (
            len(
                build_activity_heatmap(db, user, year=2023, now=datetime(2024, 3, 1, tzinfo=UTC))[
                    "days"
                ]
            )
            == 365
        )
    assert (
        client.get(
            "/api/v1/workouts/progress/activity-heatmap?year=9999", headers=headers
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/workouts/progress/activity-heatmap?year=1969", headers=headers
        ).status_code
        == 422
    )
