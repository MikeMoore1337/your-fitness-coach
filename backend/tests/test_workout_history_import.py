from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from test_training_analytics import _auth, _user_id
from test_workout_history_import_parser import _csv, _row

from fitminiapp_api.api.v1.workout_rest import _validate_source_set
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import (
    TrainingBlock,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.models.workout_history_import import ImportedWorkout, WorkoutHistoryImportDraft
from fitminiapp_api.services.account_export import build_account_export
from fitminiapp_api.services.accounts import delete_user_cascade
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.program_versioning import _lifecycle_block_summary
from fitminiapp_api.services.progression_guidance import (
    _progression_set_selection,
    build_progression_guidance,
)
from fitminiapp_api.services.training_preferences import _estimated_minutes
from fitminiapp_api.services.workout_history_import import expire_history_import_drafts

URL = "/api/v1/workout-history-imports"


def _upload(client, headers, *rows):
    response = client.post(
        URL, headers=headers, files={"file": ("history.csv", _csv(*rows), "text/csv")}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _confirm(client, headers, preview):
    return client.post(
        f"{URL}/{preview['id']}/confirm",
        headers=headers,
        json={"version": preview["version"], "preview_signature": preview["preview_signature"]},
    )


def test_import_confirmation_is_atomic_idempotent_and_visible_in_history_and_export(client):
    headers = _auth(client, 833_001)
    other_headers = _auth(client, 833_002)
    preview = _upload(client, headers, _row(exercise_name="barbell bench press"))
    assert preview["rows"][0]["match_status"] == "matched"
    assert preview["rows"][0]["blocking_issues"] == []
    assert (
        client.get("/api/v1/workouts/history/summary", headers=headers).json()["workouts_completed"]
        == 0
    )
    assert client.get(f"{URL}/{preview['id']}", headers=other_headers).status_code == 404
    assert _confirm(client, other_headers, preview).status_code == 404
    assert client.get(URL).status_code in {401, 403}

    result = _confirm(client, headers, preview)
    assert result.status_code == 200, result.text
    receipt = result.json()["result"]
    assert receipt["workout_count"] == 1 and receipt["set_count"] == 1
    assert _confirm(client, headers, preview).json()["result"] == receipt
    for action in ("start", "skip"):
        response = client.post(
            f"/api/v1/workouts/{receipt['workout_ids'][0]}/{action}", headers=headers
        )
        assert response.status_code == 404
    history = client.get("/api/v1/workouts/history", headers=headers).json()
    assert history[0]["is_imported"] is True
    assert history[0]["exercises"][0]["prescribed_sets"] is None
    assert history[0]["exercises"][0]["prescribed_reps"] is None
    assert client.get("/api/v1/workouts/history/summary", headers=headers).json() == {
        "workouts_completed": 1,
        "completed_sets": 1,
        "volume_kg": 362.88,
    }
    exercise_id = preview["rows"][0]["exercise_id"]
    exercise_history = client.get(
        f"/api/v1/programs/exercises/{exercise_id}/history", headers=headers
    )
    assert exercise_history.status_code == 200, exercise_history.text
    assert exercise_history.json()["recent_sessions"][0]["sets"][0]["load_kg"] == 45.36
    assert (
        client.get("/api/v1/workouts/history/summary", headers=other_headers).json()[
            "workouts_completed"
        ]
        == 0
    )
    progress = client.get(
        "/api/v1/workouts/progress/summary?date_from=2025-10-12&date_to=2025-10-12",
        headers=headers,
    )
    assert progress.status_code == 200, progress.text
    assert progress.json()["training"]["completed_workouts"] == 1
    assert progress.json()["training"]["planned_workouts"] == 0
    assert progress.json()["training"]["volume_kg"] == 362.88
    assert progress.json()["adherence"]["workouts"]["status"] == "not_applicable"
    with get_session_context() as db:
        workout = db.get(UserWorkout, receipt["workout_ids"][0])
        assert (
            workout.user_program_id is None
            and workout.day_number is None
            and workout.week_number is None
        )
        assert workout.exercises[0].rest_seconds is None
        assert workout.exercises[0].sets[0].actual_weight == Decimal("45.36")
        with pytest.raises(HTTPException) as rest_error:
            _validate_source_set(workout.exercises[0].sets[0], workout.exercises[0])
        assert rest_error.value.status_code == 422
        with pytest.raises(ValueError, match="Missing planned exercise parameters"):
            _estimated_minutes(workout.exercises)
        owner = db.get(User, _user_id(833_001))
        assert (
            _progression_set_selection(workout.exercises[0]).reason_code == "invalid_prescription"
        )
        assert build_progression_guidance(db, owner, workout) == {}
        block = TrainingBlock(start_date=workout.scheduled_date, end_date=workout.scheduled_date)
        with pytest.raises(ProgramError, match="нет данных плана"):
            _lifecycle_block_summary(block, [workout])
        exported = build_account_export(db, owner)["imported_workouts"]
        assert len(exported) == 1 and exported[0]["source_timezone"] == "Europe/Moscow"
        assert exported[0]["exercises"][0]["sets"][0]["actual_reps"] == 8
    again = _upload(client, headers, _row(exercise_name="barbell bench press"))
    assert again["duplicates"][0]["candidates"][0]["kind"] == "exact"
    denied = _confirm(client, headers, again)
    assert denied.status_code == 409
    assert (
        client.get("/api/v1/workouts/history/summary", headers=headers).json()["workouts_completed"]
        == 1
    )


def test_unresolved_and_unsupported_rows_cannot_change_history(client):
    headers = _auth(client, 833_003)
    preview = _upload(
        client,
        headers,
        _row(exercise_name="Неизвестное упражнение", rpe="8", side="left"),
        _row(exercise_name="Неизвестное упражнение", set_number="2"),
    )
    assert preview["rows"][0]["source"]["rpe"] == "8"
    assert preview["rows"][0]["source"]["side"] == "left"
    assert {issue["code"] for issue in preview["rows"][0]["blocking_issues"]} >= {
        "unsupported_rpe",
        "unsupported_side",
        "exercise_unresolved",
    }
    assert _confirm(client, headers, preview).status_code == 409
    with get_session_context() as db:
        exercise_id = db.query(Exercise.id).filter_by(slug="bench-press").scalar()
    resolved = client.post(
        f"{URL}/{preview['id']}/resolve",
        headers=headers,
        json={
            "version": 1,
            "exercise_choices": {str(preview["rows"][0]["line"]): exercise_id},
            "excluded_lines": [preview["rows"][0]["line"]],
            "duplicate_choices": {},
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert _confirm(client, headers, preview).status_code == 409
    result = _confirm(client, headers, resolved.json())
    assert result.status_code == 200, result.text
    assert result.json()["result"]["set_count"] == 1


def test_partial_duplicate_requires_decision_and_stale_preview_fails(client):
    headers = _auth(client, 833_004)
    first = _upload(client, headers, _row(exercise_name="barbell bench press"))
    second = _upload(client, headers, _row(exercise_name="barbell bench press", reps="9"))
    assert _confirm(client, headers, first).status_code == 200
    stale = _confirm(client, headers, second)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "preview_changed"
    refreshed = client.get(f"{URL}/{second['id']}", headers=headers).json()
    assert refreshed["duplicates"][0]["candidates"][0]["kind"] == "possible"
    assert _confirm(client, headers, refreshed).status_code == 409
    ref = refreshed["duplicates"][0]["workout_ref"]
    resolved = client.post(
        f"{URL}/{second['id']}/resolve",
        headers=headers,
        json={
            "version": refreshed["version"],
            "exercise_choices": {},
            "excluded_lines": [],
            "duplicate_choices": {ref: "keep"},
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert _confirm(client, headers, resolved.json()).status_code == 200
    assert (
        client.get("/api/v1/workouts/history/summary", headers=headers).json()["workouts_completed"]
        == 2
    )


def test_expiry_clears_normalized_source_and_account_deletion_removes_facts(client):
    headers = _auth(client, 833_005)
    preview = _upload(client, headers, _row(exercise_name="barbell bench press"))
    other = _upload(client, headers, _row(workout_ref="later", exercise_name="barbell bench press"))
    assert _confirm(client, headers, preview).status_code == 200
    user_id = _user_id(833_005)
    with get_session_context() as db:
        draft = db.get(WorkoutHistoryImportDraft, other["id"])
        draft.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db.flush()
        expire_history_import_drafts(db)
        assert draft.status == "expired" and draft.draft_json is None
        user = db.get(User, user_id)
        delete_user_cascade(db, user)
        db.flush()
        assert db.query(ImportedWorkout).filter_by(owner_user_id=user_id).count() == 0
        assert db.query(UserWorkout).filter(UserWorkout.user_program_id.is_(None)).count() == 0
        assert db.query(WorkoutHistoryImportDraft).filter_by(owner_user_id=user_id).count() == 0


def test_confirm_rolls_back_all_facts_and_draft_after_interruption(client):
    from fitminiapp_api.services.workout_history_import import confirm_history_import

    headers = _auth(client, 833_006)
    preview = _upload(client, headers, _row(exercise_name="barbell bench press"))
    user_id = _user_id(833_006)
    with pytest.raises(RuntimeError, match="injected failure"), get_session_context() as db:
        user = db.get(User, user_id)
        confirm_history_import(
            db,
            user,
            preview["id"],
            version=preview["version"],
            preview_signature=preview["preview_signature"],
        )
        raise RuntimeError("injected failure")
    with get_session_context() as db:
        assert db.get(WorkoutHistoryImportDraft, preview["id"]).status == "pending"
        assert db.query(ImportedWorkout).filter_by(owner_user_id=user_id).count() == 0
    assert _confirm(client, headers, preview).status_code == 200


def test_simultaneous_confirmations_on_postgres_are_idempotent(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fitminiapp_api.db.session import engine
    from fitminiapp_api.services.workout_history_import import confirm_history_import

    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locks")
    headers = _auth(client, 833_007)
    preview = _upload(client, headers, _row(exercise_name="barbell bench press"))
    user_id = _user_id(833_007)
    start = Barrier(2)

    def confirm():
        with get_session_context() as db:
            user = db.get(User, user_id)
            start.wait(timeout=10)
            result = confirm_history_import(
                db,
                user,
                preview["id"],
                version=preview["version"],
                preview_signature=preview["preview_signature"],
            )
            return result.result_json

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(confirm) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert results[0] == results[1]
    with get_session_context() as db:
        assert db.query(ImportedWorkout).filter_by(owner_user_id=user_id).count() == 1
        assert (
            db.query(UserWorkoutSet)
            .join(UserWorkoutExercise)
            .join(UserWorkout)
            .join(ImportedWorkout, ImportedWorkout.workout_id == UserWorkout.id)
            .filter(ImportedWorkout.owner_user_id == user_id)
            .count()
            == 1
        )


def test_simultaneous_distinct_drafts_cannot_duplicate_on_postgres(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fitminiapp_api.db.session import engine
    from fitminiapp_api.services.workout_history_import import (
        HistoryImportError,
        confirm_history_import,
    )

    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locks")
    headers = _auth(client, 833_008)
    first = _upload(client, headers, _row(exercise_name="barbell bench press"))
    second = _upload(client, headers, _row(exercise_name="barbell bench press"))
    user_id = _user_id(833_008)
    start = Barrier(2)

    def confirm(preview):
        try:
            with get_session_context() as db:
                user = db.get(User, user_id)
                start.wait(timeout=10)
                result = confirm_history_import(
                    db,
                    user,
                    preview["id"],
                    version=preview["version"],
                    preview_signature=preview["preview_signature"],
                )
                return result.status
        except HistoryImportError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(confirm, preview) for preview in (first, second)]
        results = [future.result(timeout=20) for future in futures]
    assert sorted(results) == ["confirmed", "preview_changed"]
    with get_session_context() as db:
        assert db.query(ImportedWorkout).filter_by(owner_user_id=user_id).count() == 1


def test_duplicate_names_never_choose_a_catalog_exercise_automatically(client):
    headers = _auth(client, 833_009)
    with get_session_context() as db:
        db.add_all(
            [
                Exercise(
                    slug="test-833-ambiguous-a", title="Общее название", metric_type="strength"
                ),
                Exercise(
                    slug="test-833-ambiguous-b", title="Общее название", metric_type="strength"
                ),
            ]
        )
    preview = _upload(client, headers, _row(exercise_name="Общее название"))
    row = preview["rows"][0]
    assert row["match_status"] == "ambiguous" and row["exercise_id"] is None
    assert len(row["candidates"]) == 2
    assert _confirm(client, headers, preview).status_code == 409
    assert (
        client.get("/api/v1/workouts/history/summary", headers=headers).json()["workouts_completed"]
        == 0
    )


@pytest.mark.parametrize(
    "filename", ["../history.csv", "..\\history.csv", "C:history.csv", "history.txt"]
)
def test_unsafe_upload_names_are_rejected(client, filename):
    headers = _auth(client, 833_010)
    response = client.post(
        URL, headers=headers, files={"file": (filename, _csv(_row()), "text/csv")}
    )
    assert response.status_code == 415
    assert (
        client.get("/api/v1/workouts/history/summary", headers=headers).json()["workouts_completed"]
        == 0
    )


def test_oversized_upload_does_not_create_draft_or_history(client):
    from fitminiapp_api.services.workout_history_import_parser import MAX_BYTES

    headers = _auth(client, 833_011)
    response = client.post(
        URL, headers=headers, files={"file": ("history.csv", b"x" * (MAX_BYTES + 1), "text/csv")}
    )
    assert response.status_code in {400, 413}
    assert client.get(URL, headers=headers).json() == []
    assert (
        client.get("/api/v1/workouts/history/summary", headers=headers).json()["workouts_completed"]
        == 0
    )


def test_failed_partial_flush_leaves_existing_history_untouched(client):
    from sqlalchemy import event

    from fitminiapp_api.services.workout_history_import import confirm_history_import

    headers = _auth(client, 833_012)
    first = _upload(client, headers, _row(exercise_name="barbell bench press"))
    assert _confirm(client, headers, first).status_code == 200
    second = _upload(
        client,
        headers,
        _row(
            exercise_name="barbell bench press",
            workout_ref="later",
            completed_at="2025-10-13T18:30:00+03:00",
        ),
    )
    user_id = _user_id(833_012)
    with (
        pytest.raises(RuntimeError, match="injected partial flush failure"),
        get_session_context() as db,
    ):

        @event.listens_for(db, "before_flush")
        def interrupt(session, _context, _instances):
            if any(isinstance(item, UserWorkoutSet) for item in session.new):
                raise RuntimeError("injected partial flush failure")

        confirm_history_import(
            db,
            db.get(User, user_id),
            second["id"],
            version=second["version"],
            preview_signature=second["preview_signature"],
        )
    with get_session_context() as db:
        assert db.query(ImportedWorkout).filter_by(owner_user_id=user_id).count() == 1
        assert db.get(WorkoutHistoryImportDraft, second["id"]).status == "pending"
    assert client.get("/api/v1/workouts/history/summary", headers=headers).json() == {
        "workouts_completed": 1,
        "completed_sets": 1,
        "volume_kg": 362.88,
    }
    assert _confirm(client, headers, second).status_code == 200


def test_import_preserves_existing_planned_workouts_and_adherence(client):
    from datetime import date

    from test_training_analytics import _add_exercise_session, _program

    headers = _auth(client, 833_013)
    user_id = _user_id(833_013)
    with get_session_context() as db:
        program = _program(db, user_id)
        exercise = db.query(Exercise).filter_by(slug="bench-press").one()
        existing = _add_exercise_session(
            db, program, exercise.id, days_ago=1, sets=[(5, 20, "1", True)]
        )
        existing.scheduled_date = date(2025, 10, 13)
        db.flush()
        existing_id = existing.id
    path = "/api/v1/workouts/progress/summary?date_from=2025-10-12&date_to=2025-10-13"
    before = client.get(path, headers=headers)
    assert before.status_code == 200, before.text
    assert before.json()["training"]["planned_workouts"] == 1
    assert before.json()["adherence"]["workouts"]["percent"] == 100.0
    preview = _upload(client, headers, _row(exercise_name="barbell bench press"))
    assert _confirm(client, headers, preview).status_code == 200
    after = client.get(path, headers=headers)
    assert after.status_code == 200, after.text
    assert after.json()["training"]["planned_workouts"] == 1
    assert after.json()["training"]["completed_workouts"] == 2
    assert after.json()["adherence"]["workouts"]["percent"] == 100.0
    with get_session_context() as db:
        existing = db.get(UserWorkout, existing_id)
        assert existing.user_program_id is not None
        assert existing.exercises[0].sets[0].actual_reps == 5
        assert existing.exercises[0].sets[0].actual_weight == Decimal("20.00")


def test_same_source_cannot_be_reimported_as_a_partial_duplicate(client):
    headers = _auth(client, 833_014)
    rows = (
        _row(exercise_name="barbell bench press", set_number="1"),
        _row(exercise_name="barbell bench press", set_number="2"),
    )
    first = _upload(client, headers, *rows)
    resolved = client.post(
        f"{URL}/{first['id']}/resolve",
        headers=headers,
        json={
            "version": first["version"],
            "exercise_choices": {},
            "excluded_lines": [first["rows"][1]["line"]],
            "duplicate_choices": {},
        },
    ).json()
    assert _confirm(client, headers, resolved).status_code == 200
    second = _upload(client, headers, *rows)
    assert second["duplicates"][0]["candidates"][0]["kind"] == "source"
    keep = client.post(
        f"{URL}/{second['id']}/resolve",
        headers=headers,
        json={
            "version": second["version"],
            "exercise_choices": {},
            "excluded_lines": [],
            "duplicate_choices": {"workout-1": "keep"},
        },
    ).json()
    response = _confirm(client, headers, keep)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "duplicate_exact"
    assert (
        client.get("/api/v1/workouts/history/summary", headers=headers).json()["completed_sets"]
        == 1
    )
