from __future__ import annotations

from test_offline_workout_sync import _auth, _create_started_workout

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import WorkoutSetMutation
from fitminiapp_api.services.workout_sync import _request_fingerprint


def test_new_noop_patch_does_not_create_a_version_or_mutation(client) -> None:
    headers = _auth(client, 94_810)
    _, workout_set = _create_started_workout(client, headers)
    endpoint = f"/api/v1/workouts/sets/{workout_set['id']}"
    before = workout_set["version"]

    empty = client.patch(endpoint, headers=headers, json={})
    metadata_only = client.patch(
        endpoint,
        headers=headers,
        json={"expected_version": before, "mutation_id": "new-noop-mutation-000001"},
    )
    null_completion = client.patch(endpoint, headers=headers, json={"is_completed": None})
    assert empty.status_code == 422, empty.text
    assert metadata_only.status_code == 422, metadata_only.text
    assert null_completion.status_code == 422, null_completion.text

    reread = client.get("/api/v1/workouts/today", headers=headers).json()
    persisted_set = reread["exercises"][0]["sets"][0]
    assert persisted_set["version"] == before
    assert persisted_set["is_completed"] == workout_set["is_completed"]
    with get_session_context() as db:
        assert db.query(WorkoutSetMutation).count() == 0

    valid = client.patch(
        endpoint,
        headers=headers,
        json={
            "is_completed": True,
            "expected_version": before,
            "mutation_id": "valid-new-mutation-000001",
        },
    )
    assert valid.status_code == 200, valid.text
    assert valid.json()["version"] == before + 1
    with get_session_context() as db:
        assert db.query(WorkoutSetMutation).count() == 1


def test_historical_noop_replay_remains_idempotent(client) -> None:
    headers = _auth(client, 94_811)
    _, workout_set = _create_started_workout(client, headers)
    endpoint = f"/api/v1/workouts/sets/{workout_set['id']}"
    key = "historical-noop-mutation-0001"
    with get_session_context() as db:
        db.add(
            WorkoutSetMutation(
                workout_set_id=workout_set["id"],
                mutation_id=key,
                request_fingerprint=_request_fingerprint({}),
                applied_version=workout_set["version"],
            )
        )
        db.commit()
    retry = client.patch(
        endpoint,
        headers=headers,
        json={"mutation_id": key, "expected_version": workout_set["version"]},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["version"] == workout_set["version"]
    with get_session_context() as db:
        assert db.query(WorkoutSetMutation).count() == 1
