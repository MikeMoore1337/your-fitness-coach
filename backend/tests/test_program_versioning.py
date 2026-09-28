from datetime import timedelta

from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import (
    ProgramRevision,
    TrainingBlock,
    UserProgram,
    UserWorkout,
)
from fitminiapp_api.models.user import CoachClient, User


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
