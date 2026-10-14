from datetime import timedelta

from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.program import (
    ProgramRevision,
    ProgramTemplate,
    ProgramTemplateExerciseWeekPrescription,
    TrainingBlock,
    UserProgram,
    UserWorkout,
    WorkoutAdaptation,
)
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services.program_common import ProgramError


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _assigned_program(
    client,
    headers: dict[str, str],
    *,
    start_date=None,
    duration_weeks: int = 3,
    mode: str = "self",
    target_telegram_user_id: int | None = None,
) -> tuple[int, list[dict]]:
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    assert len(exercises) >= 2
    start_date = start_date or (today_msk() + timedelta(days=1))
    response = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Версионируемая программа",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": mode,
            "target_telegram_user_id": target_telegram_user_id,
            "assign_after_create": True,
            "start_date": start_date.isoformat(),
            "duration_weeks": duration_weeks,
            "schedule_weekdays": [start_date.weekday()],
            "days": [
                {
                    "title": "Силовая",
                    "exercises": [
                        {
                            "exercise_id": exercises[0]["id"],
                            "prescribed_sets": 2,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["assigned_program_id"], exercises


def _template_edit_payload(template: dict, *, exercise_id: int, expected_revision: int) -> dict:
    day = template["days"][0]
    source = day["exercises"][0]
    return {
        "title": f"{template['title']} — обновлена",
        "goal": template["goal"],
        "level": template["level"],
        "mode": "self",
        "assign_after_create": False,
        "duration_weeks": 1,
        "schedule_weekdays": [0],
        "expected_revision_number": expected_revision,
        "days": [
            {
                "title": "Силовая — обновлена",
                "exercises": [
                    {
                        "exercise_id": exercise_id,
                        "prescribed_sets": 4,
                        "prescribed_reps": "10-12",
                        "prescribed_duration_minutes": source["prescribed_duration_minutes"],
                        "rest_seconds": 120,
                        "notes": "Новая рабочая схема",
                    }
                ],
            }
        ],
    }


def test_template_edit_applies_only_to_future_planned_workouts(client):
    headers = _auth(client, 93000)
    program_id, exercises = _assigned_program(client, headers, duration_weeks=3)
    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        template_id = program.template_id
        workouts = sorted(program.workouts, key=lambda item: item.scheduled_date)
        completed, in_progress, future = workouts
        completed.status = "completed"
        completed.completed_at = now_msk_naive()
        completed_set = completed.exercises[0].sets[0]
        completed_set.actual_reps = 11
        completed_set.actual_weight = 50
        completed_set.is_completed = True
        in_progress.status = "in_progress"
        in_progress.started_at = now_msk_naive()
        in_progress_before = (
            in_progress.exercises[0].prescribed_sets,
            in_progress.exercises[0].prescribed_reps,
            in_progress.exercises[0].rest_seconds,
        )
        future_id = future.id
        db.commit()

    history_before = client.get("/api/v1/workouts/history", headers=headers)
    summary_before = client.get("/api/v1/workouts/history/summary", headers=headers)
    assert history_before.status_code == 200, history_before.text
    assert summary_before.status_code == 200, summary_before.text

    template = client.get(f"/api/v1/programs/templates/{template_id}", headers=headers)
    assert template.status_code == 200, template.text
    concurrent_snapshot = client.get(f"/api/v1/programs/templates/{template_id}", headers=headers)
    assert concurrent_snapshot.status_code == 200, concurrent_snapshot.text
    payload = _template_edit_payload(
        template.json(), exercise_id=exercises[1]["id"], expected_revision=1
    )
    concurrent_payload = _template_edit_payload(
        concurrent_snapshot.json(), exercise_id=exercises[0]["id"], expected_revision=1
    )
    updated = client.patch(
        f"/api/v1/programs/templates/{template_id}", headers=headers, json=payload
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["assigned_program_updated"] is True
    assert updated.json()["future_workouts_updated"] == 1
    assert updated.json()["assigned_program_revision_number"] == 2
    assert updated.json()["current_revision_number"] == 2

    stale_concurrent = client.patch(
        f"/api/v1/programs/templates/{template_id}",
        headers=headers,
        json=concurrent_payload,
    )
    assert stale_concurrent.status_code == 409
    assert stale_concurrent.json()["detail"] == "Program revision conflict"
    retry = client.patch(f"/api/v1/programs/templates/{template_id}", headers=headers, json=payload)
    assert retry.status_code == 409
    assert retry.json()["detail"] == "Program revision conflict"

    refreshed = client.get(f"/api/v1/programs/templates/{template_id}", headers=headers)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["current_revision_number"] == 2
    assert refreshed.json()["days"][0]["exercises"][0]["prescribed_sets"] == 4

    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        completed = next(item for item in program.workouts if item.status == "completed")
        in_progress = next(item for item in program.workouts if item.status == "in_progress")
        future = next(item for item in program.workouts if item.id == future_id)
        assert program.current_revision_number == 2
        assert program.duration_weeks == 3
        assert db.query(ProgramRevision).filter_by(user_program_id=program_id).count() == 2
        assert completed.status == "completed"
        assert completed.completed_at is not None
        assert completed.exercises[0].sets[0].actual_reps == 11
        assert completed.exercises[0].sets[0].actual_weight == 50
        assert in_progress.status == "in_progress"
        assert in_progress.started_at is not None
        assert (
            in_progress.exercises[0].prescribed_sets,
            in_progress.exercises[0].prescribed_reps,
            in_progress.exercises[0].rest_seconds,
        ) == in_progress_before
        assert future.id == future_id
        assert future.status == "planned"
        assert future.exercises[0].exercise_id == exercises[1]["id"]
        assert future.exercises[0].prescribed_sets == 4
        assert future.exercises[0].prescribed_reps == "10-12"
        assert future.exercises[0].rest_seconds == 120
        assert len(future.exercises[0].sets) == 4
        assert {(item.week_number, item.day_number) for item in program.workouts} == {
            (1, 1),
            (2, 1),
            (3, 1),
        }

    history_after = client.get("/api/v1/workouts/history", headers=headers)
    summary_after = client.get("/api/v1/workouts/history/summary", headers=headers)
    assert history_after.status_code == 200, history_after.text
    assert summary_after.status_code == 200, summary_after.text
    assert history_after.json() == history_before.json()
    assert summary_after.json() == summary_before.json()


def test_template_edit_without_active_assignment_only_updates_the_template(client):
    headers = _auth(client, 93009)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Шаблон без назначения",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": False,
            "days": [
                {
                    "title": "Силовая",
                    "exercises": [
                        {
                            "exercise_id": exercises[0]["id"],
                            "prescribed_sets": 2,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    template = created.json()["template"]
    payload = _template_edit_payload(
        template,
        exercise_id=exercises[1]["id"],
        expected_revision=1,
    )
    payload.pop("expected_revision_number")

    updated = client.patch(
        f"/api/v1/programs/templates/{template['id']}",
        headers=headers,
        json=payload,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["assigned_program_updated"] is False
    assert updated.json()["future_workouts_updated"] == 0
    assert updated.json()["assigned_program_revision_number"] is None
    assert updated.json()["days"][0]["exercises"][0]["exercise_id"] == exercises[1]["id"]


def test_coach_template_edit_updates_client_future_workouts(client):
    coach_headers = _auth(client, 93010, is_coach=True)
    client_headers = _auth(client, 93011)
    with get_session_context() as db:
        coach_user = db.query(User).filter(User.telegram_user_id == 93010).one()
        client_user = db.query(User).filter(User.telegram_user_id == 93011).one()
        db.add(
            CoachClient(
                coach_user_id=coach_user.id,
                client_user_id=client_user.id,
                status="active",
                accepted_at=now_msk_naive(),
            )
        )
        db.commit()

    program_id, exercises = _assigned_program(
        client,
        coach_headers,
        duration_weeks=2,
        mode="coach",
        target_telegram_user_id=93011,
    )
    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        template_id = program.template_id
        schedule_weekdays = list(program.schedule_weekdays)

    template = client.get(f"/api/v1/programs/templates/{template_id}", headers=coach_headers)
    assert template.status_code == 200, template.text
    payload = _template_edit_payload(
        template.json(),
        exercise_id=exercises[1]["id"],
        expected_revision=1,
    )
    payload.update(
        {
            "mode": "coach",
            "target_telegram_user_id": 93011,
            "schedule_weekdays": schedule_weekdays,
        }
    )
    updated = client.patch(
        f"/api/v1/programs/templates/{template_id}",
        headers=coach_headers,
        json=payload,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["assigned_program_updated"] is True
    assert updated.json()["future_workouts_updated"] == 2
    assert updated.json()["assigned_program_revision_number"] == 2

    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        assert program.current_revision_number == 2
        assert all(
            workout.exercises[0].exercise_id == exercises[1]["id"] for workout in program.workouts
        )

    client_template = client.get(
        f"/api/v1/programs/templates/{template_id}", headers=client_headers
    )
    assert client_template.status_code == 200, client_template.text
    assert client_template.json()["current_revision_number"] == 2


def test_template_edit_can_add_and_remove_future_program_days_without_deleting_rows(client):
    headers = _auth(client, 93008)
    program_id, exercises = _assigned_program(client, headers, duration_weeks=2)
    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        template_id = program.template_id
        first_weekday = program.start_date.weekday()

    template = client.get(f"/api/v1/programs/templates/{template_id}", headers=headers)
    assert template.status_code == 200, template.text
    source = template.json()
    first_day = source["days"][0]
    first_exercise = first_day["exercises"][0]
    add_day_payload = {
        "title": source["title"],
        "goal": source["goal"],
        "level": source["level"],
        "mode": "self",
        "assign_after_create": False,
        "duration_weeks": 1,
        "schedule_weekdays": [first_weekday, (first_weekday + 1) % 7],
        "expected_revision_number": 1,
        "days": [
            {
                "title": first_day["title"],
                "exercises": [
                    {
                        "exercise_id": first_exercise["exercise_id"],
                        "prescribed_sets": first_exercise["prescribed_sets"],
                        "prescribed_reps": first_exercise["prescribed_reps"],
                        "rest_seconds": first_exercise["rest_seconds"],
                    }
                ],
            },
            {
                "title": "Дополнительная тренировка",
                "exercises": [
                    {
                        "exercise_id": exercises[1]["id"],
                        "prescribed_sets": 3,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            },
        ],
    }
    added = client.patch(
        f"/api/v1/programs/templates/{template_id}",
        headers=headers,
        json=add_day_payload,
    )
    assert added.status_code == 200, added.text
    assert added.json()["future_workouts_updated"] == 4

    with get_session_context() as db:
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.week_number, UserWorkout.day_number)
            .all()
        )
        assert len(workouts) == 4
        assert {workout.day_number for workout in workouts} == {1, 2}
        assert all(workout.status == "planned" for workout in workouts)
        assert all(
            any(item.exercise_id == exercises[1]["id"] for item in workout.exercises)
            for workout in workouts
            if workout.day_number == 2
        )

    remove_day_payload = {
        **add_day_payload,
        "expected_revision_number": 2,
        "schedule_weekdays": [first_weekday],
        "days": [add_day_payload["days"][0]],
    }
    removed = client.patch(
        f"/api/v1/programs/templates/{template_id}",
        headers=headers,
        json=remove_day_payload,
    )
    assert removed.status_code == 200, removed.text

    with get_session_context() as db:
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.week_number, UserWorkout.day_number)
            .all()
        )
        assert len(workouts) == 4
        assert [workout.status for workout in workouts if workout.day_number == 2] == [
            "cancelled",
            "cancelled",
        ]
        assert all(workout.status == "planned" for workout in workouts if workout.day_number == 1)
        removed_day_ids = {workout.id for workout in workouts if workout.day_number == 2}

    readded = client.patch(
        f"/api/v1/programs/templates/{template_id}",
        headers=headers,
        json={
            **add_day_payload,
            "expected_revision_number": 3,
        },
    )
    assert readded.status_code == 200, readded.text
    assert readded.json()["future_workouts_updated"] == 4

    with get_session_context() as db:
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.week_number, UserWorkout.day_number)
            .all()
        )
        assert len(workouts) == 4
        assert {(workout.week_number, workout.day_number) for workout in workouts} == {
            (1, 1),
            (1, 2),
            (2, 1),
            (2, 2),
        }
        assert all(workout.status == "planned" for workout in workouts)
        assert {workout.id for workout in workouts if workout.day_number == 2} == removed_day_ids


def test_active_template_edit_rolls_back_partial_future_update(client, monkeypatch):
    headers = _auth(client, 93080)
    program_id, exercises = _assigned_program(client, headers, duration_weeks=4)
    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        template_id = program.template_id
        before = {
            workout.id: (
                workout.status,
                workout.scheduled_date,
                workout.title,
                workout.exercises[0].exercise_id,
                workout.exercises[0].prescribed_sets,
                len(workout.exercises[0].sets),
            )
            for workout in program.workouts
        }
        assert program.current_revision_number == 1

    template = client.get(f"/api/v1/programs/templates/{template_id}", headers=headers)
    assert template.status_code == 200, template.text
    payload = _template_edit_payload(
        template.json(), exercise_id=exercises[1]["id"], expected_revision=1
    )

    from fitminiapp_api.services import program_versioning

    original_replace = program_versioning._replace_workout_exercises_from_template
    calls = 0

    def fail_on_second_replace(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ProgramError("simulated partial failure")
        return original_replace(*args, **kwargs)

    monkeypatch.setattr(
        program_versioning,
        "_replace_workout_exercises_from_template",
        fail_on_second_replace,
    )
    failed = client.patch(
        f"/api/v1/programs/templates/{template_id}", headers=headers, json=payload
    )
    assert failed.status_code == 400, failed.text
    assert failed.json()["detail"] == "simulated partial failure"
    assert calls == 2

    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        template = db.query(ProgramTemplate).filter(ProgramTemplate.id == template_id).one()
        assert program.current_revision_number == 1
        assert db.query(ProgramRevision).filter_by(user_program_id=program_id).count() == 1
        assert template.title == "Версионируемая программа"
        assert {
            workout.id: (
                workout.status,
                workout.scheduled_date,
                workout.title,
                workout.exercises[0].exercise_id,
                workout.exercises[0].prescribed_sets,
                len(workout.exercises[0].sets),
            )
            for workout in program.workouts
        } == before


def test_active_template_edit_preserves_recorded_sets_even_if_workout_is_still_planned(client):
    headers = _auth(client, 93081)
    program_id, exercises = _assigned_program(client, headers, duration_weeks=2)
    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        template_id = program.template_id
        protected = max(program.workouts, key=lambda item: item.scheduled_date)
        protected_exercise = protected.exercises[0]
        protected_set = protected_exercise.sets[0]
        protected_id = protected.id
        protected_exercise_id = protected_exercise.exercise_id
        protected_set_id = protected_set.id
        protected_set.actual_reps = 7
        protected_set.actual_weight = 42.5
        protected_set.is_completed = True
        protected_set.version = 2
        db.commit()

    template = client.get(f"/api/v1/programs/templates/{template_id}", headers=headers)
    assert template.status_code == 200, template.text
    payload = _template_edit_payload(
        template.json(), exercise_id=exercises[1]["id"], expected_revision=1
    )
    updated = client.patch(
        f"/api/v1/programs/templates/{template_id}", headers=headers, json=payload
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["future_workouts_updated"] == 1

    with get_session_context() as db:
        protected = db.query(UserWorkout).filter(UserWorkout.id == protected_id).one()
        protected_exercise = protected.exercises[0]
        protected_set = protected_exercise.sets[0]
        assert protected.status == "planned"
        assert protected_exercise.exercise_id == protected_exercise_id
        assert protected_set.id == protected_set_id
        assert protected_set.actual_reps == 7
        assert protected_set.actual_weight == 42.5
        assert protected_set.is_completed is True
        assert protected_set.version == 2


def test_revision_history_conflict_and_completed_workout_immutability(client):
    headers = _auth(client, 93001)
    program_id, exercises = _assigned_program(client, headers)

    initial = client.get(f"/api/v1/programs/assigned/{program_id}/revisions", headers=headers)
    assert initial.status_code == 200, initial.text
    assert len(initial.json()) == 1
    assert initial.json()[0]["revision_number"] == 1
    assert initial.json()[0]["change_kind"] == "assigned"
    assert initial.json()[0]["actor_role"] == "self"

    with get_session_context() as db:
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc())
            .all()
        )
        immutable_workout_id = workouts[0].id
        workouts[0].status = "completed"
        workouts[0].completed_at = now_msk_naive()
        db.commit()

    changed = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_scope": "future_program",
            "exercise_id": exercises[1]["id"],
            "day_number": 1,
            "prescribed_sets": 3,
            "prescribed_reps": "12",
            "rest_seconds": 60,
            "reason": "Добавить объём на будущие недели",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json() == {
        "workouts_updated": 2,
        "current_revision_number": 2,
    }

    stale = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_scope": "future_program",
            "exercise_id": exercises[1]["id"],
            "day_number": 1,
            "prescribed_sets": 4,
            "prescribed_reps": "10",
            "rest_seconds": 75,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == "Program revision conflict"

    history = client.get(
        f"/api/v1/programs/assigned/{program_id}/revisions", headers=headers
    ).json()
    assert [row["revision_number"] for row in history] == [2, 1]
    assert history[0]["reason"] == "Добавить объём на будущие недели"
    assert history[0]["changed_fields"] == {
        "operation": "exercise_upserted",
        "day_number": 1,
        "exercise_id": exercises[1]["id"],
        "workouts_updated": 2,
        "effective_scope": "future_program",
        "effective_date": today_msk().isoformat(),
    }
    with get_session_context() as db:
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc())
            .all()
        )
        immutable = next(row for row in workouts if row.id == immutable_workout_id)
        assert [row.exercise_id for row in immutable.exercises] == [exercises[0]["id"]]
        assert all(
            exercises[1]["id"] in {row.exercise_id for row in workout.exercises}
            for workout in workouts
            if workout.id != immutable_workout_id
        )


def test_trainer_revision_and_one_workout_adaptation_follow_template_precedence(client):
    coach_headers = _auth(client, 93031, is_coach=True)
    client_headers = _auth(client, 93032)
    client_id = client.get("/api/v1/me", headers=client_headers).json()["id"]
    with get_session_context() as db:
        coach_user = db.query(User).filter(User.telegram_user_id == 93031).one()
        client_user = db.query(User).filter(User.telegram_user_id == 93032).one()
        db.add(
            CoachClient(
                coach_user_id=coach_user.id,
                client_user_id=client_user.id,
                status="active",
                accepted_at=now_msk_naive(),
            )
        )
        db.commit()

    catalog = client.get("/api/v1/programs/exercises", headers=coach_headers).json()
    exercise_ids = {exercise["slug"]: exercise["id"] for exercise in catalog}
    exercise_slugs = [
        "bench-press",
        "squat",
        "dumbbell-curl",
        "crunch",
        "standing-calf-raise",
    ]
    assert all(slug in exercise_ids for slug in exercise_slugs)
    start = today_msk()
    created = client.post(
        "/api/v1/programs/templates",
        headers=coach_headers,
        json={
            "title": "Общий базовый шаблон",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "coach",
            "target_telegram_user_id": 93032,
            "assign_after_create": True,
            "start_date": start.isoformat(),
            "duration_weeks": 3,
            "schedule_weekdays": [start.weekday()],
            "days": [
                {
                    "title": "Силовая",
                    "exercises": [
                        {
                            "exercise_id": exercise_ids[slug],
                            "prescribed_sets": 3,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                        }
                        for slug in exercise_slugs
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    program_id = created.json()["assigned_program_id"]
    template_id = created.json()["template"]["id"]

    revised = client.post(
        f"/api/v1/coach/clients/{client_id}/programs/{program_id}/exercises",
        headers=coach_headers,
        json={
            "expected_revision_number": 1,
            "effective_scope": "future_program",
            "effective_date": start.isoformat(),
            "exercise_id": exercise_ids["bench-press"],
            "day_number": 1,
            "prescribed_sets": 5,
            "prescribed_reps": "8-10",
            "rest_seconds": 90,
            "reason": "Индивидуальная правка плана клиента",
        },
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["current_revision_number"] == 2

    history = client.get(
        f"/api/v1/programs/assigned/{program_id}/revisions",
        headers=coach_headers,
    )
    assert history.status_code == 200, history.text
    assert history.json()[0]["actor_role"] == "trainer"
    assert history.json()[0]["reason"] == "Индивидуальная правка плана клиента"

    today_workout = client.get("/api/v1/workouts/today", headers=client_headers)
    assert today_workout.status_code == 200, today_workout.text
    workout_id = today_workout.json()["id"]
    assert (
        next(
            item
            for item in today_workout.json()["exercises"]
            if item["exercise_id"] == exercise_ids["bench-press"]
        )["prescribed_sets"]
        == 5
    )
    preview = client.post(
        f"/api/v1/workouts/{workout_id}/adaptations/preview",
        headers=client_headers,
        json={"reason": "limited_time", "time_budget_minutes": 20},
    )
    assert preview.status_code == 200, preview.text
    applied = client.post(
        f"/api/v1/workouts/{workout_id}/adaptations/apply",
        headers=client_headers,
        json={
            "reason": "limited_time",
            "time_budget_minutes": 20,
            "preview_token": preview.json()["preview_token"],
        },
    )
    assert applied.status_code == 200, applied.text
    assert (
        next(
            item
            for item in applied.json()["workout"]["exercises"]
            if item["exercise_id"] == exercise_ids["bench-press"]
        )["prescribed_sets"]
        == 5
    )

    template = client.get(f"/api/v1/programs/templates/{template_id}", headers=coach_headers)
    assert template.status_code == 200, template.text
    assert (
        next(
            item
            for item in template.json()["days"][0]["exercises"]
            if item["exercise_id"] == exercise_ids["bench-press"]
        )["prescribed_sets"]
        == 3
    )
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert program is not None
        workouts = sorted(program.workouts, key=lambda item: item.scheduled_date)
        assert len(workouts) == 3
        assert workouts[0].id == workout_id
        future_prescriptions = [
            item.prescribed_sets
            for workout in workouts[1:]
            for item in workout.exercises
            if item.exercise_id == exercise_ids["bench-press"]
        ]
        assert future_prescriptions == [5, 5]
        adaptations = db.query(WorkoutAdaptation).all()
        assert [item.workout_id for item in adaptations] == [workout_id]


def test_next_workout_revision_scope_changes_only_the_earliest_planned_workout(client):
    headers = _auth(client, 93006)
    start = today_msk() + timedelta(days=1)
    program_id, exercises = _assigned_program(
        client,
        headers,
        start_date=start,
        duration_weeks=3,
    )

    changed = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_scope": "next_workout",
            "exercise_id": exercises[1]["id"],
            "day_number": 1,
            "prescribed_sets": 3,
            "prescribed_reps": "8",
            "rest_seconds": 90,
            "reason": "Начать прогрессию со следующей тренировки",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["workouts_updated"] == 1

    with get_session_context() as db:
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .all()
        )
        assert len(workouts) == 3
        assert exercises[1]["id"] in {item.exercise_id for item in workouts[0].exercises}
        assert all(
            exercises[1]["id"] not in {item.exercise_id for item in workout.exercises}
            for workout in workouts[1:]
        )

    history = client.get(
        f"/api/v1/programs/assigned/{program_id}/revisions", headers=headers
    ).json()
    assert history[0]["changed_fields"]["effective_scope"] == "next_workout"
    assert history[0]["changed_fields"]["effective_date"] == start.isoformat()


def test_current_block_revision_scope_leaves_later_weeks_unchanged(client):
    headers = _auth(client, 93007)
    start = today_msk() + timedelta(days=1)
    program_id, exercises = _assigned_program(
        client,
        headers,
        start_date=start,
        duration_weeks=3,
    )
    block = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "title": "Первый цикл",
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=13)).isoformat(),
            "purpose": "Постепенно освоить программу",
            "reason": "Сформировать первый этап",
        },
    )
    assert block.status_code == 201, block.text
    active = client.patch(
        f"/api/v1/programs/assigned/{program_id}/blocks/{block.json()['block']['id']}",
        headers=headers,
        json={
            "expected_revision_number": 2,
            "status": "active",
            "reason": "Начать первый этап",
        },
    )
    assert active.status_code == 200, active.text

    changed = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 3,
            "effective_scope": "current_block",
            "exercise_id": exercises[1]["id"],
            "day_number": 1,
            "prescribed_sets": 3,
            "prescribed_reps": "8",
            "rest_seconds": 90,
            "reason": "Обновить оставшуюся часть первого цикла",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["workouts_updated"] == 2

    with get_session_context() as db:
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .all()
        )
        assert len(workouts) == 3
        assert all(
            exercises[1]["id"] in {item.exercise_id for item in workout.exercises}
            for workout in workouts[:2]
        )
        assert exercises[1]["id"] not in {item.exercise_id for item in workouts[2].exercises}


def test_training_blocks_reject_overlap_and_enforce_manual_lifecycle(client):
    headers = _auth(client, 93002)
    start = today_msk() + timedelta(days=1)
    program_id, exercises = _assigned_program(
        client,
        headers,
        start_date=start,
        duration_weeks=4,
    )
    priority_ids = exercises[0].get("primary_muscle_ids", [])[:1]

    first = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "title": "Базовый блок",
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=6)).isoformat(),
            "purpose": "Закрепить технику основных движений",
            "priority_muscle_ids": priority_ids,
        },
    )
    assert first.status_code == 201, first.text
    first_block = first.json()["block"]
    assert first.json()["current_revision_number"] == 2
    assert first_block["duration_days"] == 7
    assert first_block["status"] == "planned"

    overlap = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=headers,
        json={
            "expected_revision_number": 2,
            "title": "Пересечение",
            "start_date": (start + timedelta(days=5)).isoformat(),
            "end_date": (start + timedelta(days=10)).isoformat(),
            "purpose": "Не должно сохраниться",
        },
    )
    assert overlap.status_code == 409
    assert overlap.json()["detail"] == "Training blocks must not overlap"

    second = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=headers,
        json={
            "expected_revision_number": 2,
            "title": "Облегчённая неделя",
            "start_date": (start + timedelta(days=7)).isoformat(),
            "end_date": (start + timedelta(days=13)).isoformat(),
            "purpose": "Снизить нагрузку вручную",
            "is_deload": True,
        },
    )
    assert second.status_code == 201, second.text
    second_block = second.json()["block"]
    assert second.json()["current_revision_number"] == 3
    assert second_block["is_deload"] is True

    premature = client.patch(
        f"/api/v1/programs/assigned/{program_id}/blocks/{second_block['id']}",
        headers=headers,
        json={"expected_revision_number": 3, "status": "active"},
    )
    assert premature.status_code == 409
    assert premature.json()["detail"] == "Complete the previous training block first"

    activated = client.patch(
        f"/api/v1/programs/assigned/{program_id}/blocks/{first_block['id']}",
        headers=headers,
        json={"expected_revision_number": 3, "status": "active"},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["current_revision_number"] == 4

    completed = client.patch(
        f"/api/v1/programs/assigned/{program_id}/blocks/{first_block['id']}",
        headers=headers,
        json={"expected_revision_number": 4, "status": "completed"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["current_revision_number"] == 5

    next_active = client.patch(
        f"/api/v1/programs/assigned/{program_id}/blocks/{second_block['id']}",
        headers=headers,
        json={"expected_revision_number": 5, "status": "active"},
    )
    assert next_active.status_code == 200, next_active.text
    assert next_active.json()["current_revision_number"] == 6

    immutable = client.patch(
        f"/api/v1/programs/assigned/{program_id}/blocks/{first_block['id']}",
        headers=headers,
        json={"expected_revision_number": 6, "notes": "Поздняя правка"},
    )
    assert immutable.status_code == 409
    assert immutable.json()["detail"] == ("Completed or archived training blocks are immutable")
    blocks = client.get(f"/api/v1/programs/assigned/{program_id}/blocks", headers=headers)
    assert blocks.status_code == 200
    assert [row["status"] for row in blocks.json()] == ["completed", "active"]


def test_trainer_access_is_revoked_without_erasing_program_history(client):
    coach_headers = _auth(client, 93003, is_coach=True)
    client_headers = _auth(client, 93004)
    with get_session_context() as db:
        coach_user = db.query(User).filter(User.telegram_user_id == 93003).one()
        client_user = db.query(User).filter(User.telegram_user_id == 93004).one()
        db.add(
            CoachClient(
                coach_user_id=coach_user.id,
                client_user_id=client_user.id,
                status="active",
                accepted_at=now_msk_naive(),
            )
        )
        db.commit()

    start = today_msk() + timedelta(days=1)
    program_id, _exercises = _assigned_program(
        client,
        coach_headers,
        start_date=start,
        duration_weeks=2,
        mode="coach",
        target_telegram_user_id=93004,
    )
    trainer_history = client.get(
        f"/api/v1/programs/assigned/{program_id}/revisions", headers=coach_headers
    )
    assert trainer_history.status_code == 200, trainer_history.text
    assert trainer_history.json()[0]["actor_role"] == "trainer"

    created = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=coach_headers,
        json={
            "expected_revision_number": 1,
            "title": "Блок тренера",
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=6)).isoformat(),
            "purpose": "Проверить отзыв доступа",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["current_revision_number"] == 2

    detached = client.delete("/api/v1/me/trainer", headers=client_headers)
    assert detached.status_code == 204

    revoked_read = client.get(
        f"/api/v1/programs/assigned/{program_id}/revisions", headers=coach_headers
    )
    assert revoked_read.status_code == 404
    revoked_write = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=coach_headers,
        json={
            "expected_revision_number": 2,
            "title": "После отзыва",
            "start_date": (start + timedelta(days=7)).isoformat(),
            "end_date": (start + timedelta(days=7)).isoformat(),
            "purpose": "Не должно сохраниться",
        },
    )
    assert revoked_write.status_code == 404

    owner_history = client.get(
        f"/api/v1/programs/assigned/{program_id}/revisions", headers=client_headers
    )
    assert owner_history.status_code == 200
    assert [row["revision_number"] for row in owner_history.json()] == [2, 1]
    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        assert program.current_revision_number == 2
        assert db.query(ProgramRevision).filter_by(user_program_id=program_id).count() == 2


def test_program_revisions_and_blocks_are_exported_and_deleted_with_account(client):
    headers = _auth(client, 93005)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    start = today_msk() + timedelta(days=1)
    program_id, _exercises = _assigned_program(
        client,
        headers,
        start_date=start,
        duration_weeks=2,
    )
    created = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "title": "Экспортируемый блок",
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=6)).isoformat(),
            "purpose": "Сохранить контекст программы",
        },
    )
    assert created.status_code == 201, created.text
    restarted = client.post(
        f"/api/v1/programs/assigned/{program_id}/lifecycle",
        headers=headers,
        json={
            "expected_revision_number": created.json()["current_revision_number"],
            "action": "restart",
            "reason": "Начать следующий цикл",
        },
    )
    assert restarted.status_code == 200, restarted.text
    new_program_id = restarted.json()["new_program_id"]
    assert new_program_id is not None

    exported = client.get("/api/v1/me/export", headers=headers)
    assert exported.status_code == 200, exported.text
    program_export = next(row for row in exported.json()["programs"] if row["id"] == program_id)
    new_program_export = next(
        row for row in exported.json()["programs"] if row["id"] == new_program_id
    )
    assert program_export["current_revision_number"] == 3
    assert [row["revision_number"] for row in program_export["revisions"]] == [1, 2, 3]
    assert program_export["training_blocks"][0]["title"] == "Экспортируемый блок"
    assert new_program_export["restarted_from_program_id"] == program_id
    assert new_program_export["training_blocks"][0]["title"] == "Экспортируемый блок"

    deleted = client.request(
        "DELETE",
        "/api/v1/me/account",
        headers=headers,
        json={"confirmation": "DELETE"},
    )
    assert deleted.status_code == 204, deleted.text
    with get_session_context() as db:
        assert db.query(User).filter(User.id == user_id).first() is None
        assert db.query(UserProgram).filter(UserProgram.id == program_id).first() is None
        assert db.query(UserProgram).filter(UserProgram.id == new_program_id).first() is None
        assert (
            db.query(ProgramRevision).filter(ProgramRevision.user_program_id == program_id).count()
            == 0
        )
        assert (
            db.query(ProgramRevision)
            .filter(ProgramRevision.user_program_id == new_program_id)
            .count()
            == 0
        )
        assert (
            db.query(TrainingBlock).filter(TrainingBlock.user_program_id == program_id).count() == 0
        )
        assert (
            db.query(TrainingBlock).filter(TrainingBlock.user_program_id == new_program_id).count()
            == 0
        )


def test_coach_clones_template_without_losing_periodization_or_source_provenance(client):
    coach_headers = _auth(client, 93041, is_coach=True)
    coach_id = client.get("/api/v1/me", headers=coach_headers).json()["id"]
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=coach_headers).json()
        if item["metric_type"] == "strength"
    ]
    plan = {
        "version": 1,
        "metric_type": "strength",
        "segments": [
            {
                "position": 1,
                "role": "working",
                "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
                "load_target": {"kind": "user_selected"},
            }
        ],
    }
    created = client.post(
        "/api/v1/programs/templates",
        headers=coach_headers,
        json={
            "title": "Источник с периодизацией",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": False,
            "days": [
                {
                    "title": "Силовая",
                    "exercises": [
                        {
                            "exercise_id": exercises[0]["id"],
                            "prescribed_sets": 3,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                            "notes": "Сохраняем заметку",
                            "prescription": plan,
                            "superset_group": 2,
                            "superset_order": 1,
                            "group_id": 2,
                            "group_kind": "superset",
                            "group_order": 1,
                        },
                        {
                            "exercise_id": exercises[1]["id"],
                            "prescribed_sets": 3,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                            "prescription": plan,
                            "superset_group": 2,
                            "superset_order": 2,
                            "group_id": 2,
                            "group_kind": "superset",
                            "group_order": 2,
                        },
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    source_id = created.json()["template"]["id"]
    with get_session_context() as db:
        source_template = db.query(ProgramTemplate).filter_by(id=source_id).one()
        source_template.default_duration_weeks = 3
        source_template.provenance_type = "SOURCE_ADAPTATION"
        source_template.provenance = {"source": "import-42", "reviewed_by": "trainer"}
        source_template.program_metadata = {"source_format": "stage0", "cycle": "strength"}
        for exercise in source_template.days[0].exercises:
            for week_number, sets in enumerate((3, 4, 5), start=1):
                db.add(
                    ProgramTemplateExerciseWeekPrescription(
                        template_exercise_id=exercise.id,
                        exercise_id=exercise.exercise_id,
                        week_number=week_number,
                        prescribed_sets=sets,
                        prescribed_reps="8-10",
                        prescribed_duration_minutes=None,
                        rest_seconds=90,
                        prescription=plan,
                    )
                )
        db.commit()

    source = client.get(f"/api/v1/programs/templates/{source_id}", headers=coach_headers)
    assert source.status_code == 200, source.text
    cloned = client.post(
        f"/api/v1/programs/templates/{source_id}/clone",
        headers=coach_headers,
    )
    assert cloned.status_code == 201, cloned.text
    result = cloned.json()

    assert result["title"] == "Источник с периодизацией (копия)"
    assert result["default_duration_weeks"] == 3
    assert result["is_public"] is False
    assert result["is_active_for_current_user"] is False
    assert result["assigned_program_id"] is None
    assert result["provenance_type"] == "SOURCE_ADAPTATION"
    assert result["provenance"] == {
        "cloned_from_template_id": source_id,
        "cloned_by_user_id": coach_id,
        "source_provenance_type": "SOURCE_ADAPTATION",
        "source_provenance": {"source": "import-42", "reviewed_by": "trainer"},
    }
    assert result["program_metadata"] == {"source_format": "stage0", "cycle": "strength"}
    for source_exercise, clone_exercise in zip(
        source.json()["days"][0]["exercises"],
        result["days"][0]["exercises"],
        strict=True,
    ):
        for field in (
            "exercise_id",
            "prescribed_sets",
            "prescribed_reps",
            "prescribed_duration_minutes",
            "rest_seconds",
            "notes",
            "superset_group",
            "superset_order",
            "prescription",
            "group_id",
            "group_kind",
            "group_order",
            "weekly_prescriptions",
        ):
            assert clone_exercise[field] == source_exercise[field]

    non_coach_headers = _auth(client, 93042)
    denied = client.post(
        f"/api/v1/programs/templates/{source_id}/clone",
        headers=non_coach_headers,
    )
    assert denied.status_code == 403
    with get_session_context() as db:
        clone_id = result["id"]
        clone_template = db.query(ProgramTemplate).filter_by(id=clone_id).one()
        assert clone_template.owner_user_id == coach_id
        assert clone_template.created_by_user_id == coach_id
        assert db.query(UserProgram.id).filter(UserProgram.template_id == clone_id).count() == 0
        event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "coach.program_template_cloned",
                AuditEvent.resource_id == str(clone_id),
            )
            .one()
        )
        assert event.actor_user_id == coach_id
        assert event.details == {"source_template_id": source_id}
