from datetime import timedelta

from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.notification import Notification
from fitminiapp_api.models.program import ProgramRevision, UserProgram, UserWorkout
from fitminiapp_api.models.user import User


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_template(client, headers, title: str) -> int:
    exercises = client.get("/api/v1/programs/exercises", headers=headers)
    assert exercises.status_code == 200
    exercise_id = next(item["id"] for item in exercises.json() if item["metric_type"] == "strength")
    response = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": title,
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": False,
            "days": [
                {
                    "title": "Силовая A",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": 1,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                        }
                    ],
                },
                {
                    "title": "Силовая B",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": 1,
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


def _assign(client, headers, template_id: int) -> int:
    response = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"start_date": (today_msk() + timedelta(days=1)).isoformat()},
    )
    assert response.status_code == 200, response.text
    return response.json()["user_program_id"]


def test_user_deletion_requires_authentication(client):
    response = client.delete("/api/v1/programs/assigned/1")

    assert response.status_code == 401


def test_user_deletion_archives_program_and_preserves_history_template_and_reassignment(client):
    headers = _auth(client, 92001)
    template_id = _create_template(client, headers, "Удаляемая программа")
    replacement_template_id = _create_template(client, headers, "Новая программа")
    program_id = _assign(client, headers, template_id)

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 92001).one()
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program.id)
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .all()
        )
        completed_workout, planned_workout = workouts
        completed_workout.status = "completed"
        completed_workout.completed_at = now_msk_naive()
        completed_set = completed_workout.exercises[0].sets[0]
        completed_set.actual_reps = 8
        completed_set.actual_weight = 20
        completed_set.is_completed = True
        db.add(
            Notification(
                user_id=user.id,
                category="workout_reminder",
                event_kind="reminder",
                title="Скоро тренировка",
                body="По плану",
                scheduled_for=now_msk_naive(),
                scheduled_for_utc=now_msk_naive(),
                status="queued",
                dedupe_key=f"workout:{planned_workout.id}:reminder",
                action_url="/app?section=today",
            )
        )
        db.commit()

    deleted = client.delete(f"/api/v1/programs/assigned/{program_id}", headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b""

    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        assert program.template_id == template_id
        assert program.is_active is False
        assert program.status == "archived"
        assert program.archived_at is not None

        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .all()
        )
        assert [workout.status for workout in workouts] == ["completed", "cancelled"]
        completed_set = workouts[0].exercises[0].sets[0]
        assert (completed_set.actual_reps, completed_set.actual_weight) == (8, 20)
        assert completed_set.is_completed is True

        reminder = (
            db.query(Notification)
            .filter(Notification.dedupe_key == f"workout:{workouts[1].id}:reminder")
            .one()
        )
        assert reminder.status == "cancelled"
        assert reminder.last_error == "workout_reminder_invalidated"

        revisions = (
            db.query(ProgramRevision)
            .filter(ProgramRevision.user_program_id == program_id)
            .order_by(ProgramRevision.revision_number.asc())
            .all()
        )
        assert [revision.revision_number for revision in revisions] == [1, 2]
        assert revisions[-1].change_kind == "program_archived"
        assert revisions[-1].reason == "Программа удалена пользователем"
        assert revisions[-1].changed_fields == {
            "removed_by_user": True,
            "cancelled_future_workouts": True,
        }

    me = client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["has_active_program"] is False
    assert (
        client.get(f"/api/v1/programs/templates/{template_id}", headers=headers).status_code == 200
    )
    history = client.get("/api/v1/workouts/history/summary", headers=headers)
    assert history.status_code == 200
    assert history.json()["workouts_completed"] == 1

    repeated = client.delete(f"/api/v1/programs/assigned/{program_id}", headers=headers)
    assert repeated.status_code == 404
    with get_session_context() as db:
        assert (
            db.query(ProgramRevision).filter(ProgramRevision.user_program_id == program_id).count()
            == 2
        )

    reassigned = client.post(
        f"/api/v1/programs/templates/{replacement_template_id}/assign-to-me",
        headers=headers,
        json={"start_date": (today_msk() + timedelta(days=1)).isoformat()},
    )
    assert reassigned.status_code == 200, reassigned.text


def test_user_deletion_does_not_reveal_foreign_program(client):
    owner_headers = _auth(client, 92002)
    template_id = _create_template(client, owner_headers, "Чужая программа")
    program_id = _assign(client, owner_headers, template_id)
    other_headers = _auth(client, 92003)

    response = client.delete(f"/api/v1/programs/assigned/{program_id}", headers=other_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Assigned program not found"
    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        assert program.is_active is True


def test_user_deletion_rejects_in_progress_workout_without_partial_archive(client):
    headers = _auth(client, 92004)
    template_id = _create_template(client, headers, "Тренировка в процессе")
    program_id = _assign(client, headers, template_id)

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 92004).one()
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .all()
        )
        workouts[0].status = "in_progress"
        db.add(
            Notification(
                user_id=user.id,
                category="workout_reminder",
                event_kind="reminder",
                title="Скоро тренировка",
                body="По плану",
                scheduled_for=now_msk_naive(),
                scheduled_for_utc=now_msk_naive(),
                status="queued",
                dedupe_key=f"workout:{workouts[1].id}:reminder",
                action_url="/app?section=today",
            )
        )
        db.commit()

    response = client.delete(f"/api/v1/programs/assigned/{program_id}", headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot delete a program while a workout is in progress"
    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        assert program.is_active is True
        assert program.status == "scheduled"
        assert program.archived_at is None
        assert program.current_revision_number == 1
        assert (
            db.query(ProgramRevision).filter(ProgramRevision.user_program_id == program_id).count()
            == 1
        )
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .all()
        )
        assert [workout.status for workout in workouts] == ["in_progress", "planned"]
        reminder = (
            db.query(Notification)
            .filter(Notification.dedupe_key == f"workout:{workouts[1].id}:reminder")
            .one()
        )
        assert reminder.status == "queued"
