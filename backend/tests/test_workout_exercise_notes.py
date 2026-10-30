from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from test_program_week_cycle import _auth
from test_workout_set_history import _session

from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.models.workout_exercise_note import (
    WorkoutExerciseNote,
    WorkoutExerciseNoteMutation,
)
from fitminiapp_api.schemas.workout_exercise_note import ExerciseNoteWrite
from fitminiapp_api.services.account_export import build_account_export
from fitminiapp_api.services.accounts import delete_user_cascade
from fitminiapp_api.services.workout_exercise_notes import ExerciseNoteError, write_exercise_note


@pytest.fixture
def case(client):
    headers = _auth(client, 995001)
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
        old = _session(db, program, days_ago=14)
        recent = _session(db, program, days_ago=7)
        current = _session(db, program, days_ago=0)
        result = {
            "headers": headers,
            "user_id": user_id,
            "program_id": program.id,
            "old": old.id,
            "old_ex": old.exercises[0].id,
            "recent": recent.id,
            "recent_ex": recent.exercises[0].id,
            "current": current.id,
            "current_ex": current.exercises[0].id,
        }
    return result


def _url(workout_id, exercise_id):
    return f"/api/v1/workouts/{workout_id}/exercise-notes/{exercise_id}"


def _read(client, case, workout="current", exercise="current_ex"):
    response = client.get(_url(case[workout], case[exercise]), headers=case["headers"])
    assert response.status_code == 200, response.text
    assert {part.strip() for part in response.headers["cache-control"].split(",")} == {
        "private",
        "no-store",
    }
    return response.json()


def _payload(data, mutation_id, **content):
    fields = [
        "exercise_id",
        "source_template_exercise_id",
        "plan_revision_number",
        "week_number",
        "day_number",
        "source_cycle_week",
        "cycle_iteration",
    ]
    return {
        **{key: data[key] for key in fields},
        "expected_version": data["version"],
        "mutation_id": mutation_id,
        **content,
    }


def test_note_history_uses_its_own_workout_and_preserves_set_history(client, case):
    old = _read(client, case, "old", "old_ex")
    response = client.put(
        _url(case["old"], case["old_ex"]),
        headers=case["headers"],
        json=_payload(
            old, "old-1", body="100 кг легко, попробовать 105", tags=["easy", "increase_weight"]
        ),
    )
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        recent_set = (
            db.query(UserWorkoutSet)
            .filter_by(workout_exercise_id=case["recent_ex"], set_number=4)
            .one()
        )
        recent_set.actual_weight = 77
        db.get(UserWorkout, case["current"]).completion_note = "Общая заметка"
    history_before = client.get(
        f"/api/v1/workouts/{case['current']}/set-history", headers=case["headers"]
    ).json()
    current = _read(client, case)
    previous = current["previous_note"]
    assert previous["body"] == "100 кг легко, попробовать 105"
    assert previous["tags"] == ["easy", "increase_weight"]
    assert previous["workout_id"] == case["old"]
    assert previous["completed_on"] == "2026-10-16"
    assert previous["load"]["actual_weight"] == 190
    assert history_before["sets"][3]["previous_workout"]["actual_weight"] == 77
    saved = client.put(
        _url(case["current"], case["current_ex"]),
        headers=case["headers"],
        json=_payload(current, "current-1", body="Сегодня тяжело", tags=["hard"]),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["current_note"]["body"] == "Сегодня тяжело"
    assert (
        client.get(
            f"/api/v1/workouts/{case['current']}/set-history", headers=case["headers"]
        ).json()
        == history_before
    )
    with get_session_context() as db:
        assert db.get(UserWorkout, case["current"]).completion_note == "Общая заметка"
        assert all(
            item.actual_weight is None
            for item in db.query(UserWorkoutSet)
            .filter_by(workout_exercise_id=case["current_ex"])
            .all()
        )


def test_version_idempotency_delete_and_validation(client, case):
    current = _read(client, case)
    path = _url(case["current"], case["current_ex"])
    payload = _payload(current, "request-1", body="Легко", tags=["easy"])
    first = client.put(path, headers=case["headers"], json=payload)
    assert first.status_code == 200, first.text
    replay = client.put(path, headers=case["headers"], json=payload)
    assert replay.status_code == 200 and replay.json()["version"] == 1
    reused = client.put(path, headers=case["headers"], json={**payload, "body": "Иначе"})
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "exercise_note_idempotency_conflict"
    stale = client.put(path, headers=case["headers"], json={**payload, "mutation_id": "stale"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["current"]["note"]["body"] == "Легко"
    empty = client.put(
        path, headers=case["headers"], json=_payload(first.json(), "empty", body=" ", tags=[])
    )
    assert empty.status_code == 422
    too_long = client.put(
        path, headers=case["headers"], json=_payload(first.json(), "long", body="я" * 501, tags=[])
    )
    assert too_long.status_code == 422
    deletion = _payload(first.json(), "delete")
    removed = client.request("DELETE", path, headers=case["headers"], json=deletion)
    assert removed.status_code == 200 and removed.json()["current_note"] is None
    replay_delete = client.request("DELETE", path, headers=case["headers"], json=deletion)
    assert replay_delete.status_code == 200 and replay_delete.json()["version"] == 2
    created_again = client.put(
        path,
        headers=case["headers"],
        json=_payload(removed.json(), "new", body=None, tags=["increase_weight"]),
    )
    assert created_again.status_code == 200
    assert created_again.json()["current_note"]["tags"] == ["increase_weight"]


def test_owner_boundary_and_replacement_do_not_move_note(client, case):
    current = _read(client, case)
    payload = _payload(current, "before-replacement", body="Личный текст", tags=["easy"])
    path = _url(case["current"], case["current_ex"])
    assert client.put(path, headers=case["headers"], json=payload).status_code == 200
    outsider = _auth(client, 995002)
    assert client.get(path, headers=outsider).status_code == 404
    assert client.put(path, headers=outsider, json=payload).status_code == 404
    assert client.get(path).status_code == 401
    with get_session_context() as db:
        item = db.get(UserWorkoutExercise, case["current_ex"])
        other = db.query(Exercise).filter(Exercise.id != item.exercise_id).first()
        item.exercise_id = other.id
    stale = client.put(
        path, headers=case["headers"], json={**payload, "mutation_id": "offline-replay"}
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "exercise_note_identity_changed"
    after = _read(client, case)
    assert after["current_note"] is None and after["previous_note"] is None
    with get_session_context() as db:
        assert (
            db.query(WorkoutExerciseNote).filter_by(workout_id=case["current"]).one().body
            == "Личный текст"
        )


def test_duplicate_program_slot_and_context_revision_fail_closed(client, case):
    old = _read(client, case, "old", "old_ex")
    assert (
        client.put(
            _url(case["old"], case["old_ex"]),
            headers=case["headers"],
            json=_payload(old, "old", body="Легко", tags=[]),
        ).status_code
        == 200
    )
    assert _read(client, case)["previous_note"] is not None
    with get_session_context() as db:
        current = db.get(UserWorkout, case["current"])
        original = db.get(UserWorkoutExercise, case["current_ex"])
        db.add(
            UserWorkoutExercise(
                workout_id=current.id,
                exercise_id=original.exercise_id,
                source_template_exercise_id=original.source_template_exercise_id,
                metric_type="strength",
                sort_order=2,
                prescribed_sets=1,
                prescribed_reps="8",
            )
        )
    assert _read(client, case)["previous_note"] is None
    stale = _payload(_read(client, case), "wrong-week", body="Текст", tags=[])
    stale["week_number"] += 1
    result = client.put(
        _url(case["current"], case["current_ex"]), headers=case["headers"], json=stale
    )
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "exercise_note_identity_changed"


def test_removed_occurrence_preserves_note_until_workout_is_deleted(client, case):
    current = _read(client, case)
    path = _url(case["current"], case["current_ex"])
    assert (
        client.put(
            path, headers=case["headers"], json=_payload(current, "keep", body="Записано", tags=[])
        ).status_code
        == 200
    )
    with get_session_context() as db:
        exercise = db.get(UserWorkoutExercise, case["current_ex"])
        db.delete(exercise)
        db.flush()
        assert (
            db.query(WorkoutExerciseNote).filter_by(workout_id=case["current"]).one().body
            == "Записано"
        )
    assert client.get(path, headers=case["headers"]).status_code == 404
    list_path = f"/api/v1/workouts/{case['current']}/exercise-notes"
    history = client.get(list_path, headers=case["headers"])
    assert history.status_code == 200 and len(history.json()) == 1
    note = history.json()[0]
    assert note["body"] == "Записано" and note["workout_exercise_id"] == case["current_ex"]
    history_path = f"/api/v1/workouts/exercise-notes/history/{note['id']}"
    outsider = _auth(client, 995003)
    assert client.get(list_path, headers=outsider).status_code == 404
    assert client.get(history_path, headers=outsider).status_code == 404
    payload = {
        "expected_version": note["version"],
        "mutation_id": "historic-edit",
        "body": "Исправлено",
        "tags": ["easy"],
    }
    assert client.put(history_path, headers=outsider, json=payload).status_code == 404
    changed = client.put(history_path, headers=case["headers"], json=payload)
    assert changed.status_code == 200 and changed.json()["current_note"]["body"] == "Исправлено"
    assert client.put(history_path, headers=case["headers"], json=payload).json()["version"] == 2
    stale = client.put(
        history_path, headers=case["headers"], json={**payload, "mutation_id": "historic-stale"}
    )
    assert stale.status_code == 409
    delete_payload = {"expected_version": 2, "mutation_id": "historic-delete"}
    deleted = client.request("DELETE", history_path, headers=case["headers"], json=delete_payload)
    assert deleted.status_code == 200 and deleted.json()["current_note"] is None
    assert (
        client.request("DELETE", history_path, headers=case["headers"], json=delete_payload).json()[
            "version"
        ]
        == 3
    )
    assert client.get(list_path, headers=case["headers"]).json() == []
    assert client.get(history_path, headers=case["headers"]).json() == {
        "version": 3,
        "current_note": None,
    }


def test_previous_note_survives_missing_load(client, case):
    old = _read(client, case, "old", "old_ex")
    assert (
        client.put(
            _url(case["old"], case["old_ex"]),
            headers=case["headers"],
            json=_payload(old, "without-load", body="Записано", tags=[]),
        ).status_code
        == 200
    )
    with get_session_context() as db:
        db.query(UserWorkoutSet).filter_by(workout_exercise_id=case["old_ex"]).update(
            {"is_completed": False}
        )
    previous = _read(client, case)["previous_note"]
    assert previous["body"] == "Записано" and previous["load"] is None


def test_same_exercise_in_distinct_slots_keeps_separate_history(client, case):
    with get_session_context() as db:
        for workout_id in (case["old"], case["current"]):
            original = db.query(UserWorkoutExercise).filter_by(workout_id=workout_id).one()
            duplicate = UserWorkoutExercise(
                workout_id=workout_id,
                exercise_id=original.exercise_id,
                source_template_exercise_id=original.source_template_exercise_id + 1,
                metric_type="strength",
                sort_order=2,
                prescribed_sets=1,
                prescribed_reps="8",
            )
            db.add(duplicate)
            db.flush()
            case["other_old" if workout_id == case["old"] else "other_current"] = duplicate.id
    for occurrence, text in ((case["old_ex"], "Первое место"), (case["other_old"], "Второе место")):
        state = client.get(_url(case["old"], occurrence), headers=case["headers"]).json()
        assert (
            client.put(
                _url(case["old"], occurrence),
                headers=case["headers"],
                json=_payload(state, f"slot-{occurrence}", body=text, tags=[]),
            ).status_code
            == 200
        )
    assert _read(client, case)["previous_note"]["body"] == "Первое место"
    other = client.get(_url(case["current"], case["other_current"]), headers=case["headers"]).json()
    assert other["previous_note"]["body"] == "Второе место"


def test_program_lineage_is_required_for_previous_note(client, case):
    old = _read(client, case, "old", "old_ex")
    assert (
        client.put(
            _url(case["old"], case["old_ex"]),
            headers=case["headers"],
            json=_payload(old, "lineage", body="Старая программа", tags=[]),
        ).status_code
        == 200
    )
    with get_session_context() as db:
        db.get(UserProgram, case["program_id"]).is_active = False
        db.flush()
        other = UserProgram(
            user_id=case["user_id"],
            start_date=date(2026, 10, 1),
            duration_weeks=16,
            schedule_weekdays=[0],
            status="active",
            is_active=True,
            current_revision_number=1,
        )
        db.add(other)
        db.flush()
        db.get(UserWorkout, case["current"]).user_program_id = other.id
        other_id = other.id
    assert _read(client, case)["previous_note"] is None
    with get_session_context() as db:
        db.get(UserProgram, other_id).restarted_from_program_id = case["program_id"]
    assert _read(client, case)["previous_note"]["body"] == "Старая программа"


@pytest.mark.parametrize(
    "field,value",
    [
        ("exercise_id", 999999),
        ("source_template_exercise_id", 999999),
        ("plan_revision_number", 99),
        ("week_number", 99),
        ("day_number", 99),
        ("source_cycle_week", 99),
        ("cycle_iteration", 99),
    ],
)
def test_offline_replay_rejects_changed_identity(client, case, field, value):
    current = _read(client, case)
    payload = _payload(current, f"stale-{field}", body="Не переносить", tags=["hard"])
    payload[field] = value
    result = client.put(
        _url(case["current"], case["current_ex"]), headers=case["headers"], json=payload
    )
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "exercise_note_identity_changed"
    assert _read(client, case)["current_note"] is None


def test_account_export_contains_only_owned_notes_and_no_mutation_keys(client, case):
    current = _read(client, case)
    assert (
        client.put(
            _url(case["current"], case["current_ex"]),
            headers=case["headers"],
            json=_payload(current, "private-mutation", body="Личная запись", tags=["hard"]),
        ).status_code
        == 200
    )
    with get_session_context() as db:
        payload = build_account_export(db, db.get(User, case["user_id"]))
        program = next(item for item in payload["programs"] if item["id"] == case["program_id"])
        workout = next(item for item in program["workouts"] if item["id"] == case["current"])
        note = workout["exercise_notes"][0]
        assert note["body"] == "Личная запись" and note["tags"] == ["hard"]
        assert "mutation_id" not in note and "context_key" not in note
        outsider = db.query(User).filter(User.id != case["user_id"]).first()
        assert "Личная запись" not in str(build_account_export(db, outsider))


def test_assigned_coach_cannot_read_or_modify_private_note(client, case):
    current = _read(client, case)
    saved = client.put(
        _url(case["current"], case["current_ex"]),
        headers=case["headers"],
        json=_payload(current, "athlete-only", body="Личное наблюдение", tags=[]),
    ).json()
    coach_headers = _auth(client, 995009)
    coach_id = client.get("/api/v1/me", headers=coach_headers).json()["id"]
    with get_session_context() as db:
        db.get(User, coach_id).is_coach = True
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=case["user_id"], status="active"))
    path = _url(case["current"], case["current_ex"])
    history_path = f"/api/v1/workouts/exercise-notes/history/{saved['current_note']['id']}"
    assert client.get(path, headers=coach_headers).status_code == 404
    assert client.get(history_path, headers=coach_headers).status_code == 404
    assert (
        client.put(
            history_path,
            headers=coach_headers,
            json={
                "expected_version": 1,
                "mutation_id": "coach-edit",
                "body": "Чужое изменение",
                "tags": [],
            },
        ).status_code
        == 404
    )
    assert _read(client, case)["current_note"]["body"] == "Личное наблюдение"


def test_account_deletion_removes_note_and_mutations(client, case):
    current = _read(client, case)
    assert (
        client.put(
            _url(case["current"], case["current_ex"]),
            headers=case["headers"],
            json=_payload(current, "delete-account-note", body="Личный текст", tags=[]),
        ).status_code
        == 200
    )
    with get_session_context() as db:
        delete_user_cascade(db, db.get(User, case["user_id"]))
        db.flush()
        assert db.query(WorkoutExerciseNote).filter_by(workout_id=case["current"]).count() == 0
        assert db.query(WorkoutExerciseNoteMutation).filter_by(user_id=case["user_id"]).count() == 0


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_mutations_and_identical_replays_are_serialized(client, case):
    current = _read(client, case)
    barrier = Barrier(2)

    def submit(payload):
        with get_session_context() as db:
            user = db.get(User, case["user_id"])
            barrier.wait(timeout=10)
            try:
                return write_exercise_note(
                    db,
                    user,
                    case["current"],
                    case["current_ex"],
                    ExerciseNoteWrite.model_validate(payload),
                )["version"]
            except ExerciseNoteError as error:
                return error.status_code

    replay = _payload(current, "concurrent-replay", body="Один раз", tags=[])
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, (replay, replay))) == [1, 1]
    current = _read(client, case)
    first = _payload(current, "concurrent-a", body="Первый", tags=[])
    second = _payload(current, "concurrent-b", body="Второй", tags=[])
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, (first, second))) == [2, 409]
    assert _read(client, case)["version"] == 2
