from __future__ import annotations

from datetime import date, timedelta

import pytest
from test_program_week_cycle import _auth, _payload

from fitminiapp_api.api.v1 import workouts as routes
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import (
    ProgramRevision,
    ProgramTemplate,
    ProgramTemplateExerciseWeekPrescription,
    UserProgram,
    UserWorkout,
    UserWorkoutSet,
)
from fitminiapp_api.services import program_versioning, programs

TODAY = date(2026, 10, 5)


@pytest.fixture(autouse=True)
def fixed_calendar(monkeypatch):
    monkeypatch.setattr(programs, "today_for_user", lambda _user: TODAY)
    monkeypatch.setattr(program_versioning, "today_for_user", lambda _user: TODAY)
    monkeypatch.setattr(routes, "recovery_today_for_user", lambda _user: TODAY)


def assigned_cycle(client, *, k=3, n=16, days=1):
    headers = _auth(client, 916200)
    payload = _payload(client, headers)
    strengths = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    strength = strengths[0]
    payload["days"][0]["exercises"][0]["exercise_id"] = strength["id"]
    payload["days"] = [
        {**payload["days"][0], "title": f"День {index}"} for index in range(1, days + 1)
    ]
    payload["week_cycle"] = {"length_weeks": k, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    with get_session_context() as db:
        template = db.get(ProgramTemplate, template_id)
        for day in template.days:
            slot = day.exercises[0]
            for week in range(1, k + 1):
                db.add(
                    ProgramTemplateExerciseWeekPrescription(
                        template_exercise_id=slot.id,
                        exercise_id=strengths[(week - 1) % len(strengths)]["id"],
                        week_number=week,
                        prescribed_sets=2,
                        prescribed_reps=str(week + 5),
                        rest_seconds=90,
                    )
                )
        slot_id = template.days[0].exercises[0].id
    response = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"duration_weeks": n},
    )
    assert response.status_code == 200, response.text
    return headers, response.json()["user_program_id"], slot_id, strength["id"]


def revision(program_id):
    with get_session_context() as db:
        return db.get(UserProgram, program_id).current_revision_number


def test_duration_change_preserves_existing_future_workout_plan(client):
    headers, program_id, _, _ = assigned_cycle(client)
    with get_session_context() as db:
        workout = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=4).one()
        workout.exercises[0].prescribed_reps = "15"
        workout_id = workout.id
        set_ids = [item.id for item in workout.exercises[0].sets]
    response = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={"expected_revision_number": 1, "effective_from_week": 4, "duration_weeks": 20},
    )
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        workout = db.get(UserWorkout, workout_id)
        assert workout.exercises[0].prescribed_reps == "15"
        assert [item.id for item in workout.exercises[0].sets] == set_ids
        program = db.get(UserProgram, program_id)
        program_versioning.record_program_revision(
            db,
            program,
            actor=None,
            change_kind="block_updated",
            changed_fields={"operation": "metadata_only"},
        )
        assert program_versioning.hydrate_cycle_workout(db, workout)
        assert workout.exercises[0].prescribed_reps == "15"
        assert [item.id for item in workout.exercises[0].sets] == set_ids


def schedule(client, headers, start, days=93):
    response = client.get(
        "/api/v1/workouts/schedule",
        headers=headers,
        params={
            "date_from": start.isoformat(),
            "date_to": (start + timedelta(days=days - 1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("k", [1, 3, 7])
@pytest.mark.parametrize("days_per_week", [1, 3, 7])
@pytest.mark.parametrize("range_days", [7, 30, 93])
def test_schedule_returns_complete_range_without_future_sets(client, k, days_per_week, range_days):
    headers, program_id, _, _ = assigned_cycle(client, k=k, n=30, days=days_per_week)
    start = TODAY + timedelta(weeks=8)
    expected = [
        (TODAY + timedelta(weeks=week - 1, days=day - 1), week, day)
        for week in range(1, 31)
        for day in range(1, days_per_week + 1)
        if start
        <= TODAY + timedelta(weeks=week - 1, days=day - 1)
        <= start + timedelta(days=range_days - 1)
    ]
    expected.sort()
    before = None
    for _ in range(2):
        result = schedule(client, headers, start, range_days)
        assert [
            (date.fromisoformat(row["scheduled_date"]), row["week_number"], row["day_number"])
            for row in result
        ] == expected
        assert all(row["status"] == "planned" for row in result)
        ids = [row["id"] for row in result]
        if before is not None:
            assert ids == before
        before = ids
    with get_session_context() as db:
        assert (
            db.query(UserWorkoutSet)
            .join(UserWorkoutSet.workout_exercise)
            .join(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .count()
            == 4 * days_per_week * 2
        )
        assert (
            db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=1).count()
            == days_per_week
        )
        assert (
            not db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=5).first()
        )
    assert schedule(client, headers, TODAY + timedelta(weeks=4), 28)


@pytest.mark.parametrize(
    "scope,affected",
    [
        ({"occurrence_weeks": [8]}, {8}),
        ({"from_week": 8, "source_cycle_week": 2}, {8, 11, 14}),
        ({"from_week": 8}, set(range(8, 17))),
    ],
)
def test_scoped_edits_materialized_and_unmaterialized(client, scope, affected):
    headers, program_id, slot, exercise = assigned_cycle(client)
    schedule(client, headers, TODAY + timedelta(weeks=7), 21)
    with get_session_context() as db:
        version = db.get(UserProgram, program_id).current_revision_number
        original_revision = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id, change_kind="assigned")
            .one()
            .snapshot
        )
        old_ids = {
            row.week_number: row.id
            for row in db.query(UserWorkout).filter_by(user_program_id=program_id)
        }
    edited = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": version,
            "effective_scope": "future_program",
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 3,
            "prescribed_reps": "12",
            "rest_seconds": 90,
            **scope,
        },
    )
    assert edited.status_code == 200, edited.text
    stale = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": version,
            "effective_scope": "future_program",
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 3,
            "prescribed_reps": "12",
            **scope,
        },
    )
    assert stale.status_code == 409, stale.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        for first in [1, 5, 9, 13]:
            program_versioning.materialize_next_cycle_window(
                db, program, through_date=TODAY + timedelta(weeks=first - 1)
            )
        rows = db.query(UserWorkout).filter_by(user_program_id=program_id).all()
        assert {row.week_number for row in rows} == set(range(1, 17))
        for row in rows:
            assert row.exercises[0].prescribed_reps == (
                "12" if row.week_number in affected else str((row.week_number - 1) % 3 + 6)
            )
            if row.week_number in old_ids:
                assert row.id == old_ids[row.week_number]
        assert (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id, change_kind="assigned")
            .one()
            .snapshot
            == original_revision
        )


def test_cycle_boundary_and_duration_revision_preserve_completed_facts(client, monkeypatch):
    headers, program_id, _, _ = assigned_cycle(client)
    first = client.get("/api/v1/workouts/today", headers=headers).json()
    started = client.post(f"/api/v1/workouts/{first['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    for item in started.json()["exercises"][0]["sets"]:
        response = client.patch(
            f"/api/v1/workouts/sets/{item['id']}",
            headers=headers,
            json={"actual_reps": 8, "actual_weight": 40, "rir": "2", "is_completed": True},
        )
        assert response.status_code == 200, response.text
    assert client.post(f"/api/v1/workouts/{first['id']}/finish", headers=headers).status_code == 200
    for week in range(2, 6):
        current_day = TODAY + timedelta(weeks=week - 1)
        monkeypatch.setattr(
            routes, "recovery_today_for_user", lambda _user, current_day=current_day: current_day
        )
        workout = client.get("/api/v1/workouts/today", headers=headers)
        assert workout.status_code == 200, workout.text
        started = client.post(f"/api/v1/workouts/{workout.json()['id']}/start", headers=headers)
        assert started.status_code == 200, started.text
        for item in started.json()["exercises"][0]["sets"]:
            logged = client.patch(
                f"/api/v1/workouts/sets/{item['id']}",
                headers=headers,
                json={"actual_reps": 8, "actual_weight": 40, "rir": "2", "is_completed": True},
            )
            assert logged.status_code == 200, logged.text
        assert (
            client.post(
                f"/api/v1/workouts/{workout.json()['id']}/finish", headers=headers
            ).status_code
            == 200
        )
    schedule(client, headers, TODAY, 93)
    with get_session_context() as db:
        row = db.get(UserWorkout, first["id"])
        all_completed_facts = [
            (
                workout.id,
                workout.completed_at,
                [
                    (item.id, item.actual_weight, item.actual_reps, item.rir, item.version)
                    for exercise in workout.exercises
                    for item in exercise.sets
                ],
            )
            for workout in db.query(UserWorkout)
            .filter_by(user_program_id=program_id, status="completed")
            .order_by(UserWorkout.id)
        ]
        assert len(all_completed_facts) == 5
        original = (
            row.completed_at,
            [
                (item.id, item.actual_weight, item.actual_reps, item.rir, item.version)
                for item in row.exercises[0].sets
            ],
        )
    for duration in [20, 10, 30]:
        response = client.patch(
            f"/api/v1/programs/assigned/{program_id}/cycle",
            headers=headers,
            json={
                "expected_revision_number": revision(program_id),
                "effective_from_week": 6,
                "duration_weeks": duration,
            },
        )
        assert response.status_code == 200, response.text
    changed = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_from_week": 6,
            "source_week_order": [1, 2, 3, 1],
        },
    )
    assert changed.status_code == 200, changed.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        program_versioning.materialize_next_cycle_window(
            db, program, through_date=TODAY + timedelta(weeks=5)
        )
        row = db.get(UserWorkout, first["id"])
        assert (
            row.completed_at,
            [
                (item.id, item.actual_weight, item.actual_reps, item.rir, item.version)
                for item in row.exercises[0].sets
            ],
        ) == original
        assert program_versioning._cycle_workout_plans(db, program, 6)[0]["source_cycle_week"] == 1
        assert program_versioning._cycle_workout_plans(db, program, 9)[0]["source_cycle_week"] == 4
        assert program_versioning._cycle_workout_plans(db, program, 10)[0]["source_cycle_week"] == 1
        assert db.get(UserWorkout, first["id"]).source_cycle_week == 1
        assert [
            (
                workout.id,
                workout.completed_at,
                [
                    (item.id, item.actual_weight, item.actual_reps, item.rir, item.version)
                    for exercise in workout.exercises
                    for item in exercise.sets
                ],
            )
            for workout in db.query(UserWorkout)
            .filter_by(user_program_id=program_id, status="completed")
            .order_by(UserWorkout.id)
        ] == all_completed_facts
    assert len(schedule(client, headers, TODAY + timedelta(weeks=9), 93)) == 14


@pytest.mark.parametrize(
    "k,n,repeat", [(7, 2, True), (7, 7, False), (3, 30, True), (7, 30, True), (1, 45, True)]
)
def test_finite_cycle_and_long_duration(client, k, n, repeat):
    headers, program_id, _, _ = assigned_cycle(client, k=k, n=n)
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert len(program.workouts) == min(4, n)
        before = program.current_revision_number
    if not repeat:
        changed = client.patch(
            f"/api/v1/programs/assigned/{program_id}/cycle",
            headers=headers,
            json={"expected_revision_number": before, "effective_from_week": 1, "repeat": False},
        )
        assert changed.status_code == 200, changed.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        program_versioning.materialize_next_cycle_window(
            db, program, through_date=TODAY + timedelta(weeks=n - 1)
        )
        last = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=n).one()
        assert last.source_cycle_week == (n - 1) % k + 1
        assert last.cycle_iteration == (n - 1) // k + 1
        assert last.exercises[0].prescribed_reps == str((n - 1) % k + 6)
        assert db.query(UserWorkout).filter_by(user_program_id=program_id).count() <= 5


def test_cycle_shared_copy_and_export_keep_logical_plan(client):
    from fitminiapp_api.models.user import User
    from fitminiapp_api.services.account_export import build_account_export

    headers, program_id, _, _ = assigned_cycle(client, k=7, n=30)
    with get_session_context() as db:
        template_id = db.get(UserProgram, program_id).template_id
    preview = client.post(
        "/api/v1/shares/program/preview", headers=headers, json={"template_id": template_id}
    )
    assert preview.status_code == 200, preview.text
    created = client.post(
        "/api/v1/shares/program",
        headers=headers,
        json={"template_id": template_id, "preview_hash": preview.json()["preview_hash"]},
    )
    assert created.status_code == 201, created.text
    other = _auth(client, 916201)
    imported = client.post(
        f"/api/v1/shares/{created.json()['share_id']}/import",
        headers=other,
        json={"preview_hash": created.json()["preview_hash"]},
    )
    assert imported.status_code == 200, imported.text
    with get_session_context() as db:
        copy = db.query(UserProgram).filter(UserProgram.id != program_id).one()
        assert copy.template.program_metadata["week_cycle"]["length_weeks"] == 7
        assert len(copy.workouts) == 4
        owner = db.query(User).filter_by(telegram_user_id=916200).one()
        exported = build_account_export(db, owner)
        assert exported["programs"][0]["duration_weeks"] == 30
        assert len(exported["programs"][0]["revisions"][0]["snapshot"]["logical_cycle"]) == 7


def test_cycle_import_revision_updates_logical_source_and_restart(client):
    from fitminiapp_api.models.user import User

    headers, program_id, _, _ = assigned_cycle(client, k=3, n=30)
    payload = _payload(client, headers)
    payload["days"][0]["exercises"][0]["prescribed_reps"] = "14"
    replacement = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert replacement.status_code == 200, replacement.text
    with get_session_context() as db:
        owner = db.query(User).filter_by(telegram_user_id=916200).one()
        program = db.get(UserProgram, program_id)
        updated, _, version = program_versioning.apply_imported_template_revision(
            db,
            owner,
            program_id,
            db.get(ProgramTemplate, replacement.json()["template"]["id"]),
            expected_revision_number=program.current_revision_number,
            import_id="synthetic-cycle-import",
            allow_structure_changes=True,
        )
        assert updated.duration_weeks == 30
        program_versioning.materialize_next_cycle_window(
            db, program, through_date=TODAY + timedelta(weeks=9)
        )
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=10)
            .one()
            .exercises[0]
            .prescribed_reps
            == "14"
        )
    restarted = client.post(
        f"/api/v1/programs/assigned/{program_id}/lifecycle",
        headers=headers,
        json={
            "action": "restart",
            "expected_revision_number": version,
            "reason": "Повторить импортированный план",
        },
    )
    assert restarted.status_code == 200, restarted.text
    with get_session_context() as db:
        new_program = db.get(UserProgram, restarted.json()["new_program_id"])
        assert len(new_program.workouts) == 4
        assert all(row.exercises[0].prescribed_reps == "14" for row in new_program.workouts)


def test_reminders_extend_logical_schedule_without_future_sets(client, monkeypatch):
    from datetime import datetime, time

    from fitminiapp_api.models.notification import Notification, NotificationSetting
    from fitminiapp_api.models.user import User
    from fitminiapp_api.services import notifications

    _, program_id, _, _ = assigned_cycle(client, k=3, n=30)
    current = TODAY + timedelta(weeks=8)
    monkeypatch.setattr(
        notifications, "now_for_user_naive", lambda _user: datetime.combine(current, time(8))
    )
    with get_session_context() as db:
        owner = db.query(User).filter_by(telegram_user_id=916200).one()
        setting = db.query(NotificationSetting).filter_by(user_id=owner.id).first()
        if setting is None:
            setting = NotificationSetting(user_id=owner.id)
            db.add(setting)
        setting.workout_reminders_enabled = True
        db.flush()
        notifications.sync_workout_reminders(db)
        db.flush()
        future = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=9).one()
        assert future.plan_materialized is False and not future.exercises
        assert (
            db.query(Notification)
            .filter_by(user_id=owner.id, dedupe_key=f"workout:{future.id}:reminder")
            .one()
            .status
            == "queued"
        )
        notifications.sync_workout_reminders(db)
        assert (
            db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=9).count() == 1
        )


def test_thirty_week_completion_and_missing_days_are_not_lost(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=30, days=3)
    # A one-day read must not make a partially projected week count as complete.
    schedule(client, headers, TODAY + timedelta(weeks=8), 1)
    for _ in range(32):
        with get_session_context() as db:
            program = db.get(UserProgram, program_id)
            planned = [
                row.id
                for row in db.query(UserWorkout).filter_by(
                    user_program_id=program_id, status="planned"
                )
            ]
            if not program.is_active:
                break
        for workout_id in planned:
            response = client.post(f"/api/v1/workouts/{workout_id}/skip", headers=headers)
            assert response.status_code == 200, response.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert program.status == "completed" and not program.is_active
        actual = {(row.week_number, row.day_number) for row in program.workouts}
        assert actual == {(week, day) for week in range(1, 31) for day in range(1, 4)}


def test_reschedule_pause_resume_keep_occurrence_identity(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=30)
    source_day = TODAY + timedelta(weeks=8)
    item = schedule(client, headers, source_day, 1)[0]
    moved_day = source_day + timedelta(days=2)
    moved = client.patch(
        f"/api/v1/workouts/{item['id']}/schedule",
        headers=headers,
        json={"scheduled_date": moved_day.isoformat()},
    )
    assert moved.status_code == 200, moved.text
    assert schedule(client, headers, source_day, 1) == []
    assert schedule(client, headers, moved_day, 1)[0]["id"] == item["id"]
    for action in ["pause", "resume"]:
        result = client.post(
            f"/api/v1/programs/assigned/{program_id}/lifecycle",
            headers=headers,
            json={
                "action": action,
                "expected_revision_number": revision(program_id),
                "reason": "Проверка расписания",
            },
        )
        assert result.status_code == 200, result.text
        items = schedule(client, headers, moved_day, 1)
        assert items == [] if action == "pause" else items[0]["id"] == item["id"]
    with get_session_context() as db:
        row = db.get(UserWorkout, item["id"])
        assert (row.week_number, row.day_number, row.source_cycle_week, row.cycle_iteration) == (
            9,
            1,
            3,
            3,
        )
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=9, day_number=1)
            .count()
            == 1
        )


def test_repeat_block_uses_unmaterialized_cycle_source(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=30)
    created = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "title": "Повторяемый блок",
            "purpose": "Проверка источника",
            "start_date": (TODAY + timedelta(weeks=9)).isoformat(),
            "end_date": (TODAY + timedelta(weeks=11) - timedelta(days=1)).isoformat(),
            "is_deload": True,
        },
    )
    assert created.status_code == 201, created.text
    block_id = created.json()["block"]["id"]
    for state in ["active", "completed"]:
        changed = client.patch(
            f"/api/v1/programs/assigned/{program_id}/blocks/{block_id}",
            headers=headers,
            json={"expected_revision_number": revision(program_id), "status": state},
        )
        assert changed.status_code == 200, changed.text
    with get_session_context() as db:
        assert (
            not db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=10).first()
        )
    repeated = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks/{block_id}/repeat",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "reason": "Повторить логический план",
        },
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["duration_weeks"] == 32
    assert repeated.json()["block"]["is_deload"] is True
    with get_session_context() as db:
        rows = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id, UserWorkout.week_number > 30)
            .order_by(UserWorkout.week_number)
            .all()
        )
        assert [row.week_number for row in rows] == [31, 32]
        assert [row.exercises[0].prescribed_reps for row in rows] == ["6", "7"]
        assert all(
            not item.is_completed and item.actual_weight is None
            for row in rows
            for exercise in row.exercises
            for item in exercise.sets
        )


def test_bounded_future_edit_refreshes_stale_plan_before_start(client, monkeypatch):
    headers, program_id, slot, exercise = assigned_cycle(client, k=1, n=30)
    with get_session_context() as db:
        row = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=2).one()
        workout_id = row.id
        old_ids = [item.id for item in row.exercises[0].sets]
        old_versions = [item.version for item in row.exercises[0].sets]
    monkeypatch.setattr(program_versioning, "MAX_GENERATED_SETS", 3)
    edited = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_scope": "future_program",
            "from_week": 1,
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": "14",
            "rest_seconds": 90,
        },
    )
    assert edited.status_code == 200, edited.text
    with get_session_context() as db:
        row = db.get(UserWorkout, workout_id)
        assert row.exercises[0].prescribed_reps == "6"
        assert row.plan_revision_number < db.get(UserProgram, program_id).current_revision_number
    monkeypatch.setattr(routes, "recovery_today_for_user", lambda _user: TODAY + timedelta(weeks=1))
    started = client.post(f"/api/v1/workouts/{workout_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    actual = started.json()["exercises"][0]
    assert actual["prescribed_reps"] == "14"
    assert [item["id"] for item in actual["sets"]] == old_ids
    assert [item["version"] for item in actual["sets"]] == [version + 1 for version in old_versions]
    stale = client.patch(
        f"/api/v1/workouts/sets/{old_ids[0]}",
        headers=headers,
        json={
            "actual_reps": 8,
            "actual_weight": 40,
            "is_completed": True,
            "expected_version": old_versions[0],
            "mutation_id": "916-stale-plan-mutation",
        },
    )
    assert stale.status_code == 409, stale.text


def test_future_edit_does_not_touch_a_started_workout(client):
    headers, program_id, slot, exercise = assigned_cycle(client)
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).status_code == 200
    )
    before = revision(program_id)
    attempted = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": before,
            "effective_scope": "future_program",
            "occurrence_weeks": [1],
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 3,
            "prescribed_reps": "15",
        },
    )
    assert attempted.status_code == 422, attempted.text
    assert revision(program_id) == before
    with get_session_context() as db:
        row = db.get(UserWorkout, workout["id"])
        assert row.status == "in_progress" and row.exercises[0].prescribed_reps == "6"


def test_future_edit_in_current_week_uses_workout_date(client, monkeypatch):
    headers, program_id, _, exercise = assigned_cycle(client, days=3)
    middle = TODAY + timedelta(days=1)
    monkeypatch.setattr(program_versioning, "today_for_user", lambda _user: middle)
    with get_session_context() as db:
        row = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=1, day_number=3)
            .one()
        )
        slot = row.exercises[0].source_template_exercise_id
        workout_id = row.id
    response = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_scope": "future_program",
            "day_number": 3,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": "17",
            "rest_seconds": 90,
        },
    )
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        assert db.get(UserWorkout, workout_id).exercises[0].prescribed_reps == "17"
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=1, day_number=1)
            .one()
            .exercises[0]
            .prescribed_reps
            == "6"
        )


def test_nonrepeating_duration_extension_requires_explicit_repeat(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=3)
    response = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_from_week": 1,
            "repeat": False,
        },
    )
    assert response.status_code == 200, response.text
    before = revision(program_id)
    for extra in ({}, {"repeat": True}):
        response = client.patch(
            f"/api/v1/programs/assigned/{program_id}/cycle",
            headers=headers,
            json={
                "expected_revision_number": before,
                "effective_from_week": 1,
                "duration_weeks": 16,
                **extra,
            },
        )
        assert response.status_code == (200 if extra else 422), response.text
        if not extra:
            assert revision(program_id) == before


def test_coach_and_progress_count_full_logical_plan_after_absence(client, monkeypatch):
    from fitminiapp_api.models.user import CoachClient, User
    from fitminiapp_api.services import progress

    headers, program_id, _, _ = assigned_cycle(client, k=3, n=30, days=3)
    coach_headers = _auth(client, 916201, is_coach=True)
    later = TODAY + timedelta(weeks=8)
    monkeypatch.setattr(programs, "today_for_user", lambda _user: later)
    monkeypatch.setattr(progress, "today_for_user", lambda _user: later)
    with get_session_context() as db:
        coach = db.query(User).filter_by(telegram_user_id=916201).one()
        program = db.get(UserProgram, program_id)
        program.assigned_by_user_id = coach.id
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=program.user_id, status="active"))
        # A moved occurrence is counted at its actual scheduled date, not again at its source date.
        moved = next(
            row for row in program.workouts if row.week_number == 2 and row.day_number == 1
        )
        moved.scheduled_date = later + timedelta(days=1)
    response = client.get("/api/v1/coach/assigned-programs", headers=coach_headers)
    assert response.status_code == 200, response.text
    item = next(row for row in response.json() if row["id"] == program_id)
    assert item["workouts_total"] == 90 and item["workouts_planned"] == 90
    assert item["next_workout_date"] == later.isoformat()
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        owner = db.get(User, program.user_id)
        result = progress.build_progress_summary_for_range(db, owner, TODAY, later)
        assert result["training"]["planned_workouts"] == 23
        assert result["training"]["completed_workouts"] == 0
        assert program_versioning.cycle_workout_count(db, program) == 90
        assert (
            db.query(UserWorkoutSet)
            .join(UserWorkoutSet.workout_exercise)
            .join(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .count()
            == 24
        )
    # Existing athlete reads keep the same projected occurrence identifiers.
    assert schedule(client, headers, later, 7)


def test_cycle_revision_checks_current_trainer_and_assignment_owner(client):
    from fitminiapp_api.models.user import CoachClient, User

    headers, program_id, _, _ = assigned_cycle(client)
    other = _auth(client, 916202)
    trainer = _auth(client, 916203, is_coach=True)
    change = {
        "expected_revision_number": revision(program_id),
        "effective_from_week": 2,
        "duration_weeks": 20,
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    assert client.patch(endpoint, headers=other, json=change).status_code in {403, 404}
    assert client.patch(endpoint, headers=trainer, json=change).status_code in {403, 404}
    with get_session_context() as db:
        coach = db.query(User).filter_by(telegram_user_id=916203).one()
        program = db.get(UserProgram, program_id)
        program.assigned_by_user_id = coach.id
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=program.user_id, status="active"))
    response = client.patch(endpoint, headers=trainer, json=change)
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        db.query(CoachClient).filter_by(
            client_user_id=db.get(UserProgram, program_id).user_id
        ).one().status = "inactive"
    change["expected_revision_number"] = revision(program_id)
    change["duration_weeks"] = 22
    assert client.patch(endpoint, headers=trainer, json=change).status_code in {403, 404}
    assert revision(program_id) == change["expected_revision_number"]
    response = client.patch(endpoint, headers=headers, json=change)
    assert response.status_code == 200, response.text
