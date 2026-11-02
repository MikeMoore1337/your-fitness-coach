from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from test_program_cycle_domain import assigned_cycle

from fitminiapp_api.api.v1 import workouts as workout_routes
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserProgram, UserWorkout, UserWorkoutSet
from fitminiapp_api.services import program_versioning, programs

TODAY = date(2026, 10, 5)


@pytest.fixture
def calendar(monkeypatch):
    from fitminiapp_api.services import period_bounds, progress, session_rotation, workout_recovery

    current = [TODAY]
    monkeypatch.setattr(programs, "today_for_user", lambda _user: current[0])
    monkeypatch.setattr(program_versioning, "today_for_user", lambda _user: current[0])
    monkeypatch.setattr(workout_routes, "recovery_today_for_user", lambda _user: current[0])
    monkeypatch.setattr(session_rotation, "today_for_user", lambda _user: current[0])
    monkeypatch.setattr(progress, "today_for_user", lambda _user: current[0])
    monkeypatch.setattr(period_bounds, "today_for_user", lambda _user: current[0])
    monkeypatch.setattr(workout_recovery, "_recovery_today", lambda _user: current[0])
    return current


def _enable(client, headers, program_id, first_day=1):
    url = f"/api/v1/programs/assigned/{program_id}/session-rotation"
    settings = client.get(url, headers=headers)
    assert settings.status_code == 200, settings.text
    assert settings.json()["mode"] == "calendar"
    body = {
        "mode": "rotation",
        "first_day_number": first_day,
        "expected_revision_number": settings.json()["revision_number"],
    }
    preview = client.post(f"{url}/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    applied = client.post(
        f"{url}/apply",
        headers=headers,
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert applied.status_code == 200, applied.text


def _state(client, headers):
    response = client.get("/api/v1/workouts/session-rotation", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _start(client, headers, state, *, mutation_id=None):
    body = {
        "expected_cursor": state["cursor"],
        "expected_day_number": state["current"]["day_number"],
        "mutation_id": mutation_id or str(uuid4()),
        "plan_week_number": 1,
    }
    response = client.post("/api/v1/workouts/session-rotation/start", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def _finish(client, headers, workout):
    first_set = workout["exercises"][0]["sets"][0]
    updated = client.patch(
        f"/api/v1/workouts/sets/{first_set['id']}",
        headers=headers,
        json={"actual_reps": 8, "actual_weight": 20, "is_completed": True},
    )
    assert updated.status_code == 200, updated.text
    finished = client.post(
        f"/api/v1/workouts/{workout['id']}/finish",
        headers=headers,
        json={"confirm_incomplete": True},
    )
    assert finished.status_code == 200, finished.text


@pytest.mark.parametrize("day_count", [1, 3, 5])
def test_rotation_advances_only_after_completion_and_wraps(client, calendar, day_count):
    headers, program_id, _, _ = assigned_cycle(client, k=1, n=16, days=day_count)
    _enable(client, headers, program_id)
    with get_session_context() as db:
        before = db.query(UserWorkout).filter_by(user_program_id=program_id).count()
    state = _state(client, headers)
    assert state["current"]["day_number"] == 1
    assert state["next"]["day_number"] == (2 if day_count > 1 else 1)
    assert _state(client, headers)["cursor"] == state["cursor"]
    with get_session_context() as db:
        assert db.query(UserWorkout).filter_by(user_program_id=program_id).count() == before

    for day in range(1, day_count + 1):
        state = _state(client, headers)
        assert state["current"]["day_number"] == day
        workout, body = _start(client, headers, state)
        replay = client.post("/api/v1/workouts/session-rotation/start", headers=headers, json=body)
        assert replay.status_code == 200, replay.text
        assert replay.json()["id"] == workout["id"]
        assert _state(client, headers)["current"]["workout_id"] == workout["id"]
        _finish(client, headers, workout)
        if day == 1:
            calendar[0] += timedelta(days=7)
    assert _state(client, headers)["current"]["day_number"] == 1
    with get_session_context() as db:
        finished = (
            db.query(UserWorkout).filter_by(user_program_id=program_id, status="completed").all()
        )
        assert len(finished) == day_count
        assert (
            sum(
                1
                for workout in finished
                for exercise in workout.exercises
                for s in exercise.sets
                if s.is_completed
            )
            == day_count
        )
        assert db.query(UserWorkoutSet).filter_by(actual_reps=8).count() == day_count
        assert db.get(UserProgram, program_id).schedule_mode == "rotation"


def test_eight_day_program_wraps_without_a_weekly_cycle(client, calendar):
    from test_program_week_cycle import _auth, _payload

    headers = _auth(client, 916208)
    payload = _payload(client, headers)
    payload["days"] = [{**payload["days"][0], "title": f"День {index}"} for index in range(1, 9)]
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 2},
    )
    assert assigned.status_code == 200, assigned.text
    _enable(client, headers, assigned.json()["user_program_id"])
    for day in range(1, 9):
        state = _state(client, headers)
        assert state["current"]["day_number"] == day
        workout, _ = _start(client, headers, state)
        _finish(client, headers, workout)
    assert _state(client, headers)["current"]["day_number"] == 1


def test_coach_permissions_and_owner_are_preserved(client, calendar):
    from test_program_week_cycle import _auth

    from fitminiapp_api.models.user import CoachClient, User

    headers, program_id, _, _ = assigned_cycle(client, k=1, n=16, days=3)
    other = _auth(client, 916202)
    trainer = _auth(client, 916203, is_coach=True)
    url = f"/api/v1/programs/assigned/{program_id}/session-rotation"
    assert client.get(url, headers=other).status_code in {403, 404}
    with get_session_context() as db:
        coach = db.query(User).filter_by(telegram_user_id=916203).one()
        program = db.get(UserProgram, program_id)
        program.assigned_by_user_id = coach.id
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=program.user_id, status="active"))
    body = {"mode": "rotation", "expected_revision_number": 1, "first_day_number": 1}
    preview = client.post(f"{url}/preview", headers=trainer, json=body)
    assert preview.status_code == 200, preview.text
    apply_body = {**body, "preview_token": preview.json()["preview_token"]}
    assert client.post(f"{url}/apply", headers=headers, json=apply_body).status_code == 403
    applied = client.post(f"{url}/apply", headers=trainer, json=apply_body)
    assert applied.status_code == 200, applied.text
    coach_programs = client.get("/api/v1/coach/assigned-programs", headers=trainer)
    assert coach_programs.status_code == 200, coach_programs.text
    summary = next(item for item in coach_programs.json() if item["id"] == program_id)
    assert summary["workouts_planned"] == 0 and summary["next_workout_date"] is None
    workout, _ = _start(client, headers, _state(client, headers))
    assert workout["status"] == "in_progress"
    assert _state(client, other)["mode"] == "calendar"


def test_settings_and_extension_conflicts_return_current_state(client, calendar):
    from test_program_week_cycle import _auth

    headers, program_id, _, _ = assigned_cycle(client, k=1, n=2, days=3)
    _enable(client, headers, program_id)
    state = _state(client, headers)
    url = f"/api/v1/programs/assigned/{program_id}/session-rotation"
    stale_settings = {
        "mode": "rotation",
        "expected_revision_number": state["revision_number"] - 1,
        "first_day_number": 1,
    }
    preview = client.post(f"{url}/preview", headers=headers, json=stale_settings)
    assert preview.status_code == 409
    assert preview.json()["detail"]["current"]["cursor"] == state["cursor"]
    calendar[0] += timedelta(days=15)
    expired = _state(client, headers)
    extension = {
        "expected_revision_number": expired["revision_number"],
        "expected_cursor": "0" * 64,
        "duration_weeks": 4,
        "mutation_id": str(uuid4()),
    }
    conflict = client.post(f"{url}/extend", headers=headers, json=extension)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["current"]["cursor"] == expired["cursor"]
    stranger = _auth(client, 916202)
    assert client.post(f"{url}/extend", headers=stranger, json=extension).status_code == 404


def test_expired_coach_program_requires_coach_extension(client, calendar):
    from test_program_week_cycle import _auth

    from fitminiapp_api.models.user import CoachClient, User

    headers, program_id, _, _ = assigned_cycle(client, k=1, n=2, days=3)
    trainer = _auth(client, 916203, is_coach=True)
    with get_session_context() as db:
        coach = db.query(User).filter_by(telegram_user_id=916203).one()
        program = db.get(UserProgram, program_id)
        program.assigned_by_user_id = coach.id
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=program.user_id, status="active"))
    _enable(client, trainer, program_id)
    calendar[0] += timedelta(days=15)
    expired = _state(client, headers)
    assert expired["status"] == "expired" and expired["can_extend"] is False
    body = {
        "expected_revision_number": expired["revision_number"],
        "expected_cursor": expired["cursor"],
        "duration_weeks": 4,
        "mutation_id": str(uuid4()),
    }
    url = f"/api/v1/programs/assigned/{program_id}/session-rotation/extend"
    assert client.post(url, headers=headers, json=body).status_code == 403
    response = client.post(url, headers=trainer, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["current"]["day_number"] == expired["current"]["day_number"]


def test_missing_template_days_require_preview_and_keep_confirmed_plan(client, calendar):
    from test_program_week_cycle import _auth, _payload

    from fitminiapp_api.models.program import ProgramTemplate

    headers = _auth(client, 916209)
    payload = _payload(client, headers)
    payload["days"] = [{**payload["days"][0], "title": f"День {index}"} for index in range(1, 9)]
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    with get_session_context() as db:
        db.get(ProgramTemplate, template_id).program_metadata = {"days_per_week": 2}
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 1},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    url = f"/api/v1/programs/assigned/{program_id}/session-rotation"
    settings = client.get(url, headers=headers).json()
    assert len(settings["days"]) == 8
    assert sum(day["from_template"] for day in settings["days"]) == 6
    body = {"mode": "rotation", "expected_revision_number": 1, "first_day_number": 3}
    preview = client.post(f"{url}/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert len(preview.json()["template_plans"]) == 6
    applied = client.post(
        f"{url}/apply",
        headers=headers,
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert applied.status_code == 200, applied.text
    with get_session_context() as db:
        db.get(ProgramTemplate, template_id).days[2].exercises[0].prescribed_reps = "99"
    plan = client.get(
        "/api/v1/workouts/session-rotation/plan?day_number=3&week_number=1", headers=headers
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["exercises"][0]["prescribed_reps"] == "8"
    workout, _ = _start(client, headers, _state(client, headers))
    assert workout["day_number"] == 3
    _finish(client, headers, workout)
    assert _state(client, headers)["current"]["day_number"] == 4


@pytest.mark.parametrize("length, expected", [(1, 200), (3, 422)])
def test_ambiguous_week_requires_an_explicit_selection(client, calendar, length, expected):
    headers, program_id, _, _ = assigned_cycle(client, k=length, n=16, days=2)
    _enable(client, headers, program_id)
    state = _state(client, headers)
    assert state["default_plan_week"] == (1 if length == 1 else None)
    body = {
        "expected_cursor": state["cursor"],
        "expected_day_number": 1,
        "mutation_id": str(uuid4()),
    }
    response = client.post("/api/v1/workouts/session-rotation/start", headers=headers, json=body)
    assert response.status_code == expected, response.text


def test_unperiodized_program_uses_saved_plan_without_copying_completed_edits(client, calendar):
    from test_program_week_cycle import _auth, _payload

    headers = _auth(client, 916210)
    payload = _payload(client, headers)
    payload["days"] = [{**payload["days"][0], "title": f"День {index}"} for index in range(1, 4)]
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 2},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    with get_session_context() as db:
        source = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=1, day_number=1)
            .one()
        )
        source.status = "completed"
        source.exercises[0].prescribed_reps = "99"
        source.exercises[0].sets[0].is_completed = True
        source.exercises[0].sets[0].actual_reps = 99
    _enable(client, headers, program_id)
    state = _state(client, headers)
    assert state["default_plan_week"] == 1
    body = {
        "expected_cursor": state["cursor"],
        "expected_day_number": 1,
        "mutation_id": str(uuid4()),
    }
    started = client.post("/api/v1/workouts/session-rotation/start", headers=headers, json=body)
    assert started.status_code == 200, started.text
    assert started.json()["exercises"][0]["prescribed_reps"] == "8"
    assert all(not item["is_completed"] for item in started.json()["exercises"][0]["sets"])


def test_switch_cancels_only_workout_reminders_and_scheduler_does_not_recreate_them(
    client, calendar, monkeypatch
):
    from datetime import datetime, time

    from fitminiapp_api.models.notification import Notification, NotificationSetting
    from fitminiapp_api.services import notifications

    headers, program_id, _, _ = assigned_cycle(client, k=1, n=16, days=3)
    monkeypatch.setattr(
        notifications, "now_for_user_naive", lambda _user: datetime.combine(calendar[0], time(8))
    )
    with get_session_context() as db:
        owner_id = db.get(UserProgram, program_id).user_id
        setting = db.query(NotificationSetting).filter_by(user_id=owner_id).one()
        setting.workout_reminders_enabled = True
        notifications.sync_workout_reminders(db)
        pending = (
            db.query(Notification)
            .filter_by(user_id=owner_id, category="workout_reminder", status="queued")
            .all()
        )
        assert pending
        pending_ids = [item.id for item in pending]
        personal = Notification(
            user_id=owner_id,
            category="meal_reminder",
            title="Личное напоминание",
            body="Тест",
            scheduled_for=datetime(2026, 10, 6, 12),
            scheduled_for_utc=datetime(2026, 10, 6, 12),
            status="queued",
            dedupe_key="meal:rotation-test",
        )
        db.add(personal)
        db.flush()
        personal_id = personal.id
    url = f"/api/v1/programs/assigned/{program_id}/session-rotation"
    body = {"mode": "rotation", "expected_revision_number": 1, "first_day_number": 1}
    preview = client.post(f"{url}/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["future_reminders"] == len(pending_ids)
    applied = client.post(
        f"{url}/apply",
        headers=headers,
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert applied.status_code == 200, applied.text
    with get_session_context() as db:
        assert all(
            db.get(Notification, notification_id).status == "cancelled"
            for notification_id in pending_ids
        )
        assert db.get(Notification, personal_id).status == "queued"
        notifications.sync_workout_reminders(db)
        assert (
            not db.query(Notification)
            .filter_by(user_id=owner_id, category="workout_reminder", status="queued")
            .count()
        )
        assert db.get(Notification, personal_id).status == "queued"


def test_cancel_restore_skip_and_extra_preserve_the_queue_and_facts(client, calendar):
    headers, program_id, _, _ = assigned_cycle(client, k=1, n=16, days=3)
    _enable(client, headers, program_id)
    workout, _ = _start(client, headers, _state(client, headers))
    workout_set = workout["exercises"][0]["sets"][0]
    response = client.patch(
        f"/api/v1/workouts/sets/{workout_set['id']}",
        headers=headers,
        json={"actual_reps": 7, "actual_weight": 42, "is_completed": True},
    )
    assert response.status_code == 200, response.text
    active = _state(client, headers)
    body = {
        "workout_id": workout["id"],
        "expected_cursor": active["cursor"],
        "mutation_id": str(uuid4()),
    }
    canceled = client.post("/api/v1/workouts/session-rotation/cancel", headers=headers, json=body)
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["status"] == "cancelled"
    assert (
        client.post(
            "/api/v1/workouts/session-rotation/cancel", headers=headers, json=body
        ).status_code
        == 200
    )
    restore_body = {
        **body,
        "expected_cursor": canceled.json()["cursor"],
        "mutation_id": str(uuid4()),
    }
    restored = client.post(
        "/api/v1/workouts/session-rotation/restore", headers=headers, json=restore_body
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["current"]["workout_id"] == workout["id"]
    delayed_cancel = client.post(
        "/api/v1/workouts/session-rotation/cancel", headers=headers, json=body
    )
    assert delayed_cancel.status_code == 409
    assert _state(client, headers)["status"] == "in_progress"
    with get_session_context() as db:
        saved = db.get(UserWorkoutSet, workout_set["id"])
        assert saved.is_completed and saved.actual_reps == 7 and saved.actual_weight == 42
    _finish(client, headers, workout)
    state = _state(client, headers)
    assert state["current"]["day_number"] == 2
    extra_body = {
        "expected_cursor": state["cursor"],
        "expected_day_number": 3,
        "mutation_id": str(uuid4()),
        "plan_week_number": 1,
        "out_of_order": True,
    }
    extra = client.post("/api/v1/workouts/session-rotation/start", headers=headers, json=extra_body)
    assert extra.status_code == 200, extra.text
    _finish(client, headers, extra.json())
    state = _state(client, headers)
    assert state["current"]["day_number"] == 2
    skip_body = {
        "expected_cursor": state["cursor"],
        "expected_day_number": 2,
        "mutation_id": str(uuid4()),
        "plan_week_number": 1,
    }
    skipped = client.post("/api/v1/workouts/session-rotation/skip", headers=headers, json=skip_body)
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["current"]["day_number"] == 3
    undo = {
        "expected_cursor": skipped.json()["cursor"],
        "workout_id": skipped.json()["undo_skip_workout_id"],
        "mutation_id": str(uuid4()),
    }
    undone = client.post("/api/v1/workouts/session-rotation/undo-skip", headers=headers, json=undo)
    assert undone.status_code == 200, undone.text
    assert undone.json()["current"]["day_number"] == 2
    stale_skip = client.post(
        "/api/v1/workouts/session-rotation/skip",
        headers=headers,
        json={**skip_body, "mutation_id": str(uuid4())},
    )
    assert stale_skip.status_code == 409
    assert _state(client, headers)["current"]["day_number"] == 2
    assert (
        client.post(
            "/api/v1/workouts/session-rotation/undo-skip", headers=headers, json=undo
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/workouts/session-rotation/start", headers=headers, json=extra_body
        ).json()["id"]
        == extra.json()["id"]
    )
    with get_session_context() as db:
        assert db.get(UserProgram, program_id).schedule_mode == "rotation"


def test_expired_program_extension_keeps_the_next_day(client, calendar):
    headers, program_id, _, _ = assigned_cycle(client, k=1, n=2, days=3)
    _enable(client, headers, program_id)
    workout, _ = _start(client, headers, _state(client, headers))
    _finish(client, headers, workout)
    calendar[0] += timedelta(days=21)
    expired = _state(client, headers)
    assert expired["status"] == "expired"
    assert expired["current"]["day_number"] == 2
    assert expired["min_extension_weeks"] == 4
    lifecycle = client.get(f"/api/v1/programs/assigned/{program_id}/lifecycle", headers=headers)
    assert lifecycle.status_code == 200, lifecycle.text
    assert lifecycle.json()["rotation_status"] == "expired"
    assert lifecycle.json()["rotation_current_title"] == expired["current"]["title"]
    assert lifecycle.json()["next_workout"] is None
    body = {
        "expected_revision_number": expired["revision_number"],
        "expected_cursor": expired["cursor"],
        "duration_weeks": 5,
        "mutation_id": str(uuid4()),
    }
    url = f"/api/v1/programs/assigned/{program_id}/session-rotation/extend"
    extended = client.post(url, headers=headers, json=body)
    assert extended.status_code == 200, extended.text
    assert extended.json()["status"] == "ready"
    assert extended.json()["current"]["day_number"] == 2
    assert (
        client.post(url, headers=headers, json=body).json()["cursor"] == extended.json()["cursor"]
    )


def test_days_off_do_not_count_as_missed_in_progress_summary(client, calendar):
    headers, program_id, _, _ = assigned_cycle(client, k=1, n=16, days=3)
    _enable(client, headers, program_id)
    calendar[0] += timedelta(days=7)
    response = client.get("/api/v1/workouts/progress/summary?period_days=30", headers=headers)
    assert response.status_code == 200, response.text
    training = response.json()["training"]
    assert training["planned_workouts"] == 0
    assert training["skipped_workouts"] == 0
    assert training["next_workout"] is None
    workout, _ = _start(client, headers, _state(client, headers))
    _finish(client, headers, workout)
    response = client.get("/api/v1/workouts/progress/summary?period_days=30", headers=headers)
    assert response.status_code == 200, response.text
    training = response.json()["training"]
    assert training["planned_workouts"] == 1
    assert training["completed_workouts"] == 1
    assert training["next_workout"] is None


def test_return_to_calendar_uses_chosen_date_without_inventing_missed_workouts(client, calendar):
    headers, program_id, _, _ = assigned_cycle(client, k=1, n=16, days=3)
    _enable(client, headers, program_id)
    calendar[0] += timedelta(days=7)
    url = f"/api/v1/programs/assigned/{program_id}/session-rotation"
    settings = client.get(url, headers=headers).json()
    chosen = settings["calendar_options"][2]
    body = {
        "mode": "calendar",
        "expected_revision_number": settings["revision_number"],
        "resume_calendar_week": chosen["week_number"],
        "resume_calendar_day": chosen["day_number"],
    }
    preview = client.post(f"{url}/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["calendar_resume"] == chosen
    applied = client.post(
        f"{url}/apply",
        headers=headers,
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert applied.status_code == 200, applied.text
    with get_session_context() as db:
        stale = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, scheduled_date=calendar[0], rotation_epoch=None)
            .first()
        )
        assert stale is not None
        stale_id = stale.id
    assert client.post(f"/api/v1/workouts/{stale_id}/start", headers=headers).status_code == 409
    assert client.get("/api/v1/workouts/today", headers=headers).status_code == 404
    schedule = client.get(
        f"/api/v1/workouts/schedule?date_from={TODAY}&date_to={TODAY + timedelta(days=20)}",
        headers=headers,
    )
    assert schedule.status_code == 200, schedule.text
    assert all(item["scheduled_date"] >= chosen["scheduled_date"] for item in schedule.json())
    assert client.get("/api/v1/workouts/recovery", headers=headers).json()["status"] == "clear"
    training = client.get(
        "/api/v1/workouts/progress/summary?period_days=30", headers=headers
    ).json()["training"]
    assert training["planned_workouts"] == 0
    assert training["next_workout"]["scheduled_date"] == chosen["scheduled_date"]
    calendar[0] = date.fromisoformat(chosen["scheduled_date"])
    current = client.get("/api/v1/workouts/today", headers=headers)
    assert current.status_code == 200, current.text
    assert current.json()["day_number"] == chosen["day_number"]


def test_reenable_rotation_cancels_a_future_return_to_calendar(client, calendar):
    from fitminiapp_api.services.schedule_modes import calendar_active_on, mode_changes

    headers, program_id, _, _ = assigned_cycle(client, k=1, n=16, days=3)
    _enable(client, headers, program_id)
    calendar[0] += timedelta(days=7)
    url = f"/api/v1/programs/assigned/{program_id}/session-rotation"
    settings = client.get(url, headers=headers).json()
    chosen = next(
        option
        for option in settings["calendar_options"]
        if date.fromisoformat(option["scheduled_date"]) > calendar[0]
    )
    body = {
        "mode": "calendar",
        "expected_revision_number": settings["revision_number"],
        "resume_calendar_week": chosen["week_number"],
        "resume_calendar_day": chosen["day_number"],
    }
    preview = client.post(f"{url}/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    applied = client.post(
        f"{url}/apply",
        headers=headers,
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert applied.status_code == 200, applied.text
    _enable(client, headers, program_id)
    with get_session_context() as db:
        changes = mode_changes(db, {program_id})[program_id]
        assert not calendar_active_on(changes, date.fromisoformat(chosen["scheduled_date"]))
    assert _state(client, headers)["status"] == "ready"


def test_two_clients_cannot_start_same_position(client, calendar):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    headers, program_id, _, _ = assigned_cycle(client, k=1, n=16, days=3)
    _enable(client, headers, program_id)
    state = _state(client, headers)
    barrier = Barrier(2)

    def start(_):
        body = {
            "expected_cursor": state["cursor"],
            "expected_day_number": 1,
            "mutation_id": str(uuid4()),
            "plan_week_number": 1,
        }
        barrier.wait(timeout=10)
        return client.post("/api/v1/workouts/session-rotation/start", headers=headers, json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(start, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    with get_session_context() as db:
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, status="in_progress")
            .count()
            == 1
        )


def test_cycle_edit_preserves_rotation_facts_and_requires_review(client, calendar):
    headers, program_id, _, _ = assigned_cycle(client, k=1, n=16, days=1)
    _enable(client, headers, program_id)
    for _ in range(2):
        workout, _ = _start(client, headers, _state(client, headers))
        _finish(client, headers, workout)
    before = _state(client, headers)
    payload = {
        "expected_revision_number": before["revision_number"],
        "effective_from_week": 2,
        "duration_weeks": 20,
    }
    response = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle", headers=headers, json=payload
    )
    assert response.status_code == 200, response.text
    after = _state(client, headers)
    assert after["status"] == "review_required"
    assert after["current"]["day_number"] == before["current"]["day_number"]
    stale = {
        "expected_cursor": before["cursor"],
        "expected_day_number": 1,
        "mutation_id": str(uuid4()),
        "plan_week_number": 1,
    }
    conflict = client.post("/api/v1/workouts/session-rotation/start", headers=headers, json=stale)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["current"]["cursor"] == after["cursor"]
    with get_session_context() as db:
        facts = db.query(UserWorkoutSet).filter_by(actual_reps=8, is_completed=True).all()
        assert len(facts) == 2
        assert all(item.actual_weight == 20 for item in facts)
