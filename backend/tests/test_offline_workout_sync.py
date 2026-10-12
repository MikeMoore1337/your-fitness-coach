from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import WorkoutSetMutation


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_started_workout(client, headers: dict[str, str]) -> tuple[dict, dict]:
    exercises = client.get("/api/v1/programs/exercises", headers=headers).json()
    exercise_id = next(item["id"] for item in exercises if item["metric_type"] == "strength")
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Офлайн-тренировка",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": True,
            "days": [
                {
                    "title": "День 1",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": 1,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    started_workout = started.json()
    return started_workout, started_workout["exercises"][0]["sets"][0]


def _load_migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0049_offline_workout_sync.py"
    )
    spec = importlib.util.spec_from_file_location("offline_workout_sync_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_offline_sync_migration_preserves_sets_and_rolls_back(tmp_path: Path) -> None:
    migration = _load_migration()
    assert migration.down_revision == "0048_workout_adaptations"
    engine = sa.create_engine(f"sqlite:///{(tmp_path / 'offline-workout.db').as_posix()}")
    metadata = sa.MetaData()
    sets = sa.Table(
        "user_workout_sets",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actual_reps", sa.Integer(), nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(sets.insert(), {"id": 1, "actual_reps": 8})
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        assert (
            connection.execute(
                sa.text("SELECT version FROM user_workout_sets WHERE id = 1")
            ).scalar_one()
            == 1
        )
        assert "workout_set_mutations" in sa.inspect(connection).get_table_names()

        migration.downgrade()
        assert "workout_set_mutations" not in sa.inspect(connection).get_table_names()
        assert "version" not in {
            column["name"] for column in sa.inspect(connection).get_columns("user_workout_sets")
        }

    engine.dispose()


def test_set_mutations_are_idempotent_and_rebase_after_version_conflict(client) -> None:
    headers = _auth(client, 93_600)
    _, workout_set = _create_started_workout(client, headers)
    endpoint = f"/api/v1/workouts/sets/{workout_set['id']}"
    first_payload = {
        "actual_reps": 8,
        "actual_weight": 40,
        "is_completed": True,
        "expected_version": 1,
        "mutation_id": "offline-mutation-00000001",
    }

    first = client.patch(endpoint, headers=headers, json=first_payload)
    duplicate = client.patch(endpoint, headers=headers, json=first_payload)
    assert first.status_code == duplicate.status_code == 200
    assert first.json()["version"] == duplicate.json()["version"] == 2
    with get_session_context() as db:
        assert db.query(WorkoutSetMutation).count() == 1

    reused_key = client.patch(
        endpoint,
        headers=headers,
        json={**first_payload, "actual_reps": 9},
    )
    assert reused_key.status_code == 409
    assert reused_key.json()["detail"]["code"] == "workout_set_idempotency_conflict"

    stale_payload = {
        "actual_reps": 10,
        "actual_weight": 42.5,
        "is_completed": True,
        "expected_version": 1,
        "mutation_id": "offline-mutation-00000002",
    }
    stale = client.patch(endpoint, headers=headers, json=stale_payload)
    assert stale.status_code == 409
    assert stale.json()["detail"] == {
        "code": "workout_set_version_conflict",
        "message": "Подход изменён в другой вкладке. Локальное изменение можно повторить.",
        "current": first.json(),
    }

    rebased = client.patch(
        endpoint,
        headers=headers,
        json={**stale_payload, "expected_version": 2},
    )
    assert rebased.status_code == 200
    assert rebased.json()["version"] == 3
    assert rebased.json()["actual_reps"] == 10
    with get_session_context() as db:
        assert db.query(WorkoutSetMutation).count() == 2


def test_completion_survives_stale_autosave_and_persisted_reread(client) -> None:
    headers = _auth(client, 93_603)
    _, workout_set = _create_started_workout(client, headers)
    endpoint = f"/api/v1/workouts/sets/{workout_set['id']}"
    draft = {
        "actual_reps": 9,
        "actual_weight": 42.5,
        "rir": "2",
        "is_completed": False,
        "expected_version": 1,
        "mutation_id": "completion-autosave-0001",
    }
    assert client.patch(endpoint, headers=headers, json=draft).status_code == 200
    completion = {
        **draft,
        "is_completed": True,
        "expected_version": 2,
        "mutation_id": "completion-accepted-0001",
    }
    saved = client.patch(endpoint, headers=headers, json=completion)
    assert saved.status_code == 200
    stale = client.patch(
        endpoint,
        headers=headers,
        json={**draft, "expected_version": 2, "mutation_id": "completion-stale-000001"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["current"]["is_completed"] is True
    assert client.patch(endpoint, headers=headers, json=completion).json()["version"] == 3
    reread = client.get("/api/v1/workouts/today", headers=headers).json()["exercises"][0]["sets"][0]
    assert reread["is_completed"] is True
    assert (reread["actual_reps"], reread["actual_weight"], reread["rir"]) == (9, 42.5, "2")
    with get_session_context() as db:
        assert db.query(WorkoutSetMutation).count() == 2


def test_retry_is_safe_after_finish_and_other_accounts_cannot_replay_it(client) -> None:
    owner_headers = _auth(client, 93_601)
    workout, workout_set = _create_started_workout(client, owner_headers)
    endpoint = f"/api/v1/workouts/sets/{workout_set['id']}"
    payload = {
        "actual_reps": 8,
        "actual_weight": 40,
        "is_completed": True,
        "expected_version": 1,
        "mutation_id": "offline-mutation-00000003",
    }
    assert client.patch(endpoint, headers=owner_headers, json=payload).status_code == 200
    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=owner_headers).status_code
        == 200
    )

    lost_response_retry = client.patch(endpoint, headers=owner_headers, json=payload)
    assert lost_response_retry.status_code == 200
    assert lost_response_retry.json()["version"] == 2

    stale_edit = client.patch(
        endpoint,
        headers=owner_headers,
        json={
            **payload,
            "actual_reps": 9,
            "expected_version": 2,
            "mutation_id": "offline-mutation-00000004",
        },
    )
    assert stale_edit.status_code == 409
    assert stale_edit.json()["detail"]["code"] == "workout_not_active"

    other_headers = _auth(client, 93_602)
    forbidden = client.patch(endpoint, headers=other_headers, json=payload)
    assert forbidden.status_code == 404
