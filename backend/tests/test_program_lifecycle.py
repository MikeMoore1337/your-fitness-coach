from datetime import timedelta

from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserProgram, UserWorkout
from fitminiapp_api.models.user import User


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_template(client, headers, *, sets: int = 1, assigned: bool = False) -> int:
    exercises = client.get("/api/v1/programs/exercises", headers=headers).json()
    exercise_id = next(item["id"] for item in exercises if item["metric_type"] == "strength")
    response = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Жизненный цикл",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": assigned,
            "days": [
                {
                    "title": "Силовая A",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": sets,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                            "notes": "Контролировать негативную фазу",
                        }
                    ],
                },
                {
                    "title": "Силовая B",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": sets,
                            "prescribed_reps": "10",
                            "rest_seconds": 60,
                        }
                    ],
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["template"]["id"]


def test_recurring_schedule_snapshots_notes_and_requires_replacement_confirmation(client):
    headers = _auth(client, 91001)
    template_id = _create_template(client, headers)
    start_date = today_msk() + timedelta(days=1)
    second_date = start_date + timedelta(days=2)
    next_week_start = start_date + timedelta(days=7)
    next_week_second = start_date + timedelta(days=9)

    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={
            "start_date": start_date.isoformat(),
            "duration_weeks": 2,
            "schedule_weekdays": [start_date.weekday(), second_date.weekday()],
        },
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["workouts_created"] == 4
    assert assigned.json()["duration_weeks"] == 2

    template = next(
        item
        for item in client.get("/api/v1/programs/templates/mine", headers=headers).json()
        if item["id"] == template_id
    )
    assert template["is_active_for_current_user"] is True
    assert template["assigned_program_id"] == assigned.json()["user_program_id"]
    assert template["assigned_program_status"] == "scheduled"
    assert template["assigned_program_start_date"] == start_date.isoformat()
    assert template["assigned_program_duration_weeks"] == 2
    assert template["current_revision_number"] == 1

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 91001).one()
        program = db.query(UserProgram).filter(UserProgram.user_id == user.id).one()
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program.id)
            .order_by(UserWorkout.scheduled_date.asc())
            .all()
        )
        assert [workout.scheduled_date.isoformat() for workout in workouts] == [
            start_date.isoformat(),
            second_date.isoformat(),
            next_week_start.isoformat(),
            next_week_second.isoformat(),
        ]
        assert [workout.week_number for workout in workouts] == [1, 1, 2, 2]
        assert workouts[0].exercises[0].notes == "Контролировать негативную фазу"
        first_workout_id = workouts[0].id
        second_workout_id = workouts[1].id

    schedule = client.get(
        "/api/v1/workouts/schedule"
        f"?date_from={start_date.isoformat()}&date_to={next_week_second.isoformat()}",
        headers=headers,
    )
    assert schedule.status_code == 200
    assert len(schedule.json()) == 4
    rescheduled = client.patch(
        f"/api/v1/workouts/{first_workout_id}/schedule",
        headers=headers,
        json={"scheduled_date": (start_date + timedelta(days=1)).isoformat()},
    )
    assert rescheduled.status_code == 200
    skipped = client.post(f"/api/v1/workouts/{second_workout_id}/skip", headers=headers)
    assert skipped.status_code == 200
    assert skipped.json()["status"] == "skipped"

    refused = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"start_date": (start_date + timedelta(days=30)).isoformat()},
    )
    assert refused.status_code == 409

    replaced = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={
            "start_date": (start_date + timedelta(days=30)).isoformat(),
            "replace_active": True,
        },
    )
    assert replaced.status_code == 200, replaced.text


def test_finish_requires_explicit_incomplete_confirmation_and_completes_program(client):
    headers = _auth(client, 91002)
    exercises = client.get("/api/v1/programs/exercises", headers=headers).json()
    exercise_id = next(item["id"] for item in exercises if item["metric_type"] == "strength")
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Сегодня",
            "goal": "maintenance",
            "level": "beginner",
            "mode": "self",
            "assign_after_create": True,
            "start_date": today_msk().isoformat(),
            "days": [
                {
                    "title": "Сегодня",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": 2,
                            "prescribed_reps": "8",
                            "rest_seconds": 60,
                            "notes": "Без боли",
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    today = client.get("/api/v1/workouts/today", headers=headers)
    assert today.status_code == 200
    workout = today.json()
    assert workout["exercises"][0]["notes"] == "Без боли"

    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).status_code == 200
    )
    first_set = workout["exercises"][0]["sets"][0]
    updated = client.patch(
        f"/api/v1/workouts/sets/{first_set['id']}",
        headers=headers,
        json={"actual_reps": 8, "actual_weight": 20, "is_completed": True},
    )
    assert updated.status_code == 200

    refused = client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=headers)
    assert refused.status_code == 409
    finished = client.post(
        f"/api/v1/workouts/{workout['id']}/finish",
        headers=headers,
        json={"confirm_incomplete": True},
    )
    assert finished.status_code == 200, finished.text
    with get_session_context() as db:
        completed_workout = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        completed_program = (
            db.query(UserProgram).filter(UserProgram.id == completed_workout.user_program_id).one()
        )
        terminal_timestamps = (completed_workout.completed_at, completed_program.completed_at)
    repeated_finish = client.post(
        f"/api/v1/workouts/{workout['id']}/finish",
        headers=headers,
        json={"confirm_incomplete": True},
    )
    assert repeated_finish.status_code == 200
    assert repeated_finish.json() == finished.json()
    other_headers = _auth(client, 91003)
    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=other_headers).status_code
        == 404
    )

    progress = client.get("/api/v1/workouts/progress", headers=headers)
    assert progress.status_code == 200
    assert progress.json()["workouts_completed"] == 1
    assert progress.json()["weekly_volume"][0]["volume_kg"] == 160.0
    assert progress.json()["personal_records"][0]["max_weight_kg"] == 20.0
    summary = client.get("/api/v1/workouts/history/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json() == {
        "workouts_completed": 1,
        "completed_sets": 1,
        "volume_kg": 160.0,
    }

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 91002).one()
        program = db.query(UserProgram).filter(UserProgram.user_id == user.id).one()
        completed_workout = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        assert program.status == "completed"
        assert program.is_active is False
        assert (completed_workout.completed_at, program.completed_at) == terminal_timestamps
        assert program.completed_at is not None

    history = client.get(
        f"/api/v1/programs/assigned/{created.json()['assigned_program_id']}/revisions",
        headers=headers,
    )
    assert history.status_code == 200
    assert [revision["change_kind"] for revision in history.json()] == [
        "program_lifecycle",
        "assigned",
    ]
    assert history.json()[0]["changed_fields"]["operation"] == "program_completed_from_schedule"


def test_assignment_rejects_a_start_date_in_the_past(client):
    headers = _auth(client, 91003)
    template_id = _create_template(client, headers)

    response = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"start_date": (today_msk() - timedelta(days=1)).isoformat()},
    )

    assert response.status_code == 422


def test_pause_resume_terminate_and_restart_keep_completed_history(client):
    headers = _auth(client, 91004)
    template_id = _create_template(client, headers)
    start_date = today_msk()
    second_date = start_date + timedelta(days=2)
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={
            "start_date": start_date.isoformat(),
            "duration_weeks": 2,
            "schedule_weekdays": [start_date.weekday(), second_date.weekday()],
        },
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]

    today_workout = client.get("/api/v1/workouts/today", headers=headers)
    assert today_workout.status_code == 200, today_workout.text
    assert (
        client.post(
            f"/api/v1/workouts/{today_workout.json()['id']}/start", headers=headers
        ).status_code
        == 200
    )
    first_set = today_workout.json()["exercises"][0]["sets"][0]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{first_set['id']}",
            headers=headers,
            json={"actual_reps": 8, "actual_weight": 20, "is_completed": True},
        ).status_code
        == 200
    )
    finished = client.post(f"/api/v1/workouts/{today_workout.json()['id']}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    completed_at = finished.json()["completed_at"]

    summary = client.get(f"/api/v1/programs/assigned/{program_id}/lifecycle", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["status"] == "active"
    next_workout_id = summary.json()["next_workout"]["id"]
    paused = client.post(
        f"/api/v1/programs/assigned/{program_id}/lifecycle",
        headers=headers,
        json={
            "expected_revision_number": summary.json()["current_revision_number"],
            "action": "pause",
            "reason": "Нужна неделя восстановления",
        },
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"
    paused_schedule = client.get(
        "/api/v1/workouts/schedule",
        headers=headers,
        params={
            "date_from": start_date.isoformat(),
            "date_to": (start_date + timedelta(days=20)).isoformat(),
        },
    )
    assert paused_schedule.status_code == 200
    assert paused_schedule.json() == []
    unavailable_workout = client.post(f"/api/v1/workouts/{next_workout_id}/skip", headers=headers)
    assert unavailable_workout.status_code == 409
    assert unavailable_workout.json()["detail"] == "Программа сейчас неактивна"
    resumed = client.post(
        f"/api/v1/programs/assigned/{program_id}/lifecycle",
        headers=headers,
        json={
            "expected_revision_number": paused.json()["current_revision_number"],
            "action": "resume",
            "reason": "Можно продолжить план",
        },
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "active"
    resumed_schedule = client.get(
        "/api/v1/workouts/schedule",
        headers=headers,
        params={
            "date_from": start_date.isoformat(),
            "date_to": (start_date + timedelta(days=20)).isoformat(),
        },
    )
    assert resumed_schedule.status_code == 200
    assert len(resumed_schedule.json()) == 4
    terminated = client.post(
        f"/api/v1/programs/assigned/{program_id}/lifecycle",
        headers=headers,
        json={
            "expected_revision_number": resumed.json()["current_revision_number"],
            "action": "terminate",
            "reason": "План больше не подходит",
        },
    )
    assert terminated.status_code == 200, terminated.text
    assert terminated.json()["status"] == "terminated"

    restarted = client.post(
        f"/api/v1/programs/assigned/{program_id}/lifecycle",
        headers=headers,
        json={
            "expected_revision_number": terminated.json()["current_revision_number"],
            "action": "restart",
            "reason": "Начать новый цикл",
            "restarted_from_program_id": 999999,
        },
    )
    assert restarted.status_code == 200, restarted.text
    new_program_id = restarted.json()["new_program_id"]
    assert new_program_id != program_id

    with get_session_context() as db:
        source = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        source_workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .all()
        )
        new_program = db.query(UserProgram).filter(UserProgram.id == new_program_id).one()
        new_workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == new_program_id)
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .all()
        )
        assert source.status == "terminated"
        assert source_workouts[0].status == "completed"
        assert source_workouts[0].completed_at.isoformat() == completed_at
        assert all(workout.status == "cancelled" for workout in source_workouts[1:])
        assert new_program.restarted_from_program_id == source.id
        assert new_program.user_id == source.user_id
        assert db.query(UserProgram.id).filter(
            UserProgram.id == new_program.restarted_from_program_id,
            UserProgram.user_id == new_program.user_id,
        ).one() == (source.id,)
        assert new_program.status == "scheduled"
        assert len(new_workouts) == len(source_workouts)
        assert all(workout.status == "planned" for workout in new_workouts)
        assert all(workout.scheduled_date > today_msk() for workout in new_workouts)


def test_block_advance_repeat_and_deload_extend_future_without_rewriting_history(client):
    headers = _auth(client, 91005)
    template_id = _create_template(client, headers)
    start_date = today_msk() + timedelta(days=1)
    second_date = start_date + timedelta(days=2)
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={
            "start_date": start_date.isoformat(),
            "duration_weeks": 2,
            "schedule_weekdays": [start_date.weekday(), second_date.weekday()],
        },
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    first = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "title": "Накопление",
            "start_date": start_date.isoformat(),
            "end_date": (start_date + timedelta(days=6)).isoformat(),
            "purpose": "Постепенно увеличить объём",
            "reason": "Начало цикла",
        },
    )
    assert first.status_code == 201, first.text
    second_start = start_date + timedelta(days=7)
    second = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=headers,
        json={
            "expected_revision_number": 2,
            "title": "Облегчённая неделя",
            "start_date": second_start.isoformat(),
            "end_date": (second_start + timedelta(days=6)).isoformat(),
            "purpose": "Снизить накопленную нагрузку",
            "is_deload": True,
            "reason": "Плановое восстановление",
        },
    )
    assert second.status_code == 201, second.text
    activated = client.patch(
        f"/api/v1/programs/assigned/{program_id}/blocks/{first.json()['block']['id']}",
        headers=headers,
        json={
            "expected_revision_number": 3,
            "status": "active",
            "reason": "Начать первый этап",
        },
    )
    assert activated.status_code == 200, activated.text

    with get_session_context() as db:
        original_workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .all()
        )
        for workout in original_workouts[:2]:
            workout.status = "completed"
            workout.completed_at = now_msk_naive()
        original_completed_at = original_workouts[0].completed_at
        db.commit()

    advanced = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks/{first.json()['block']['id']}/advance",
        headers=headers,
        json={
            "expected_revision_number": 4,
            "reason": "Первый этап выполнен",
        },
    )
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["block"]["id"] == second.json()["block"]["id"]
    assert advanced.json()["completed_block_id"] == first.json()["block"]["id"]

    lifecycle = client.get(f"/api/v1/programs/assigned/{program_id}/lifecycle", headers=headers)
    assert lifecycle.status_code == 200, lifecycle.text
    assert lifecycle.json()["current_block"]["is_deload"] is True
    assert lifecycle.json()["next_deload"]["id"] == second.json()["block"]["id"]

    repeated = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks/{first.json()['block']['id']}/repeat",
        headers=headers,
        json={
            "expected_revision_number": advanced.json()["current_revision_number"],
            "reason": "Повторить накопительный этап",
        },
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["duration_weeks"] == 3
    assert repeated.json()["block"]["start_date"] == (start_date + timedelta(days=14)).isoformat()
    with get_session_context() as db:
        original = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .all()
        )
        assert original[0].status == "completed"
        assert original[0].completed_at == original_completed_at
        assert (
            db.query(UserWorkout)
            .filter(
                UserWorkout.user_program_id == program_id,
                UserWorkout.week_number == 3,
            )
            .count()
            == 2
        )
