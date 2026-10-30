from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Barrier, Event

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from fitminiapp_api.db.session import SessionLocal, engine, get_session_context
from fitminiapp_api.models.program import (
    ProgramRevision,
    ProgramTemplate,
    UserProgram,
    UserWorkout,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.program import (
    CoachProgramExerciseCreate,
    ProgramCycleDisableRequest,
    ProgramLifecycleActionRequest,
    ProgramWeekTypeRevisionRequest,
)
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.program_versioning import (
    apply_program_lifecycle_action,
    disable_program_cycle,
    materialize_cycle_schedule,
    revise_program_week_type,
    upsert_future_program_exercise,
)
from fitminiapp_api.services.programs import assign_template_to_user

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="requires real PostgreSQL row locks and constraints"
)


def _assigned_cycle_with_completed_facts(client):
    auth = client.post("/api/v1/auth/dev-login", json={"telegram_user_id": 916190})
    assert auth.status_code == 200, auth.text
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    catalog = client.get("/api/v1/programs/exercises", headers=headers)
    exercise_id = next(row["id"] for row in catalog.json() if row["metric_type"] == "strength")
    template = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Concurrency cycle",
            "goal": "strength",
            "level": "beginner",
            "assign_after_create": False,
            "week_cycle": {"length_weeks": 1, "repeat": True},
            "days": [
                {
                    "title": "Day",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": 2,
                            "prescribed_reps": "8",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert template.status_code == 200, template.text
    assigned = client.post(
        f"/api/v1/programs/templates/{template.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    with get_session_context() as db:
        workout = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=1).one()
        workout_id = workout.id
        slot_id = workout.exercises[0].source_template_exercise_id
    started = client.post(f"/api/v1/workouts/{workout_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    for item in started.json()["exercises"][0]["sets"]:
        result = client.patch(
            f"/api/v1/workouts/sets/{item['id']}",
            headers=headers,
            json={
                "actual_reps": 8,
                "actual_weight": 42.5,
                "rir": "2",
                "reached_failure": False,
                "is_completed": True,
            },
        )
        assert result.status_code == 200, result.text
    finished = client.post(f"/api/v1/workouts/{workout_id}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        facts = {
            "program_id": program_id,
            "owner_id": program.user_id,
            "workout_id": workout_id,
            "slot_id": slot_id,
            "exercise_id": exercise_id,
            "version": program.current_revision_number,
            "window_start": program.start_date + timedelta(weeks=9),
            "history": {
                row.id: deepcopy(row.snapshot)
                for row in db.query(ProgramRevision).filter_by(user_program_id=program_id)
            },
            "completed": _completed_values(db, workout_id),
        }
    return facts


def _completed_values(db, workout_id):
    row = db.get(UserWorkout, workout_id)
    return (
        row.id,
        row.status,
        row.scheduled_date,
        row.started_at,
        row.completed_at,
        tuple(
            (
                item.id,
                item.set_number,
                item.actual_reps,
                item.actual_weight,
                item.rir,
                item.reached_failure,
                item.is_completed,
                item.version,
            )
            for exercise in row.exercises
            for item in sorted(exercise.sets, key=lambda value: value.id)
        ),
    )


def _assert_facts_unchanged(facts):
    with get_session_context() as db:
        assert _completed_values(db, facts["workout_id"]) == facts["completed"]
        for revision_id, snapshot in facts["history"].items():
            assert db.get(ProgramRevision, revision_id).snapshot == snapshot


def _run_parallel(*actions):
    barrier = Barrier(len(actions))

    def run(action):
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            result = action(db)
            db.commit()
            return "ok", result
        except ProgramError as exc:
            db.rollback()
            return "conflict", str(exc)
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=len(actions)) as executor:
        futures = [executor.submit(run, action) for action in actions]
        return [future.result(timeout=30) for future in futures]


def _materialize(db, facts):
    program = db.get(UserProgram, facts["program_id"])
    return materialize_cycle_schedule(
        db,
        program,
        facts["window_start"],
        facts["window_start"] + timedelta(days=6),
        with_sets=True,
    )


def _edit(db, facts, sets):
    return upsert_future_program_exercise(
        db,
        db.get(User, facts["owner_id"]),
        facts["program_id"],
        CoachProgramExerciseCreate(
            expected_revision_number=facts["version"],
            effective_scope="future_program",
            occurrence_weeks=[10],
            day_number=1,
            target_template_exercise_id=facts["slot_id"],
            exercise_id=facts["exercise_id"],
            prescribed_sets=sets,
            prescribed_reps="12",
            rest_seconds=90,
        ),
    )


def _week_ten(db, facts):
    row = db.query(UserWorkout).filter_by(user_program_id=facts["program_id"], week_number=10).one()
    assert row.source_cycle_week == 1 and row.cycle_iteration == 10
    assert row.plan_materialized
    assert len(row.exercises) == 1
    items = row.exercises[0].sets
    assert len({item.set_number for item in items}) == len(items)
    assert all(
        not item.is_completed and item.actual_reps is None and item.actual_weight is None
        for item in items
    )
    return row


def test_concurrent_cycle_materialization_creates_one_occurrence(client):
    facts = _assigned_cycle_with_completed_facts(client)
    results = _run_parallel(lambda db: _materialize(db, facts), lambda db: _materialize(db, facts))
    assert [status for status, _ in results] == ["ok", "ok"]
    assert sum(count for _, count in results) == 1
    with get_session_context() as db:
        row = _week_ten(db, facts)
        assert len(row.exercises[0].sets) == 2
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=facts["program_id"], week_number=10)
            .count()
            == 1
        )
    _assert_facts_unchanged(facts)


def test_scoped_edit_and_materialization_serialize_without_losing_plan(client):
    facts = _assigned_cycle_with_completed_facts(client)
    results = _run_parallel(lambda db: _materialize(db, facts), lambda db: _edit(db, facts, 4))
    assert [status for status, _ in results] == ["ok", "ok"]
    with get_session_context() as db:
        row = _week_ten(db, facts)
        assert row.exercises[0].prescribed_sets == 4
        assert len(row.exercises[0].sets) == 4
        assert row.exercises[0].prescribed_reps == "12"
        program = db.get(UserProgram, facts["program_id"])
        assert program.current_revision_number == facts["version"] + 1
        assert row.plan_revision_number == program.current_revision_number
    _assert_facts_unchanged(facts)


def test_two_scoped_edits_with_same_revision_have_one_winner(client):
    facts = _assigned_cycle_with_completed_facts(client)
    results = _run_parallel(lambda db: _edit(db, facts, 3), lambda db: _edit(db, facts, 4))
    assert sorted(status for status, _ in results) == ["conflict", "ok"]
    assert (
        next(value for status, value in results if status == "conflict")
        == "Program revision conflict"
    )
    with get_session_context() as db:
        assert (
            db.get(UserProgram, facts["program_id"]).current_revision_number == facts["version"] + 1
        )
        overrides = [
            row
            for row in db.query(ProgramRevision).filter_by(user_program_id=facts["program_id"])
            if "occurrence_override" in row.changed_fields
        ]
        assert len(overrides) == 1
        _materialize(db, facts)
        row = _week_ten(db, facts)
        assert (
            row.exercises[0].prescribed_sets
            == overrides[0].changed_fields["occurrence_override"]["exercise"]["prescribed_sets"]
        )
    _assert_facts_unchanged(facts)


def test_concurrent_type_change_and_disable_have_one_winner(client):
    facts = _assigned_cycle_with_completed_facts(client)

    def set_type(db):
        return revise_program_week_type(
            db,
            db.get(User, facts["owner_id"]),
            facts["program_id"],
            ProgramWeekTypeRevisionRequest(
                expected_revision_number=facts["version"], week_type="heavy", occurrence_weeks=[10]
            ),
            preview=False,
        )

    def disable(db):
        return disable_program_cycle(
            db,
            db.get(User, facts["owner_id"]),
            facts["program_id"],
            ProgramCycleDisableRequest(
                expected_revision_number=facts["version"], effective_from_week=4
            ),
            preview=False,
        )

    results = _run_parallel(set_type, disable)
    assert sorted(status for status, _ in results) == ["conflict", "ok"]
    assert (
        next(value for status, value in results if status == "conflict")
        == "Program revision conflict"
    )
    with get_session_context() as db:
        assert (
            db.get(UserProgram, facts["program_id"]).current_revision_number == facts["version"] + 1
        )
    _assert_facts_unchanged(facts)


def test_two_restarts_with_same_revision_create_one_new_assignment(client):
    facts = _assigned_cycle_with_completed_facts(client)

    def restart(db):
        return apply_program_lifecycle_action(
            db,
            db.get(User, facts["owner_id"]),
            facts["program_id"],
            ProgramLifecycleActionRequest(
                expected_revision_number=facts["version"],
                action="restart",
                reason="Concurrent restart",
            ),
        )

    results = _run_parallel(restart, restart)
    assert sorted(status for status, _ in results) == ["conflict", "ok"]
    assert (
        next(value for status, value in results if status == "conflict")
        == "Program revision conflict"
    )
    new_id = next(result["new_program_id"] for status, result in results if status == "ok")
    with get_session_context() as db:
        restarted = (
            db.query(UserProgram).filter_by(restarted_from_program_id=facts["program_id"]).one()
        )
        assert restarted.id == new_id and restarted.duration_weeks == 16
        assert (
            db.query(UserProgram).filter_by(user_id=facts["owner_id"], is_active=True).count() == 1
        )
        rows = db.query(UserWorkout).filter_by(user_program_id=new_id).all()
        assert rows and all(row.status == "planned" and row.completed_at is None for row in rows)
        assert all(
            not item.is_completed and item.actual_reps is None and item.actual_weight is None
            for row in rows
            for exercise in row.exercises
            for item in exercise.sets
        )
    _assert_facts_unchanged(facts)


def test_restart_and_replacement_use_the_same_postgres_lock_order(client):
    facts = _assigned_cycle_with_completed_facts(client)
    owner_locked, restart_requesting_owner = Event(), Event()

    def observe_owner_lock(connection, _cursor, statement, _parameters, _context, _many):
        if (
            connection.info.get("916_lock_scenario") == "restart"
            and "FROM users" in statement
            and "FOR UPDATE" in statement
        ):
            restart_requesting_owner.set()

    def replace(db):
        db.execute(text("SET LOCAL lock_timeout = '3s'"))
        db.connection().info["916_lock_scenario"] = "replace"
        owner = db.query(User).filter_by(id=facts["owner_id"]).with_for_update().one()
        owner_locked.set()
        assert restart_requesting_owner.wait(10)
        old = db.get(UserProgram, facts["program_id"])
        return assign_template_to_user(
            db,
            db.get(ProgramTemplate, old.template_id),
            owner,
            owner,
            start_date=old.start_date,
            duration_weeks=16,
            replace_active=True,
        )[0].id

    def restart(db):
        db.execute(text("SET LOCAL lock_timeout = '3s'"))
        db.connection().info["916_lock_scenario"] = "restart"
        assert owner_locked.wait(10)
        return apply_program_lifecycle_action(
            db,
            db.get(User, facts["owner_id"]),
            facts["program_id"],
            ProgramLifecycleActionRequest(
                action="restart",
                expected_revision_number=facts["version"],
                reason="Проверка порядка блокировок",
            ),
        )

    event.listen(engine, "before_cursor_execute", observe_owner_lock)
    try:
        results = _run_parallel(replace, restart)
    finally:
        event.remove(engine, "before_cursor_execute", observe_owner_lock)
    assert results[0][0] == "ok"
    assert results[1] == ("conflict", "Program revision conflict")
    with get_session_context() as db:
        assert (
            db.query(UserProgram).filter_by(user_id=facts["owner_id"], is_active=True).count() == 1
        )
    _assert_facts_unchanged(facts)


def test_cycle_materialization_rollback_then_retry_preserves_facts(client):
    facts = _assigned_cycle_with_completed_facts(client)
    db = SessionLocal()
    reached_sets = []

    def fail_on_new_sets(session, _context, _instances):
        if any(isinstance(row, UserWorkoutSet) for row in session.new):
            reached_sets.append(True)
            raise RuntimeError("injected cycle materialization failure")

    event.listen(db, "before_flush", fail_on_new_sets)
    try:
        with pytest.raises(RuntimeError, match="injected cycle materialization failure"):
            _materialize(db, facts)
        db.rollback()
    finally:
        event.remove(db, "before_flush", fail_on_new_sets)
        db.close()
    assert reached_sets == [True]
    with get_session_context() as db:
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=facts["program_id"], week_number=10)
            .count()
            == 0
        )
        assert db.get(UserProgram, facts["program_id"]).current_revision_number == facts["version"]
        assert _materialize(db, facts) == 1
    with get_session_context() as db:
        _week_ten(db, facts)
        assert _materialize(db, facts) == 0
    _assert_facts_unchanged(facts)


def test_cycle_workout_and_set_identities_are_unique_in_postgresql(client):
    facts = _assigned_cycle_with_completed_facts(client)
    with get_session_context() as db:
        _materialize(db, facts)
    db = SessionLocal()
    try:
        row = _week_ten(db, facts)
        db.add(
            UserWorkout(
                user_program_id=row.user_program_id,
                week_number=row.week_number,
                day_number=row.day_number,
                scheduled_date=row.scheduled_date,
                title="duplicate",
                status="planned",
                source_cycle_week=row.source_cycle_week,
                cycle_iteration=row.cycle_iteration,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        row = _week_ten(db, facts)
        db.add(
            UserWorkoutSet(
                workout_exercise_id=row.exercises[0].id, set_number=1, is_completed=False
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=facts["program_id"], week_number=10)
            .count()
            == 1
        )
    finally:
        db.close()
    _assert_facts_unchanged(facts)
