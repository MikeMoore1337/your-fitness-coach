from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from test_program_deletion import _assign, _create_template
from test_program_import import _auth, _upload, _weekly_matrix_xlsx

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import SessionLocal, engine, get_session_context
from fitminiapp_api.models.program import ProgramTemplate, UserProgram, UserWorkout
from fitminiapp_api.models.program_import import ProgramImport
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.program_import import ProgramImportAssignmentRequest
from fitminiapp_api.services import program_imports
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.program_versioning import _cycle_workout_plans


def _ready_import(client, headers, *, weeks=1, duration=1, repeat=False):
    uploaded = _upload(client, headers, "synthetic.xlsx", _weekly_matrix_xlsx(weeks=weeks))
    assert uploaded.status_code == 201, uploaded.text
    draft = uploaded.json()
    resolved = client.post(
        f"/api/v1/programs/imports/{draft['id']}/resolve",
        headers=headers,
        json={
            "expected_draft_version": draft["draft_version"],
            "title": "Импортированная программа",
            "goal": "maintenance",
            "level": "intermediate",
            "assignment_duration_weeks": duration,
            "repeat": repeat,
            "week_types": [None] * weeks,
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["summary"]["blocking_issue_count"] == 0
    return resolved.json()


def _save(client, headers, draft):
    response = client.post(
        f"/api/v1/programs/imports/{draft['id']}/confirm",
        headers=headers,
        json={"expected_draft_version": draft["draft_version"]},
    )
    assert response.status_code == 200, response.text
    return response.json()["template"]["id"]


def _payload(*, duration=1, active_id=None, revision=None, start_date=None):
    return {
        "duration_weeks": duration,
        "start_date": start_date,
        "schedule_weekdays": None,
        "replace_active": active_id is not None,
        "expected_active_program_id": active_id,
        "expected_active_revision_number": revision,
    }


@pytest.mark.parametrize(
    ("weeks", "duration", "repeat"), [(1, 16, True), (3, 16, True), (12, 12, False)]
)
def test_saved_import_can_be_assigned_once_and_recovered(client, weeks, duration, repeat):
    headers = _auth(client, 138_100 + weeks)
    draft = _ready_import(client, headers, weeks=weeks, duration=duration, repeat=repeat)
    template_id = _save(client, headers, draft)
    replay_save = _save(client, headers, draft)
    assert replay_save == template_id
    with get_session_context() as db:
        owner = db.query(User).filter_by(telegram_user_id=138_100 + weeks).one()
        assert db.query(UserProgram).filter_by(user_id=owner.id).count() == 0

    payload = _payload(duration=duration, start_date=(today_msk() + timedelta(days=7)).isoformat())
    url = f"/api/v1/programs/imports/{draft['id']}/assign-to-me"
    assigned = client.post(url, headers=headers, json=payload)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["status"] == "scheduled"
    assigned_id = assigned.json()["user_program_id"]
    assert client.post(url, headers=headers, json=payload).json()["user_program_id"] == assigned_id
    assert (
        client.post(url, headers=headers, json={**payload, "duration_weeks": 1}).status_code == 409
    )
    recovered = client.get(f"/api/v1/programs/imports/{draft['id']}", headers=headers)
    assert recovered.json()["confirmed_template_id"] == template_id
    assert recovered.json()["self_assigned_program_id"] == assigned_id
    with get_session_context() as db:
        row = db.get(ProgramImport, draft["id"])
        assert row.confirmed_program_id is None
        assert row.self_assigned_program_id == assigned_id
        assert (
            db.query(UserProgram)
            .filter_by(user_id=row.owner_user_id, template_id=template_id)
            .count()
            == 1
        )
        assert db.query(ProgramTemplate).filter_by(id=template_id).count() == 1
        assert all(
            workout.status != "completed" for workout in db.get(UserProgram, assigned_id).workouts
        )
        program = db.get(UserProgram, assigned_id)
        if repeat:
            for week in {1, min(duration, 4), duration}:
                plans = _cycle_workout_plans(db, program, week)
                assert {plan["source_cycle_week"] for plan in plans} == {((week - 1) % weeks) + 1}
                assert {plan["cycle_iteration"] for plan in plans} == {((week - 1) // weeks) + 1}
        else:
            assert {workout.week_number for workout in program.workouts} == set(range(1, weeks + 1))
            for week in {1, min(duration, 4), duration}:
                workout = next(
                    item
                    for item in program.workouts
                    if item.week_number == week and item.day_number == 1
                )
                exercise = workout.exercises[0]
                source = next(
                    item
                    for item in program.template.days[0].exercises
                    if item.id == exercise.source_template_exercise_id
                )
                prescription = next(
                    item for item in source.weekly_prescriptions if item.week_number == week
                )
                assert exercise.prescribed_reps == prescription.prescribed_reps

    other = _auth(client, 139_100 + weeks)
    assert client.get(f"/api/v1/programs/imports/{draft['id']}", headers=other).status_code == 404
    assert client.post(url, headers=other, json=payload).status_code == 404


def test_replacement_checks_snapshot_and_preserves_completed_facts(client):
    headers = _auth(client, 138_210)
    old_id = _assign(client, headers, _create_template(client, headers, "Текущая программа"))
    draft = _ready_import(client, headers)
    template_id = _save(client, headers, draft)
    url = f"/api/v1/programs/imports/{draft['id']}/assign-to-me"
    with get_session_context() as db:
        old = db.get(UserProgram, old_id)
        old.workouts[0].status = "completed"
        completed = old.workouts[0].exercises[0].sets[0]
        completed.actual_reps, completed.actual_weight, completed.is_completed = 8, 20, True
        workout_id, set_id, revision = old.workouts[0].id, completed.id, old.current_revision_number
        db.commit()
    assert client.post(url, headers=headers, json=_payload()).status_code == 409
    assert (
        client.post(
            url, headers=headers, json=_payload(active_id=old_id, revision=revision + 1)
        ).status_code
        == 409
    )
    assert (
        client.get(f"/api/v1/programs/imports/{draft['id']}", headers=headers).json()[
            "confirmed_template_id"
        ]
        == template_id
    )
    assigned = client.post(url, headers=headers, json=_payload(active_id=old_id, revision=revision))
    assert assigned.status_code == 200, assigned.text
    with get_session_context() as db:
        old = db.get(UserProgram, old_id)
        workout = db.get(UserWorkout, workout_id)
        completed = next(
            item for exercise in workout.exercises for item in exercise.sets if item.id == set_id
        )
        assert old.status == "archived" and not old.is_active
        assert (
            workout.status,
            completed.actual_reps,
            float(completed.actual_weight),
            completed.is_completed,
        ) == ("completed", 8, 20.0, True)


@pytest.mark.parametrize("blocker", ["in_progress", "trainer"])
def test_replacement_blockers_keep_both_template_and_current_program(client, blocker):
    headers = _auth(client, 138_220)
    old_id = _assign(client, headers, _create_template(client, headers, "Текущая программа"))
    if blocker == "trainer":
        _auth(client, 138_221, is_coach=True)
    draft = _ready_import(client, headers)
    template_id = _save(client, headers, draft)
    with get_session_context() as db:
        old = db.get(UserProgram, old_id)
        revision = old.current_revision_number
        if blocker == "in_progress":
            old.workouts[0].status = "in_progress"
        else:
            old.assigned_by_user_id = db.query(User.id).filter_by(telegram_user_id=138_221).scalar()
        db.commit()
    response = client.post(
        f"/api/v1/programs/imports/{draft['id']}/assign-to-me",
        headers=headers,
        json=_payload(active_id=old_id, revision=revision),
    )
    assert response.status_code == (409 if blocker == "in_progress" else 403), response.text
    assert response.json()["detail"]["code"] == (
        "workout_in_progress" if blocker == "in_progress" else "trainer_owned_program"
    )
    with get_session_context() as db:
        assert db.get(UserProgram, old_id).is_active
        assert db.get(ProgramTemplate, template_id) is not None
        assert db.get(ProgramImport, draft["id"]).self_assigned_program_id is None


def test_assignment_rolls_back_after_domain_write_but_keeps_saved_template(client, monkeypatch):
    headers = _auth(client, 138_230)
    old_id = _assign(client, headers, _create_template(client, headers, "Текущая программа"))
    draft = _ready_import(client, headers)
    template_id = _save(client, headers, draft)
    with get_session_context() as db:
        revision = db.get(UserProgram, old_id).current_revision_number
    original = program_imports.assign_template_to_self

    def fail_after_assignment(*args, **kwargs):
        original(*args, **kwargs)
        raise ProgramError("Cannot replace a program while a workout is in progress")

    monkeypatch.setattr(program_imports, "assign_template_to_self", fail_after_assignment)
    response = client.post(
        f"/api/v1/programs/imports/{draft['id']}/assign-to-me",
        headers=headers,
        json=_payload(active_id=old_id, revision=revision),
    )
    assert response.status_code == 409
    with get_session_context() as db:
        assert db.get(UserProgram, old_id).is_active
        assert db.get(ProgramTemplate, template_id) is not None
        assert db.get(ProgramImport, draft["id"]).self_assigned_program_id is None
        assert db.query(UserProgram).filter_by(template_id=template_id).count() == 0


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_assignment_replays_one_result(client):
    headers = _auth(client, 138_240)
    draft = _ready_import(client, headers)
    template_id = _save(client, headers, draft)
    barrier = Barrier(2)
    payload = ProgramImportAssignmentRequest.model_validate(_payload())

    def assign():
        with SessionLocal() as db:
            owner = db.query(User).filter_by(telegram_user_id=138_240).one()
            barrier.wait(timeout=10)
            return program_imports.assign_confirmed_program_import(
                db, owner, draft["id"], payload
            ).id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: assign(), range(2)))
    assert results[0] == results[1]
    with get_session_context() as db:
        assert db.query(UserProgram).filter_by(template_id=template_id).count() == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_confirmation_creates_one_template(client):
    headers = _auth(client, 138_250)
    draft = _ready_import(client, headers)
    barrier = Barrier(2)

    def confirm():
        with SessionLocal() as db:
            owner = db.query(User).filter_by(telegram_user_id=138_250).one()
            barrier.wait(timeout=10)
            return program_imports.confirm_program_import(
                db, owner, draft["id"], expected_draft_version=draft["draft_version"]
            )[1].id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: confirm(), range(2)))
    assert results[0] == results[1]
    with get_session_context() as db:
        assert db.query(ProgramTemplate).filter_by(id=results[0]).count() == 1
        assert db.get(ProgramImport, draft["id"]).confirmed_template_id == results[0]
