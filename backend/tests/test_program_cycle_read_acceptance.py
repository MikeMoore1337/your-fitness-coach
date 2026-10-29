"""Focused acceptance regressions for cycle read projections and scoped edits."""

from datetime import datetime, time, timedelta

import pytest
from sqlalchemy.orm import joinedload
from test_program_cycle_domain import TODAY, assigned_cycle, revision, schedule
from test_program_cycle_domain import fixed_calendar as fixed_calendar
from test_program_week_cycle import _auth, _payload

from fitminiapp_api.api.v1 import workouts as routes
from fitminiapp_api.db.session import SessionLocal, engine, get_session_context
from fitminiapp_api.models.notification import Notification, NotificationSetting
from fitminiapp_api.models.program import (
    ProgramRevision,
    ProgramTemplate,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
    WorkoutSetMutation,
)
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.schemas.program import CoachProgramExerciseCreate
from fitminiapp_api.services import notifications, program_versioning, programs, progress


def _completed_facts(body):
    return {
        **{key: body[key] for key in ("id", "status", "started_at", "completed_at")},
        "exercises": [
            {
                "id": exercise["id"],
                "prescribed_reps": exercise["prescribed_reps"],
                "sets": [
                    {
                        key: item[key]
                        for key in (
                            "id",
                            "actual_reps",
                            "actual_weight",
                            "rir",
                            "is_completed",
                            "version",
                        )
                    }
                    for item in exercise["sets"]
                ],
            }
            for exercise in body["exercises"]
        ],
    }


def _complete_today(client, headers):
    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    workout_id = response.json()["id"]
    response = client.post(f"/api/v1/workouts/{workout_id}/start", headers=headers)
    assert response.status_code == 200, response.text
    for item in response.json()["exercises"][0]["sets"]:
        logged = client.patch(
            f"/api/v1/workouts/sets/{item['id']}",
            headers=headers,
            json={
                "actual_reps": 8,
                "actual_weight": 40,
                "rir": "2",
                "is_completed": True,
                "expected_version": item["version"],
                "mutation_id": f"916-acceptance-completed-{item['id']}",
            },
        )
        assert logged.status_code == 200, logged.text
        assert logged.json()["version"] == item["version"] + 1
    response = client.post(f"/api/v1/workouts/{workout_id}/finish", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    return _completed_facts(response.json())


def _duration(client, headers, program_id, weeks):
    before = revision(program_id)
    response = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": before,
            "effective_from_week": 6,
            "duration_weeks": weeks,
        },
    )
    assert response.status_code == 200, response.text
    assert revision(program_id) == before + 1


@pytest.mark.parametrize("read_path", ["schedule", "week"])
def test_reduced_duration_hides_cancelled_occurrences_but_preserves_history(
    client, monkeypatch, read_path
):
    headers, program_id, _, _ = assigned_cycle(client, n=20)
    completed = _complete_today(client, headers)
    future = TODAY + timedelta(weeks=10)
    original = schedule(client, headers, future, 70)
    assert [row["week_number"] for row in original] == list(range(11, 21))
    _duration(client, headers, program_id, 10)

    with get_session_context() as db:
        cancelled = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id, UserWorkout.week_number > 10)
            .all()
        )
        assert {row.id for row in cancelled} == {row["id"] for row in original}
        assert all(row.status == "cancelled" for row in cancelled)
        assert all(row.plan_materialized is False and not row.exercises for row in cancelled)
    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    assert _completed_facts(response.json()) == completed

    if read_path == "schedule":
        result = schedule(client, headers, future, 70)
    else:
        monkeypatch.setattr(routes, "recovery_today_for_user", lambda _user: future)
        response = client.get("/api/v1/workouts/week", headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
    assert result == [], [(row["week_number"], row["status"]) for row in result]


def test_duration_restore_reuses_occurrences_facts_and_scheduled_reminders(client, monkeypatch):
    headers, program_id, _, _ = assigned_cycle(client, n=20)
    completed = _complete_today(client, headers)
    future = TODAY + timedelta(weeks=10)
    original = schedule(client, headers, future, 70)
    monkeypatch.setattr(
        notifications, "now_for_user_naive", lambda _user: datetime.combine(future, time(8))
    )
    with get_session_context() as db:
        owner = db.query(User).filter_by(telegram_user_id=916200).one()
        owner_id = owner.id
        setting = db.query(NotificationSetting).filter_by(user_id=owner.id).one_or_none()
        if setting is None:
            setting = NotificationSetting(user_id=owner.id)
            db.add(setting)
        setting.workout_reminders_enabled = True
        first = db.get(UserWorkout, original[0]["id"])
        first.scheduled_time = time(10)
        db.flush()
        notifications.sync_workout_reminders(db)
        reminder_ids = {
            row.dedupe_key: row.id
            for row in db.query(Notification).filter_by(
                user_id=owner_id, category="workout_reminder"
            )
        }
        assert len(reminder_ids) == 10

    _duration(client, headers, program_id, 10)
    monkeypatch.setattr(progress, "today_for_user", lambda _user: TODAY + timedelta(weeks=20))
    with get_session_context() as db:
        owner = db.get(User, owner_id)
        summary = progress.build_progress_summary_for_range(
            db, owner, TODAY, TODAY + timedelta(weeks=20) - timedelta(days=1)
        )
        assert summary["training"]["planned_workouts"] == 10
        assert summary["training"]["completed_workouts"] == 1
        notifications.sync_workout_reminders(db)
        reminders = (
            db.query(Notification).filter_by(user_id=owner_id, category="workout_reminder").all()
        )
        assert {row.dedupe_key: row.id for row in reminders} == reminder_ids
        assert all(row.status == "cancelled" for row in reminders)

    _duration(client, headers, program_id, 20)
    restored = schedule(client, headers, future, 70)
    assert [(row["id"], row["week_number"]) for row in restored] == [
        (row["id"], row["week_number"]) for row in original
    ]
    assert all(row["status"] == "planned" for row in restored)
    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    assert _completed_facts(response.json()) == completed
    with get_session_context() as db:
        notifications.sync_workout_reminders(db)
        notifications.sync_workout_reminders(db)
        reminders = (
            db.query(Notification).filter_by(user_id=owner_id, category="workout_reminder").all()
        )
        assert {row.dedupe_key: row.id for row in reminders} == reminder_ids
        assert all(row.status == "queued" for row in reminders)
        scheduled = next(
            row for row in reminders if row.dedupe_key == f"workout:{original[0]['id']}:reminder"
        )
        assert (
            scheduled.scheduled_for
            == datetime.combine(future, time(10)) - notifications.WORKOUT_REMINDER_LEAD
        )


def _read_projection(db, owner, program_id, target, read_path):
    if read_path == "schedule":
        return routes.get_schedule(
            date_from=target, date_to=target + timedelta(weeks=1), current_user=owner, db=db
        )
    if read_path == "today":
        return routes.get_today_workout(current_user=owner, db=db)
    if read_path == "detail":
        workout = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=9).one()
        return routes._get_user_workout_or_404(db, owner, workout.id)
    if read_path == "lifecycle":
        return program_versioning.program_lifecycle_summary(db, owner, program_id)
    if read_path == "coach":
        coach = db.query(User).filter_by(telegram_user_id=916201).one()
        return programs.list_coach_assigned_programs(db, coach)
    return progress.build_progress_summaries(
        db, [owner], period_days=30, nutrition_visible_user_ids={owner.id}
    )


def _projected_rows(db, program_id):
    return (
        db.query(UserWorkout)
        .filter(UserWorkout.user_program_id == program_id, UserWorkout.week_number >= 9)
        .order_by(UserWorkout.week_number)
        .all()
    )


@pytest.mark.parametrize("flushed", [False, True], ids=["dirty", "flushed"])
@pytest.mark.parametrize(
    "read_path", ["schedule", "today", "detail", "lifecycle", "coach", "progress"]
)
def test_read_projection_persists_without_committing_or_losing_caller_work(
    client, monkeypatch, read_path, flushed
):
    if flushed and engine.dialect.name != "postgresql":
        pytest.skip("An independent projection writer cannot bypass SQLite's flushed writer lock")
    _, program_id, _, _ = assigned_cycle(client, n=20)
    target = TODAY + timedelta(weeks=8)
    if read_path == "coach":
        _auth(client, 916201, is_coach=True)
        with get_session_context() as db:
            coach = db.query(User).filter_by(telegram_user_id=916201).one()
            program = db.get(UserProgram, program_id)
            program.assigned_by_user_id = coach.id
            db.add(
                CoachClient(coach_user_id=coach.id, client_user_id=program.user_id, status="active")
            )
    if read_path == "detail":
        with get_session_context() as db:
            program_versioning.materialize_cycle_schedule(
                db, db.get(UserProgram, program_id), target, target
            )
            row = _projected_rows(db, program_id)[0]
            assert row.plan_materialized is False and not row.exercises
    monkeypatch.setattr(routes, "recovery_today_for_user", lambda _user: target)
    monkeypatch.setattr(program_versioning, "today_for_user", lambda _user: target)
    monkeypatch.setattr(programs, "today_for_user", lambda _user: target)
    monkeypatch.setattr(progress, "today_for_user", lambda _user: target)

    with SessionLocal() as db:
        owner = db.query(User).filter_by(telegram_user_id=916200).one()
        owner_id, original_name = owner.id, owner.first_name
        owner.first_name = "Caller pending name"
        if flushed:
            db.flush()
        _read_projection(db, owner, program_id, target, read_path)
        assert owner.first_name == "Caller pending name", "Read discarded caller state"
        with SessionLocal() as observer:
            assert observer.get(User, owner_id).first_name == original_name, (
                "Read committed caller state"
            )
            projected = _projected_rows(observer, program_id)
            expected_weeks = (
                [9, 10]
                if read_path == "schedule"
                else [9]
                if read_path == "detail"
                else [9, 10, 11, 12]
            )
            assert [row.week_number for row in projected] == expected_weeks
            projected_ids = [row.id for row in projected]
            if read_path in {"today", "detail"}:
                assert all(row.plan_materialized is True for row in projected)
                assert all(len(row.exercises[0].sets) == 2 for row in projected)
            else:
                assert all(
                    row.plan_materialized is False and not row.exercises for row in projected
                )
        db.rollback()
        assert owner.first_name == original_name
    with SessionLocal() as observer:
        assert observer.get(User, owner_id).first_name == original_name
        assert [row.id for row in _projected_rows(observer, program_id)] == projected_ids


@pytest.mark.parametrize("flushed", [False, True], ids=["dirty", "flushed"])
def test_failed_materialization_rolls_back_only_projection(client, monkeypatch, flushed):
    if flushed and engine.dialect.name != "postgresql":
        pytest.skip("An independent projection writer cannot bypass SQLite's flushed writer lock")
    _, program_id, _, _ = assigned_cycle(client, n=20)
    target = TODAY + timedelta(weeks=8)
    materialize = program_versioning.materialize_cycle_schedule

    def fail_after_materialization(db, program, start, end, **kwargs):
        assert materialize(db, program, start, end, **kwargs) > 0
        raise RuntimeError("916 projection failure")

    monkeypatch.setattr(
        program_versioning, "materialize_cycle_schedule", fail_after_materialization
    )
    with SessionLocal() as db:
        owner = db.query(User).filter_by(telegram_user_id=916200).one()
        owner_id, original_name = owner.id, owner.first_name
        owner.first_name = "Caller survives failure"
        if flushed:
            db.flush()
        with pytest.raises(RuntimeError, match="916 projection failure"):
            routes._materialize_user_cycle_window(db, owner, target, target)
        assert owner.first_name == "Caller survives failure"
        assert db.is_active
        assert _projected_rows(db, program_id) == [], (
            "Failed projection leaked into caller transaction"
        )
        db.flush()
        with SessionLocal() as observer:
            assert observer.get(User, owner_id).first_name == original_name
            assert _projected_rows(observer, program_id) == []
        db.rollback()
    with SessionLocal() as observer:
        assert observer.get(User, owner_id).first_name == original_name
        assert _projected_rows(observer, program_id) == []


def _edit(client, headers, program_id, slot, exercise, reps):
    return client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_scope": "future_program",
            "occurrence_weeks": [2],
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": reps,
            "rest_seconds": 90,
        },
    )


def test_repeat_scoped_edit_accepts_plan_only_versions_and_keeps_set_ids(client):
    headers, program_id, slot, exercise = assigned_cycle(client, k=1, n=20)
    before = revision(program_id)
    with get_session_context() as db:
        row = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=2).one()
        workout_id = row.id
        old_ids = [item.id for item in row.exercises[0].sets]
        old_versions = [item.version for item in row.exercises[0].sets]
    for offset, reps in enumerate(["14", "16", "18"], 1):
        response = _edit(client, headers, program_id, slot, exercise, reps)
        assert response.status_code == 200, response.text
        assert revision(program_id) == before + offset
        with get_session_context() as db:
            row = db.get(UserWorkout, workout_id)
            assert row.status == "planned" and row.started_at is None and row.completed_at is None
            assert row.plan_revision_number == before + offset
            assert row.exercises[0].prescribed_reps == reps
            assert [item.id for item in row.exercises[0].sets] == old_ids
            assert [item.version for item in row.exercises[0].sets] == [
                version + offset for version in old_versions
            ]
            assert all(
                item.actual_reps is None and item.actual_weight is None and not item.is_completed
                for item in row.exercises[0].sets
            )
            assert (
                db.query(WorkoutSetMutation)
                .filter(WorkoutSetMutation.workout_set_id.in_(old_ids))
                .count()
                == 0
            )


@pytest.mark.parametrize("plan_edited", [False, True])
@pytest.mark.parametrize("cleared", [False, True], ids=["actual", "actual-then-clear"])
def test_scoped_edit_still_rejects_recorded_facts_even_with_planned_status(
    client, monkeypatch, cleared, plan_edited
):
    headers, program_id, slot, exercise = assigned_cycle(client, k=1, n=20)
    if plan_edited:
        changed = _edit(client, headers, program_id, slot, exercise, "12")
        assert changed.status_code == 200, changed.text
    target = TODAY + timedelta(weeks=1)
    monkeypatch.setattr(routes, "recovery_today_for_user", lambda _user: target)
    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    workout_id = response.json()["id"]
    response = client.post(f"/api/v1/workouts/{workout_id}/start", headers=headers)
    assert response.status_code == 200, response.text
    item = response.json()["exercises"][0]["sets"][0]
    for index, actual_reps in enumerate([8, None] if cleared else [8], 1):
        response = client.patch(
            f"/api/v1/workouts/sets/{item['id']}",
            headers=headers,
            json={
                "actual_reps": actual_reps,
                "expected_version": item["version"] + index - 1,
                "mutation_id": f"916-acceptance-fact-{index}",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["version"] == item["version"] + index
    with get_session_context() as db:
        row = db.get(UserWorkout, workout_id)
        # Persisted facts stay protected even if legacy workout status is inconsistent.
        row.status = "planned"
        row.started_at = None
        row.completed_at = None
        saved_set = row.exercises[0].sets[0]
        facts = (saved_set.id, saved_set.actual_reps, saved_set.version)
        assert saved_set.actual_reps == (None if cleared else 8)
        assert db.query(WorkoutSetMutation).filter_by(workout_set_id=saved_set.id).count() == (
            2 if cleared else 1
        )
    before = revision(program_id)
    response = _edit(client, headers, program_id, slot, exercise, "16")
    assert response.status_code == 422, response.text
    assert revision(program_id) == before
    with get_session_context() as db:
        row = db.get(UserWorkout, workout_id)
        assert row.exercises[0].prescribed_reps == ("12" if plan_edited else "6")
        saved_set = row.exercises[0].sets[0]
        assert (saved_set.id, saved_set.actual_reps, saved_set.version) == facts


def test_start_rehydrates_when_edit_commits_after_get_hydration(client, monkeypatch):
    headers, program_id, slot, exercise = assigned_cycle(client, k=1, n=20)
    target = TODAY + timedelta(weeks=8)
    upcoming = schedule(client, headers, target, 1)[0]
    monkeypatch.setattr(routes, "recovery_today_for_user", lambda _: target)
    monkeypatch.setattr(program_versioning, "MAX_GENERATED_SETS", 8)
    original_lock = routes._lock_program
    interleaved = []

    def edit_then_relock(db, locked_program_id):
        if not interleaved:
            interleaved.append(True)
            with SessionLocal() as editor:
                program = editor.get(UserProgram, program_id)
                owner = editor.get(User, program.user_id)
                program_versioning.upsert_future_program_exercise(
                    editor,
                    owner,
                    program_id,
                    CoachProgramExerciseCreate(
                        expected_revision_number=program.current_revision_number,
                        effective_scope="future_program",
                        from_week=1,
                        day_number=1,
                        target_template_exercise_id=slot,
                        exercise_id=exercise,
                        prescribed_sets=2,
                        prescribed_reps="16",
                        rest_seconds=90,
                    ),
                )
        return original_lock(db, locked_program_id)

    monkeypatch.setattr(routes, "_lock_program", edit_then_relock)
    result = client.post(f"/api/v1/workouts/{upcoming['id']}/start", headers=headers)
    assert result.status_code == 200, result.text
    assert interleaved
    assert result.json()["exercises"][0]["prescribed_reps"] == "16", result.json()["exercises"][0][
        "prescribed_reps"
    ]


@pytest.mark.parametrize("resize", [False, True])
def test_structure_readdition_restores_only_structure_cancelled_occurrences(client, resize):
    headers, program_id, _, _ = assigned_cycle(client, k=1, n=20, days=2)
    original_ids = {
        (row["week_number"], row["day_number"]): row["id"]
        for row in schedule(client, headers, TODAY, 28)
    }
    original_ids.update(
        {
            (row["week_number"], row["day_number"]): row["id"]
            for row in schedule(client, headers, TODAY + timedelta(weeks=8), 84)
        }
    )
    with get_session_context() as db:
        manual = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=3, day_number=1)
            .one()
        )
        manual.status = "cancelled"
        manual_id = manual.id
    template_ids = []
    for days in (1, 2):
        payload = _payload(client, headers)
        payload["days"] = [
            {**payload["days"][0], "title": f"День {index}"} for index in range(1, days + 1)
        ]
        response = client.post("/api/v1/programs/templates", headers=headers, json=payload)
        assert response.status_code == 200, response.text
        template_ids.append(response.json()["template"]["id"])
    for index, template_id in enumerate(template_ids):
        with get_session_context() as db:
            owner = db.query(User).filter_by(telegram_user_id=916200).one()
            program = db.get(UserProgram, program_id)
            program_versioning.apply_imported_template_revision(
                db,
                owner,
                program_id,
                db.get(ProgramTemplate, template_id),
                expected_revision_number=program.current_revision_number,
                import_id="reviewer-structure-revision",
                allow_structure_changes=True,
            )
        if resize and index == 0:
            _duration(client, headers, program_id, 10)
    if resize:
        _duration(client, headers, program_id, 20)
    with get_session_context() as db:
        rows = db.query(UserWorkout).filter_by(user_program_id=program_id, day_number=2).all()
        assert {(row.week_number, row.day_number): row.id for row in rows} == {
            key: value for key, value in original_ids.items() if key[1] == 2
        }
        assert all(row.status == "planned" for row in rows), [
            (row.week_number, row.status) for row in rows
        ]
        assert db.get(UserWorkout, manual_id).status == "cancelled"


def test_next_workout_scope_selects_nearest_logical_occurrence(client, monkeypatch):
    headers, program_id, slot, exercise = assigned_cycle(client, k=1, n=20)
    schedule(client, headers, TODAY + timedelta(weeks=15), 1)
    target = TODAY + timedelta(weeks=8)
    monkeypatch.setattr(program_versioning, "today_for_user", lambda _: target)
    changed = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_scope": "next_workout",
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": "14",
            "rest_seconds": 90,
        },
    )
    assert changed.status_code == 200, changed.text
    with get_session_context() as db:
        override = program_versioning._cycle_occurrence_overrides(db, program_id)[-1]
        assert override["weeks"] == [9], override


def test_plan_revision_snapshot_matches_removed_set_composition(client):
    headers, program_id, slot, exercise = assigned_cycle(client, k=1, n=20)
    response = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_scope": "future_program",
            "occurrence_weeks": [2],
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 1,
            "prescribed_reps": "14",
            "rest_seconds": 90,
        },
    )
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        row = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=2).one()
        assert len(row.exercises[0].sets) == 1
        record = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id, revision_number=revision(program_id))
            .one()
        )
        snapshot = next(item for item in record.snapshot["workouts"] if item["week_number"] == 2)
        assert len(snapshot["exercises"][0]["sets"]) == 1


@pytest.mark.parametrize(
    "dirty_notes,pending_set,extra_set",
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (False, False, True),
    ],
)
def test_read_hydration_refreshes_already_loaded_exercises_and_set_versions(
    client, monkeypatch, dirty_notes, pending_set, extra_set
):
    _, program_id, slot, exercise_id = assigned_cycle(client, k=1, n=20)
    if extra_set:
        with get_session_context() as db:
            workout = (
                db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=2).one()
            )
            db.add(UserWorkoutSet(workout_exercise_id=workout.exercises[0].id, set_number=3))
    monkeypatch.setattr(program_versioning, "MAX_GENERATED_SETS", 1)
    with SessionLocal() as caller:
        owner = caller.query(User).filter_by(telegram_user_id=916200).one()
        workout = (
            caller.query(UserWorkout)
            .options(joinedload(UserWorkout.exercises).joinedload(UserWorkoutExercise.sets))
            .filter_by(user_program_id=program_id, week_number=2)
            .one()
        )
        old_exercise = workout.exercises[0]
        old_sets = list(old_exercise.sets)
        assert old_exercise.prescribed_reps == "6"
        if dirty_notes:
            old_exercise.notes = "Caller pending exercise notes"
        pending = UserWorkoutSet(set_number=4) if pending_set else None
        if pending is not None:
            old_exercise.sets.append(pending)
        with SessionLocal() as editor:
            program = editor.get(UserProgram, program_id)
            program_versioning.upsert_future_program_exercise(
                editor,
                editor.get(User, owner.id),
                program_id,
                CoachProgramExerciseCreate(
                    expected_revision_number=program.current_revision_number,
                    effective_scope="future_program",
                    occurrence_weeks=[2],
                    day_number=1,
                    target_template_exercise_id=slot,
                    exercise_id=exercise_id,
                    prescribed_sets=2,
                    prescribed_reps="14",
                    rest_seconds=90,
                ),
            )
        read = routes._get_user_workout_or_404(caller, owner, workout.id)
        assert read.plan_revision_number == 2
        live_sets = [item for item in read.exercises[0].sets if item is not pending]
        assert (
            read.exercises[0].prescribed_reps,
            [item.version for item in live_sets],
        ) == ("14", [2, 2])
        assert [item.id for item in live_sets] == [item.id for item in old_sets[:2]]
        assert old_exercise.prescribed_reps == "14"
        assert [item.version for item in old_sets[:2]] == [2, 2]
        assert [item.plan_version for item in old_sets[:2]] == [2, 2]
        if extra_set:
            assert old_sets[-1].id not in [item.id for item in live_sets]
        if pending is not None:
            assert pending in caller.new and pending in old_exercise.sets
            caller.rollback()
            with SessionLocal() as observer:
                assert (
                    observer.query(UserWorkoutSet)
                    .filter_by(workout_exercise_id=old_exercise.id)
                    .count()
                    == 2
                )
        if dirty_notes:
            assert old_exercise.notes == "Caller pending exercise notes"
            caller.rollback()
            with SessionLocal() as observer:
                assert (
                    observer.get(UserWorkoutExercise, old_exercise.id).notes
                    != "Caller pending exercise notes"
                )
