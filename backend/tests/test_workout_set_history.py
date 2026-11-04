from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import event
from test_program_week_cycle import _auth

from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.services.workout_set_history import build_workout_set_history

NOW = datetime(2026, 10, 30, 12)


def _session(db, program, *, days_ago, count=4, roles=None, group_kind=None):
    workout = UserWorkout(
        user_program_id=program.id,
        scheduled_date=NOW.date() - timedelta(days=days_ago),
        day_number=1,
        week_number=1,
        title="Силовая",
        status="completed" if days_ago else "in_progress",
        started_at=NOW - timedelta(days=days_ago, hours=1),
        completed_at=NOW - timedelta(days=days_ago) if days_ago else None,
    )
    bench = db.query(Exercise).filter_by(slug="bench-press").one()
    roles = roles or ["working"] * count
    segments = [
        {"position": index, "role": role, "rep_target": {"kind": "exact", "value": 8}}
        for index, role in enumerate(roles, 1)
    ]
    groups = []
    if group_kind:
        groups = [{"group_id": 1, "kind": group_kind}]
        for index, part in enumerate(segments, 1):
            part.update(group_id=1, group_position=index)
            if group_kind == "circuit":
                part.update(round_number=index, group_position=1)
                groups[0]["rounds"] = count
    exercise = UserWorkoutExercise(
        workout=workout,
        exercise_id=bench.id,
        source_template_exercise_id=1132,
        metric_type="strength",
        sort_order=1,
        prescribed_sets=count,
        prescribed_reps="8",
        prescription={
            "version": 1,
            "metric_type": "strength",
            "segments": segments,
            "groups": groups,
        },
    )
    db.add(workout)
    for index, role in enumerate(roles, 1):
        db.add(
            UserWorkoutSet(
                workout_exercise=exercise,
                set_number=index,
                actual_weight=([160, 180, 200, 190][index - 1] if count == 4 else 140 + 20 * index)
                if days_ago
                else None,
                actual_reps=8 if days_ago else None,
                is_completed=bool(days_ago),
                set_kind="warmup" if role == "warmup" else "drop" if role == "drop" else "working",
                planned_role=role,
                planned_position=index,
                planned_group_id=1 if group_kind else None,
                planned_group_kind=group_kind,
                planned_round=index if group_kind == "circuit" else None,
            )
        )
    db.flush()
    return workout


@pytest.fixture
def case(client):
    headers = _auth(client, 113200)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    with get_session_context() as db:
        program = UserProgram(
            user_id=user_id,
            start_date=date(2026, 10, 1),
            duration_weeks=16,
            schedule_weekdays=[0],
            status="active",
            is_active=True,
            current_revision_number=1,
        )
        db.add(program)
        db.flush()
        source = _session(db, program, days_ago=7)
        current = _session(db, program, days_ago=0)
        result = headers, user_id, program.id, current.id, source.id
    return result


def _read(client, case):
    response = client.get(f"/api/v1/workouts/{case[3]}/set-history", headers=case[0])
    assert response.status_code == 200, response.text
    assert {value.strip() for value in response.headers["cache-control"].split(",")} == {
        "private",
        "no-store",
    }
    return response.json()


def _sets(db, workout_id):
    return (
        db.query(UserWorkoutSet)
        .join(UserWorkoutExercise)
        .filter(UserWorkoutExercise.workout_id == workout_id)
        .order_by(UserWorkoutSet.set_number)
        .all()
    )


@pytest.mark.parametrize("count", [1, 4, 17])
def test_all_sets_have_their_own_facts_without_prefill(client, case, count):
    with get_session_context() as db:
        for workout_id in case[3:]:
            db.delete(db.get(UserWorkout, workout_id))
        db.flush()
        current = _session(db, db.get(UserProgram, case[2]), days_ago=0, count=count)
        _session(db, db.get(UserProgram, case[2]), days_ago=7, count=count)
        case = (*case[:3], current.id, case[4])
    result = _read(client, case)
    assert len(result["sets"]) == count
    assert all(row["source_template_exercise_id"] == 1132 for row in result["sets"])
    assert len({row["exercise_id"] for row in result["sets"]}) == 1
    assert [row["previous_workout"]["actual_weight"] for row in result["sets"]] == [
        ([160, 180, 200, 190][index - 1] if count == 4 else 140 + 20 * index)
        for index in range(1, count + 1)
    ]
    assert all(row["previous_today"] is None for row in result["sets"])
    with get_session_context() as db:
        assert all(row.actual_weight is None for row in _sets(db, case[3]))


def test_previous_today_uses_only_completed_facts_and_skips_an_unfinished_set(client, case):
    with get_session_context() as db:
        first, second, third, _ = _sets(db, case[3])
        first.actual_weight, first.actual_reps, first.is_completed = 165, 6, True
        second.actual_weight, second.actual_reps = 999, 99
        third.actual_weight, third.actual_reps, third.is_completed = 205, 4, True
    rows = _read(client, case)["sets"]
    assert rows[0]["previous_today"] is None
    assert rows[1]["previous_today"]["actual_weight"] == 165
    assert rows[2]["previous_today"]["set_id"] == rows[0]["set_id"]
    assert rows[2]["previous_workout"]["actual_weight"] == 200
    assert rows[3]["previous_today"]["actual_weight"] == 205


@pytest.mark.parametrize("missing", ["deleted", "unfinished", "no_actuals"])
def test_missing_third_never_uses_neighbours_or_an_older_session(client, case, missing):
    with get_session_context() as db:
        _session(db, db.get(UserProgram, case[2]), days_ago=14)
        item = _sets(db, case[4])[2]
        if missing == "deleted":
            db.delete(item)
        elif missing == "unfinished":
            item.is_completed = False
        else:
            item.actual_weight = item.actual_reps = None
    rows = _read(client, case)["sets"]
    assert [
        row["previous_workout"]["actual_weight"] if row["previous_workout"] else None
        for row in rows
    ] == [160, 180, None, 190]
    assert rows[2]["history_status"] == "no_matching_set"


@pytest.mark.parametrize(
    "field,value",
    [
        ("set_kind", "warmup"),
        ("set_kind", None),
        ("planned_role", "top"),
        ("planned_role", "backoff"),
        ("planned_role", "drop"),
        ("planned_role", None),
        ("planned_position", 2),
        ("planned_group_id", 2),
        ("planned_group_kind", "superset"),
        ("planned_round", 2),
    ],
)
def test_different_set_identity_is_not_a_match(client, case, field, value):
    with get_session_context() as db:
        setattr(_sets(db, case[4])[2], field, value)
    assert _read(client, case)["sets"][2]["previous_workout"] is None


@pytest.mark.parametrize(
    "roles,kind",
    [
        (["warmup", "working", "top", "backoff"], None),
        (["working", "drop", "drop", "drop"], "drop_chain"),
        (["working"] * 4, "superset"),
        (["working"] * 4, "circuit"),
        (["working", "cluster_member", "cluster_member", "cluster_member"], "cluster"),
    ],
)
def test_structured_roles_groups_and_rounds_match_only_the_same_slot(client, case, roles, kind):
    with get_session_context() as db:
        for workout_id in case[3:]:
            db.delete(db.get(UserWorkout, workout_id))
        db.flush()
        current = _session(
            db, db.get(UserProgram, case[2]), days_ago=0, roles=roles, group_kind=kind
        )
        _session(db, db.get(UserProgram, case[2]), days_ago=7, roles=roles, group_kind=kind)
        case = (*case[:3], current.id, case[4])
    assert all(row["previous_workout"] for row in _read(client, case)["sets"])


@pytest.mark.parametrize(
    "change", ["no_history", "in_progress", "missing_timestamp", "later_than_start"]
)
def test_only_an_earlier_completed_session_is_eligible(client, case, change):
    with get_session_context() as db:
        source = db.get(UserWorkout, case[4])
        if change == "no_history":
            db.delete(source)
        elif change == "in_progress":
            source.status = "in_progress"
        elif change == "missing_timestamp":
            source.completed_at = None
            _session(db, db.get(UserProgram, case[2]), days_ago=14)
        else:
            source.completed_at = NOW
    rows = _read(client, case)["sets"]
    assert all(row["previous_workout"] is None for row in rows)
    expected = (
        "identity_unproven"
        if change in {"later_than_start", "missing_timestamp"}
        else "no_previous_workout"
    )
    assert all(row["history_status"] == expected for row in rows)


@pytest.mark.parametrize(
    "change",
    ["exercise", "slot", "day", "program", "null_slot", "null_plan", "order", "count", "per_side"],
)
def test_changed_or_unknown_program_identity_fails_closed(client, case, change):
    with get_session_context() as db:
        source = db.get(UserWorkout, case[4])
        exercise = source.exercises[0]
        if change == "exercise":
            exercise.exercise_id = db.query(Exercise).filter_by(slug="squat").one().id
        elif change == "slot":
            exercise.source_template_exercise_id += 1
        elif change == "day":
            source.day_number = 2
        elif change == "program":
            program = UserProgram(
                user_id=case[1],
                start_date=NOW.date(),
                duration_weeks=1,
                status="completed",
                is_active=False,
                schedule_weekdays=[0],
            )
            db.add(program)
            db.flush()
            source.user_program_id = program.id
        elif change == "null_slot":
            exercise.source_template_exercise_id = None
        elif change == "null_plan":
            exercise.prescription = None
        elif change == "per_side":
            unilateral = db.query(Exercise).filter_by(slug="unilateral-leg-press").one()
            exercise.exercise_id = db.get(UserWorkout, case[3]).exercises[0].exercise_id = (
                unilateral.id
            )
        else:
            plan = deepcopy(exercise.prescription)
            if change == "count":
                plan["segments"].pop()
            else:
                plan["segments"][0]["role"] = "warmup"
            exercise.prescription = plan
    assert all(row["previous_workout"] is None for row in _read(client, case)["sets"])


def test_harmless_revision_and_actual_date_survive_reschedule(client, case):
    with get_session_context() as db:
        source = db.get(UserWorkout, case[4])
        source.scheduled_date = date(2030, 1, 1)
        source.completed_at = datetime(2026, 10, 23, 0, 5)
        current = db.get(UserWorkout, case[3])
        current.scheduled_date = date(2026, 11, 1)
        plan = deepcopy(current.exercises[0].prescription)
        plan["segments"][0]["rep_target"]["value"] = 6
        plan["segments"][0]["load_target"] = {"kind": "absolute", "value": 999}
        current.exercises[0].prescription = plan
        db.get(UserProgram, case[2]).current_revision_number = 2
    result = _read(client, case)
    assert result["program_revision_number"] == 2
    assert result["sets"][0]["previous_workout"]["performed_on"] == "2026-10-23"
    assert result["sets"][0]["previous_workout"]["actual_weight"] == 160


def test_history_is_owner_scoped_even_for_a_coach_and_lineage(client, case):
    stranger = _auth(client, 113201, is_coach=True)
    assert (
        client.get(f"/api/v1/workouts/{case[3]}/set-history", headers=stranger).status_code == 404
    )
    assert client.get(f"/api/v1/workouts/{case[3]}/set-history").status_code == 401
    other_id = client.get("/api/v1/me", headers=stranger).json()["id"]
    with get_session_context() as db:
        other_program = UserProgram(
            user_id=other_id,
            start_date=NOW.date(),
            duration_weeks=1,
            status="active",
            is_active=True,
            schedule_weekdays=[0],
        )
        db.add(other_program)
        db.flush()
        db.get(UserProgram, case[2]).restarted_from_program_id = other_program.id
        source = db.get(UserWorkout, case[4])
        source.user_program_id = other_program.id
    assert all(row["previous_workout"] is None for row in _read(client, case)["sets"])


def test_restart_follows_only_explicit_same_owner_lineage(client, case):
    with get_session_context() as db:
        original = db.get(UserProgram, case[2])
        original.is_active, original.status = False, "completed"
        db.flush()
        restarted = UserProgram(
            user_id=case[1],
            start_date=NOW.date(),
            duration_weeks=16,
            status="active",
            is_active=True,
            schedule_weekdays=[0],
            restarted_from_program_id=original.id,
        )
        db.add(restarted)
        db.flush()
        db.get(UserWorkout, case[3]).user_program_id = restarted.id
    assert all(row["previous_workout"] for row in _read(client, case)["sets"])


@pytest.mark.parametrize("plan_revision,materialized", [(0, True), (1, False)])
def test_repeated_reads_are_one_select_without_materialization_or_side_effects(
    client, case, plan_revision, materialized
):
    with get_session_context() as db:
        current = db.get(UserWorkout, case[3])
        current.source_cycle_week, current.cycle_iteration = 1, 1
        current.plan_revision_number, current.plan_materialized = plan_revision, materialized
        current.status = "planned"
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    with get_session_context() as db:
        user = db.get(User, case[1])
        event.listen(engine, "before_cursor_execute", capture)
        try:
            first = build_workout_set_history(db, user, case[3])
            second = build_workout_set_history(db, user, case[3])
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert first == second
        assert len(statements) == 2
        assert all(
            statement.lstrip().upper().startswith("WITH RECURSIVE") for statement in statements
        )
        assert not db.new and not db.dirty and not db.deleted
    assert all(row["history_status"] == "identity_unproven" for row in first["sets"])
    with get_session_context() as db:
        assert db.get(UserWorkout, case[3]).plan_materialized is materialized


def test_conflict_and_reconnect_reads_observe_facts_without_writing_history(client, case):
    before = _read(client, case)
    target = before["sets"][0]
    change = {
        "actual_weight": 170,
        "actual_reps": 7,
        "is_completed": True,
        "expected_version": target["set_version"],
        "mutation_id": "1132-offline-reconnect",
    }
    path = f"/api/v1/workouts/sets/{target['set_id']}"
    response = client.patch(path, headers=case[0], json=change)
    assert response.status_code == 200, response.text
    stale = client.patch(
        path, headers=case[0], json={**change, "mutation_id": "1132-stale-mutation"}
    )
    assert stale.status_code == 409, stale.text
    after = _read(client, case)
    assert after["sets"][0]["set_version"] == target["set_version"] + 1
    assert after["sets"][1]["previous_today"]["actual_weight"] == 170
    assert after["sets"][0]["previous_workout"] == target["previous_workout"]
    assert _read(client, case) == after


def test_actual_k3_n16_assignment_matches_the_latest_execution_across_cycles(client, monkeypatch):
    from datetime import UTC

    from fitminiapp_api.api.v1 import workouts as routes
    from fitminiapp_api.services import program_versioning, programs, workout_set_history

    day = date(2026, 10, 5)
    monkeypatch.setattr(programs, "today_for_user", lambda _user: day)
    monkeypatch.setattr(program_versioning, "today_for_user", lambda _user: day)
    monkeypatch.setattr(routes, "recovery_today_for_user", lambda _user: day)
    monkeypatch.setattr(
        workout_set_history,
        "now_in_timezone",
        lambda _zone: datetime(day.year, day.month, day.day, 12, tzinfo=UTC),
    )
    headers = _auth(client, 113216)
    exercises = client.get("/api/v1/programs/exercises", headers=headers).json()
    bench = next(item for item in exercises if item["slug"] == "bench-press")
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Цикл 3 на 16 недель",
            "goal": "strength",
            "level": "beginner",
            "assign_after_create": False,
            "week_cycle": {
                "length_weeks": 3,
                "repeat": True,
                "week_types": ["light", "medium", "heavy"],
            },
            "days": [
                {
                    "title": "День",
                    "exercises": [
                        {
                            "exercise_id": bench["id"],
                            "prescribed_sets": 4,
                            "prescribed_reps": "8",
                            "rest_seconds": 90,
                            "prescription": {
                                "version": 1,
                                "metric_type": "strength",
                                "segments": [
                                    {
                                        "position": index,
                                        "role": "working",
                                        "rep_target": {"kind": "exact", "value": 8},
                                    }
                                    for index in range(1, 5)
                                ],
                            },
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    with get_session_context() as db:
        workouts = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id)
            .order_by(UserWorkout.week_number)
            .all()
        )
        assert len(workouts) == 4
        for workout in workouts:
            workout.status = "completed"
            workout.started_at = datetime.combine(workout.scheduled_date, datetime.min.time())
            workout.completed_at = workout.started_at + timedelta(hours=1)
            for item in _sets(db, workout.id):
                item.actual_weight = (
                    [160, 180, 200, 190][item.set_number - 1] if workout.week_number == 4 else 100
                )
                item.actual_reps, item.is_completed = 8, True
        latest_id = workouts[-1].id
        _sets(db, latest_id)[2].is_completed = False
        workouts[-1].scheduled_date = date(2030, 1, 1)
    day += timedelta(weeks=15)
    today = client.get("/api/v1/workouts/today", headers=headers)
    assert today.status_code == 200, today.text
    assert (
        today.json()["week_number"],
        today.json()["source_cycle_week"],
        today.json()["cycle_iteration"],
    ) == (16, 1, 6)
    response = client.get(f"/api/v1/workouts/{today.json()['id']}/set-history", headers=headers)
    assert response.status_code == 200, response.text
    facts = [item["previous_workout"] for item in response.json()["sets"]]
    assert [item["actual_weight"] if item else None for item in facts] == [160, 180, None, 190]
    assert all(item["workout_id"] == latest_id for item in facts if item)
    with get_session_context() as db:
        heavy = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=3).one()
        heavy.started_at, heavy.completed_at = NOW - timedelta(hours=1), NOW
        heavy_id = heavy.id
        assert heavy.source_cycle_week == 3
    cross_type = client.get(f"/api/v1/workouts/{today.json()['id']}/set-history", headers=headers)
    assert cross_type.status_code == 200, cross_type.text
    assert all(
        item["previous_workout"]["workout_id"] == heavy_id for item in cross_type.json()["sets"]
    )
    assert "progression_guidance" not in cross_type.text


@pytest.mark.parametrize(
    "timezone,completed",
    [
        ("Europe/Moscow", datetime(2026, 10, 23, 23, 59)),
        ("Pacific/Kiritimati", datetime(2026, 10, 24, 0, 1)),
        ("America/New_York", datetime(2026, 10, 23, 23, 59)),
    ],
)
def test_actual_completion_date_does_not_use_schedule_or_current_timezone(
    client, case, timezone, completed
):
    with get_session_context() as db:
        db.get(User, case[1]).profile.timezone = timezone
        db.get(UserWorkout, case[4]).completed_at = completed
        db.get(UserWorkout, case[4]).scheduled_date = date(2000, 1, 1)
    fact = _read(client, case)["sets"][0]["previous_workout"]
    assert fact["performed_on"] == completed.date().isoformat()
    assert fact["completed_at"] == completed.isoformat()


@pytest.mark.parametrize("near_target", [True, False])
def test_legacy_timestamps_do_not_guess_order_across_unknown_timezone_changes(
    client, case, near_target
):
    with get_session_context() as db:
        if near_target:
            db.get(UserWorkout, case[4]).completed_at = NOW - timedelta(hours=12)
        else:
            other = _session(db, db.get(UserProgram, case[2]), days_ago=6)
            other.completed_at = NOW - timedelta(days=6)
    assert all(
        row["history_status"] == "identity_unproven" and row["previous_workout"] is None
        for row in _read(client, case)["sets"]
    )


def test_existing_utc_completion_fact_orders_sources_across_calendar_and_timezone_changes(
    client, case
):
    with get_session_context() as db:
        source = db.get(UserWorkout, case[4])
        source.completed_at = datetime(2026, 10, 23, 23, 30)
        source.completed_at_utc = datetime(2026, 10, 24, 6, 30)
        other = _session(db, db.get(UserProgram, case[2]), days_ago=6)
        other.completed_at = datetime(2026, 10, 24, 2)
        other.completed_at_utc = datetime(2026, 10, 23, 23)
    facts = [row["previous_workout"] for row in _read(client, case)["sets"]]
    assert all(fact["workout_id"] == case[4] for fact in facts)
    assert all(fact["performed_on"] == "2026-10-23" for fact in facts)


def test_planned_workout_can_use_a_recent_proven_utc_fact_without_guessing_local_offset(
    client, case, monkeypatch
):
    from datetime import UTC

    from fitminiapp_api.services import workout_set_history

    monkeypatch.setattr(
        workout_set_history, "now_in_timezone", lambda _zone: NOW.replace(tzinfo=UTC)
    )
    with get_session_context() as db:
        current = db.get(UserWorkout, case[3])
        current.status, current.started_at = "planned", None
        source = db.get(UserWorkout, case[4])
        source.completed_at = NOW + timedelta(hours=2)
        source.completed_at_utc = NOW - timedelta(hours=1)
    assert all(row["previous_workout"] for row in _read(client, case)["sets"])


def test_duplicate_slot_and_changed_superset_peer_are_not_proof(client, case):
    with get_session_context() as db:
        for workout_id in case[3:]:
            exercise = db.get(UserWorkout, workout_id).exercises[0]
            exercise.group_id, exercise.group_kind, exercise.group_order = 1, "superset", 1
        original = db.get(UserWorkout, case[4]).exercises[0]
        db.add(
            UserWorkoutExercise(
                workout_id=case[4],
                exercise_id=original.exercise_id,
                source_template_exercise_id=1133,
                sort_order=2,
                prescribed_sets=4,
                prescribed_reps="8",
                group_id=1,
                group_kind="superset",
                group_order=2,
            )
        )
    assert all(row["previous_workout"] is None for row in _read(client, case)["sets"])
    with get_session_context() as db:
        peer = db.get(UserWorkout, case[4]).exercises[1]
        peer.source_template_exercise_id = 1132
    assert all(row["previous_workout"] is None for row in _read(client, case)["sets"])


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Requires PostgreSQL MVCC")
def test_concurrent_commit_cannot_tear_target_versions_and_history_facts(client, case):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    selected = threading.Event()
    reader_thread = threading.get_ident()

    def edit():
        assert selected.wait(timeout=10), "Reader did not execute its snapshot query"
        with get_session_context() as db:
            current = _sets(db, case[3])[0]
            current.actual_weight, current.actual_reps, current.is_completed = 170, 7, True
            current.version += 1
            source = _sets(db, case[4])[0]
            source.actual_weight = 999
            source.version += 1

    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(edit)

        def after_select(_conn, _cursor, statement, _parameters, _context, _many):
            if threading.get_ident() == reader_thread and statement.lstrip().upper().startswith(
                "WITH RECURSIVE"
            ):
                selected.set()
                writer.result(timeout=10)

        with get_session_context() as db:
            user = db.get(User, case[1])
            event.listen(engine, "after_cursor_execute", after_select)
            try:
                before = build_workout_set_history(db, user, case[3])
            finally:
                event.remove(engine, "after_cursor_execute", after_select)
        writer.result(timeout=10)
    after = _read(client, case)
    assert before["sets"][0]["set_version"] == 1
    assert before["sets"][1]["previous_today"] is None
    assert before["sets"][0]["previous_workout"]["actual_weight"] == 160
    assert after["sets"][0]["set_version"] == 2
    assert after["sets"][1]["previous_today"]["actual_weight"] == 170
    assert after["sets"][0]["previous_workout"]["actual_weight"] == 999


def test_history_retains_labeled_side_facts_without_inference(client, case):
    from fitminiapp_api.models.program import UserWorkoutSetSide

    with get_session_context() as db:
        source = _sets(db, case[4])[0]
        source.execution_mode = "per_side"
        source.actual_reps = source.actual_weight = None
        source.side_results = [
            UserWorkoutSetSide(side="left", actual_reps=10, actual_weight=18, is_completed=True),
            UserWorkoutSetSide(side="right", actual_reps=8, actual_weight=16, is_completed=True),
        ]
        current = _sets(db, case[3])[0]
        current.execution_mode = "per_side"
        unilateral = db.query(Exercise).filter_by(slug="unilateral-leg-press").one()
        source.workout_exercise.exercise_id = unilateral.id
        current.workout_exercise.exercise_id = unilateral.id
    result = _read(client, case)["sets"][0]["previous_workout"]
    assert result["execution_mode"] == "per_side"
    assert result["actual_reps"] is None
    assert result["sides"]["left"]["actual_reps"] == 10
    assert result["sides"]["right"]["actual_reps"] == 8


def test_partial_side_remains_visible_after_workout_completion(client, case):
    from fitminiapp_api.models.program import UserWorkoutSetSide

    with get_session_context() as db:
        source = _sets(db, case[4])[0]
        source.execution_mode = "per_side"
        source.actual_reps = source.actual_weight = None
        source.is_completed = False
        source.side_results = [
            UserWorkoutSetSide(side="left", actual_reps=10, actual_weight=18, is_completed=True)
        ]
    result = _read(client, case)["sets"][0]["previous_workout"]
    assert result["is_completed"] is False
    assert result["sides"]["left"]["actual_reps"] == 10
    assert result["sides"]["right"] is None
