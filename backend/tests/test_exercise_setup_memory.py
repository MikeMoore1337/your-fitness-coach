from __future__ import annotations

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.exercise_setup_memory import ExerciseSetupMemory
from fitminiapp_api.models.user import User


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _exercise_id() -> int:
    with get_session_context() as db:
        return db.query(Exercise.id).filter(Exercise.slug == "bench-press").one()[0]


def test_exercise_setup_memory_is_private_versioned_exported_and_deleted(client) -> None:
    owner_headers = _auth(client, 9_697_001)
    other_headers = _auth(client, 9_697_002)
    exercise_id = _exercise_id()

    empty = client.get(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=owner_headers,
    )
    assert empty.status_code == 200
    assert empty.json() is None

    created = client.put(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=owner_headers,
        json={"body": "  Сиденье 4\r\nСпинка 2  "},
    )
    assert created.status_code == 200
    assert created.json()["exercise_id"] == exercise_id
    assert created.json()["body"] == "Сиденье 4\nСпинка 2"
    assert created.json()["version"] == 1

    other_empty = client.get(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=other_headers,
    )
    assert other_empty.status_code == 200
    assert other_empty.json() is None
    other_created = client.put(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=other_headers,
        json={"body": "Чужая заметка"},
    )
    assert other_created.status_code == 200

    stale = client.put(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=owner_headers,
        json={"body": "Новая настройка", "expected_version": 9},
    )
    assert stale.status_code == 409

    updated = client.put(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=owner_headers,
        json={"body": "Блок 7", "expected_version": 1},
    )
    assert updated.status_code == 200
    assert updated.json()["body"] == "Блок 7"
    assert updated.json()["version"] == 2

    missing_version_delete = client.delete(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=owner_headers,
    )
    assert missing_version_delete.status_code == 409

    exported = client.get("/api/v1/me/export", headers=owner_headers)
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["exercise_setup_memories"] == [
        {
            "id": updated.json()["id"],
            "exercise_id": exercise_id,
            "body": "Блок 7",
            "version": 2,
            "created_at": updated.json()["created_at"],
            "updated_at": updated.json()["updated_at"],
        }
    ]
    assert "Чужая заметка" not in exported.text

    deleted = client.delete(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}?expected_version=2",
        headers=owner_headers,
    )
    assert deleted.status_code == 204
    assert (
        client.get(
            f"/api/v1/me/exercise-setup-memories/{exercise_id}",
            headers=owner_headers,
        ).json()
        is None
    )

    with get_session_context() as db:
        owner = db.query(User).filter(User.telegram_user_id == 9_697_001).one()
        other = db.query(User).filter(User.telegram_user_id == 9_697_002).one()
        assert db.query(ExerciseSetupMemory).filter_by(user_id=owner.id).count() == 0
        assert db.query(ExerciseSetupMemory).filter_by(user_id=other.id).count() == 1

    recreate = client.put(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=owner_headers,
        json={"body": "Красная резина"},
    )
    assert recreate.status_code == 200
    account_deleted = client.request(
        "DELETE",
        "/api/v1/me/account",
        headers=owner_headers,
        json={"confirmation": "DELETE"},
    )
    assert account_deleted.status_code == 204
    with get_session_context() as db:
        assert (
            db.query(ExerciseSetupMemory)
            .join(User, User.id == ExerciseSetupMemory.user_id)
            .filter(User.telegram_user_id == 9_697_001)
            .count()
            == 0
        )
        assert (
            db.query(ExerciseSetupMemory)
            .join(User, User.id == ExerciseSetupMemory.user_id)
            .filter(User.telegram_user_id == 9_697_002)
            .count()
            == 1
        )


def test_exercise_setup_memory_rejects_invalid_input_and_inaccessible_exercises(client) -> None:
    headers = _auth(client, 9_697_003)
    exercise_id = _exercise_id()
    too_long = client.put(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=headers,
        json={"body": "x" * 241},
    )
    assert too_long.status_code == 422
    control = client.put(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=headers,
        json={"body": "сиденье\u0000 4"},
    )
    assert control.status_code == 422
    extra = client.put(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=headers,
        json={"body": "сиденье 4", "unexpected": "value"},
    )
    assert extra.status_code == 422

    inaccessible = client.get(
        "/api/v1/me/exercise-setup-memories/999999999",
        headers=headers,
    )
    assert inaccessible.status_code == 404


def test_exercise_setup_memory_is_included_in_today_workout(client) -> None:
    headers = _auth(client, 9_697_004)
    exercise_id = _exercise_id()
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Память настройки упражнения",
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
                            "prescribed_reps": "8",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200

    saved = client.put(
        f"/api/v1/me/exercise-setup-memories/{exercise_id}",
        headers=headers,
        json={"body": "Сиденье 4"},
    )
    assert saved.status_code == 200

    today = client.get("/api/v1/workouts/today", headers=headers)
    assert today.status_code == 200
    assert today.json()["exercises"][0]["setup_memory"]["body"] == "Сиденье 4"
