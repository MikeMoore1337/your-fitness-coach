from datetime import UTC, datetime, timedelta

from sqlalchemy import event
from test_program_cycle_domain import TODAY, assigned_cycle, schedule

from fitminiapp_api.api.v1 import workouts as workout_routes
from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import UserProgram, UserWorkout, UserWorkoutExercise
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services import program_versioning, programs


def auth(client, user_id, *, is_coach=False):
    response = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": user_id, "is_coach": is_coach}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def assignment(client, headers, *, duration=4):
    catalog = client.get("/api/v1/programs/exercises", headers=headers).json()
    exercise_id = next(item["id"] for item in catalog if item["metric_type"] == "strength")
    template = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Тест заметки",
            "goal": "strength",
            "level": "beginner",
            "assign_after_create": False,
            "days": [
                {
                    "title": f"День {number}",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": 1,
                            "prescribed_reps": "8",
                            "rest_seconds": 90,
                        }
                    ],
                }
                for number in range(1, 4)
            ],
        },
    )
    assert template.status_code == 200, template.text
    response = client.post(
        f"/api/v1/programs/templates/{template.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": duration},
    )
    assert response.status_code == 200, response.text
    return response.json()["user_program_id"]


def workout_id(program_id, week, day=3):
    with get_session_context() as db:
        return (
            db.query(UserWorkout.id)
            .filter_by(user_program_id=program_id, week_number=week, day_number=day)
            .scalar()
        )


def complete_in_past(workout, days, note):
    workout.status = "completed"
    workout.completed_at = now_msk_naive() - timedelta(days=days)
    workout.completed_at_utc = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    workout.completion_note = note


def previous_note(client, headers, workout):
    return client.get(f"/api/v1/workouts/{workout}/previous-completion-note", headers=headers)


def test_note_from_rescheduled_day_is_read_only_and_stays_in_history(client):
    headers = auth(client, 1195001)
    program = assignment(client, headers)
    first = workout_id(program, 1)
    next_workout = workout_id(program, 2)
    today = today_msk()
    moved = client.patch(
        f"/api/v1/workouts/{workout_id(program, 1, 1)}/schedule",
        headers=headers,
        json={"scheduled_date": (today + timedelta(days=3)).isoformat()},
    )
    assert moved.status_code == 200, moved.text
    moved = client.patch(
        f"/api/v1/workouts/{first}/schedule",
        headers=headers,
        json={"scheduled_date": today.isoformat()},
    )
    assert moved.status_code == 200, moved.text
    started = client.post(f"/api/v1/workouts/{first}/start", headers=headers)
    assert started.status_code == 200, started.text
    current_set = started.json()["exercises"][0]["sets"][0]
    saved_set = client.patch(
        f"/api/v1/workouts/sets/{current_set['id']}",
        headers=headers,
        json={"actual_weight": 42.5, "actual_reps": 8, "rir": "2", "is_completed": True},
    )
    assert saved_set.status_code == 200, saved_set.text
    finished = client.post(f"/api/v1/workouts/{first}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    feedback = client.put(
        f"/api/v1/workouts/{first}/completion-feedback",
        headers=headers,
        json={"note": "Жим ногами можно прибавить"},
    )
    assert feedback.status_code == 200, feedback.text

    statements = []

    def record_sql(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        result = previous_note(client, headers, next_workout)
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)
    assert len([statement for statement in statements if "user_workouts" in statement]) == 1
    assert not any(
        statement.lstrip().startswith(("insert", "update", "delete")) for statement in statements
    )
    assert result.status_code == 200, result.text
    assert set(result.headers["cache-control"].split(", ")) == {"private", "no-store"}
    assert result.json()["previous_note"] == {
        "note": "Жим ногами можно прибавить",
        "completed_on": today.isoformat(),
        "day_number": 3,
        "workout_title": "День 3",
        "is_latest_completion": True,
    }
    assert previous_note(client, headers, workout_id(program, 2, 1)).json() == {
        "previous_note": None
    }
    conflict = client.put(
        f"/api/v1/workouts/{next_workout}/completion-feedback",
        headers=headers,
        json={"note": "Нельзя сохранить до завершения"},
    )
    assert conflict.status_code == 409
    history = client.get("/api/v1/workouts/history", headers=headers).json()
    assert next(item for item in history if item["id"] == first)["completion_note"] == (
        "Жим ногами можно прибавить"
    )
    with get_session_context() as db:
        target = db.get(UserWorkout, next_workout)
        assert target.status == "planned" and target.completion_note is None
        assert all(
            item.actual_weight is None and item.actual_reps is None
            for item in target.exercises[0].sets
        )


def test_empty_changed_and_deleted_notes_use_factual_order_and_honest_label(client):
    headers = auth(client, 1195002)
    program = assignment(client, headers)
    older, latest, target = [workout_id(program, week) for week in (1, 2, 3)]
    with get_session_context() as db:
        complete_in_past(db.get(UserWorkout, older), 14, "Старая заметка")
        complete_in_past(db.get(UserWorkout, latest), 7, None)
        db.get(UserWorkout, older).scheduled_date = today_msk() + timedelta(days=100)
    result = previous_note(client, headers, target).json()["previous_note"]
    assert result["note"] == "Старая заметка"
    assert result["completed_on"] == (now_msk_naive() - timedelta(days=14)).date().isoformat()
    assert result["is_latest_completion"] is False
    edited = client.put(
        f"/api/v1/workouts/{older}/completion-feedback", headers=headers, json={"note": "Изменена"}
    )
    assert edited.status_code == 200, edited.text
    assert previous_note(client, headers, target).json()["previous_note"]["note"] == "Изменена"
    deleted = client.put(
        f"/api/v1/workouts/{older}/completion-feedback", headers=headers, json={"note": " "}
    )
    assert deleted.status_code == 200, deleted.text
    assert previous_note(client, headers, target).json() == {"previous_note": None}


def test_assignment_restart_and_rbac_are_isolated(client):
    headers = auth(client, 1195003)
    coach = auth(client, 1195004, is_coach=True)
    program = assignment(client, headers)
    first, target = workout_id(program, 1), workout_id(program, 2)
    with get_session_context() as db:
        source = db.get(UserWorkout, first)
        complete_in_past(source, 7, "Личная заметка")
        owner = db.query(User).filter_by(telegram_user_id=1195003).one()
        trainer = db.query(User).filter_by(telegram_user_id=1195004).one()
        db.add(CoachClient(coach_user_id=trainer.id, client_user_id=owner.id))
        original = db.get(UserProgram, program)
        restarted = UserProgram(
            user_id=owner.id,
            template_id=original.template_id,
            start_date=today_msk(),
            duration_weeks=2,
            schedule_weekdays=[],
            status="archived",
            is_active=False,
            restarted_from_program_id=original.id,
        )
        db.add(restarted)
        db.flush()
        restart_workout = UserWorkout(
            user_program_id=restarted.id,
            scheduled_date=today_msk(),
            day_number=3,
            week_number=1,
            title="День 3",
            status="planned",
        )
        db.add(restart_workout)
        db.flush()
        db.add(
            UserWorkoutExercise(
                workout_id=restart_workout.id,
                exercise_id=source.exercises[0].exercise_id,
                source_template_exercise_id=source.exercises[0].source_template_exercise_id,
                sort_order=1,
                prescribed_sets=1,
                prescribed_reps="8",
                rest_seconds=90,
            )
        )
        restart_id = restart_workout.id
        other = UserProgram(
            user_id=owner.id,
            template_id=None,
            start_date=today_msk(),
            duration_weeks=1,
            schedule_weekdays=[],
            status="archived",
            is_active=False,
        )
        db.add(other)
        db.flush()
        other_workout = UserWorkout(
            user_program_id=other.id,
            scheduled_date=today_msk(),
            day_number=3,
            week_number=1,
            title="Другая программа",
            status="planned",
        )
        db.add(other_workout)
        db.flush()
        other_id = other_workout.id
    assert (
        previous_note(client, headers, target).json()["previous_note"]["note"] == "Личная заметка"
    )
    assert previous_note(client, headers, restart_id).json() == {"previous_note": None}
    assert previous_note(client, headers, other_id).json() == {"previous_note": None}
    assert previous_note(client, coach, target).status_code == 404
    assert client.get(f"/api/v1/workouts/{target}/previous-completion-note").status_code == 401


def test_changed_day_lineage_and_legacy_are_not_guessed(client):
    headers = auth(client, 1195005)
    program = assignment(client, headers)
    first, target = workout_id(program, 1), workout_id(program, 2)
    with get_session_context() as db:
        previous, current = db.get(UserWorkout, first), db.get(UserWorkout, target)
        complete_in_past(previous, 7, "Заметка дня")
        current.exercises[0].exercise_id = (
            db.query(Exercise.id)
            .filter(Exercise.id != previous.exercises[0].exercise_id)
            .first()[0]
        )
        # The source slot remains stable even when a future exercise is replaced.
    assert previous_note(client, headers, target).json()["previous_note"]["note"] == "Заметка дня"
    with get_session_context() as db:
        db.get(UserWorkout, target).exercises[0].source_template_exercise_id += 100_000
    assert previous_note(client, headers, target).json() == {"previous_note": None}
    with get_session_context() as db:
        previous, current = db.get(UserWorkout, first), db.get(UserWorkout, target)
        previous.exercises[0].source_template_exercise_id = None
        current.exercises[0].source_template_exercise_id = None
        current.exercises[0].exercise_id = previous.exercises[0].exercise_id
    assert previous_note(client, headers, target).json()["previous_note"]["note"] == "Заметка дня"
    with get_session_context() as db:
        db.get(UserWorkout, target).exercises[0].sort_order += 1
    assert previous_note(client, headers, target).json() == {"previous_note": None}


def test_ambiguous_or_missing_completion_time_fails_closed(client):
    headers = auth(client, 1195006)
    program = assignment(client, headers)
    first, target = workout_id(program, 1), workout_id(program, 2)
    with get_session_context() as db:
        previous, current = db.get(UserWorkout, first), db.get(UserWorkout, target)
        complete_in_past(previous, 0, "Слишком близко по времени")
        previous.completed_at_utc = None
        current.status = "in_progress"
        current.started_at = now_msk_naive()
    assert previous_note(client, headers, target).json() == {"previous_note": None}
    with get_session_context() as db:
        db.get(UserWorkout, first).completed_at = None
    assert previous_note(client, headers, target).json() == {"previous_note": None}


def test_started_workout_uses_previous_completed_day_without_copying_note(client):
    headers = auth(client, 1195009)
    program = assignment(client, headers)
    first, target = workout_id(program, 1), workout_id(program, 2)
    with get_session_context() as db:
        complete_in_past(db.get(UserWorkout, first), 14, "До старта")
        current = db.get(UserWorkout, target)
        current.status = "in_progress"
        current.started_at = now_msk_naive() - timedelta(days=7)
    assert previous_note(client, headers, target).json()["previous_note"]["note"] == "До старта"
    with get_session_context() as db:
        assert db.get(UserWorkout, target).completion_note is None


def test_ambiguous_order_cannot_be_claimed_as_latest(client):
    headers = auth(client, 1195007)
    program = assignment(client, headers)
    first, second, target = [workout_id(program, week) for week in (1, 2, 3)]
    with get_session_context() as db:
        complete_in_past(db.get(UserWorkout, first), 14, "Заметка A")
        complete_in_past(db.get(UserWorkout, second), 14, "Заметка B")
        db.get(UserWorkout, second).completed_at_utc = None
    assert previous_note(client, headers, target).json() == {"previous_note": None}


def test_new_day_context_does_not_inherit_old_context_but_can_build_its_own_history(client):
    headers = auth(client, 1195008)
    program = assignment(client, headers)
    first, second, target = [workout_id(program, week) for week in (1, 2, 3)]
    with get_session_context() as db:
        old = db.get(UserWorkout, first)
        complete_in_past(old, 14, "Старый состав")
        old.exercises[0].source_template_exercise_id += 100_000
        complete_in_past(db.get(UserWorkout, second), 7, "Новый состав")
    assert previous_note(client, headers, target).json()["previous_note"]["note"] == "Новый состав"
    with get_session_context() as db:
        db.get(UserWorkout, second).completion_note = None
    assert previous_note(client, headers, target).json() == {"previous_note": None}


def test_repeating_cycle_future_edit_and_unmaterialized_read(client, monkeypatch):
    monkeypatch.setattr(programs, "today_for_user", lambda _user: TODAY)
    monkeypatch.setattr(program_versioning, "today_for_user", lambda _user: TODAY)
    headers, program, _, exercise = assigned_cycle(client, k=3, n=16, days=3)
    first, week2 = workout_id(program, 1), workout_id(program, 2)
    with get_session_context() as db:
        source = db.get(UserWorkout, first)
        complete_in_past(source, 14, "Повтор цикла")
        source.scheduled_date += timedelta(days=1)
        slot = source.exercises[0].source_template_exercise_id
        version = db.get(UserProgram, program).current_revision_number
        assert db.get(UserWorkout, week2).source_cycle_week == 2
    assert previous_note(client, headers, week2).json()["previous_note"]["note"] == "Повтор цикла"

    week8 = TODAY + timedelta(weeks=7)
    schedule(client, headers, week8, 7)
    target = workout_id(program, 8)
    with get_session_context() as db:
        row = db.get(UserWorkout, target)
        assert row.plan_materialized is False and not row.exercises
    assert previous_note(client, headers, target).json() == {"previous_note": None}
    with get_session_context() as db:
        row = db.get(UserWorkout, target)
        assert row.plan_materialized is False and not row.exercises

    payload = {
        "expected_revision_number": version,
        "effective_scope": "future_program",
        "day_number": 3,
        "target_template_exercise_id": slot,
        "exercise_id": exercise,
        "prescribed_sets": 3,
        "prescribed_reps": "12",
        "rest_seconds": 90,
        "from_week": 8,
        "source_cycle_week": 2,
    }
    edit = client.post(
        f"/api/v1/programs/assigned/{program}/exercises", headers=headers, json=payload
    )
    assert edit.status_code == 200, edit.text
    stale = client.post(
        f"/api/v1/programs/assigned/{program}/exercises", headers=headers, json=payload
    )
    assert stale.status_code == 409, stale.text
    assert previous_note(client, headers, target).json() == {"previous_note": None}
    with get_session_context() as db:
        current_program = db.get(UserProgram, program)
        program_versioning.materialize_next_cycle_window(db, current_program, through_date=week8)
    monkeypatch.setattr(
        workout_routes, "recovery_today_for_user", lambda _user: week8 + timedelta(days=2)
    )
    opened = client.get("/api/v1/workouts/today", headers=headers)
    assert opened.status_code == 200, opened.text
    assert opened.json()["id"] == target
    assert opened.json()["exercises"][0]["prescribed_reps"] == "12"
    assert previous_note(client, headers, target).json()["previous_note"]["note"] == "Повтор цикла"
    with get_session_context() as db:
        assert db.get(UserWorkout, first).completion_note == "Повтор цикла"
        current_program = db.get(UserProgram, program)
        week16 = TODAY + timedelta(weeks=15)
        program_versioning.materialize_next_cycle_window(db, current_program, through_date=week16)
    target16 = workout_id(program, 16)
    with get_session_context() as db:
        assert db.get(UserWorkout, target16).source_cycle_week == 1
    assert (
        previous_note(client, headers, target16).json()["previous_note"]["note"] == "Повтор цикла"
    )
