from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from fitminiapp_api.db.session import engine
from fitminiapp_api.main import app


def _auth(client, telegram_user_id: int, *, coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": coach},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_profiles_crud_selection_and_export_are_user_scoped(client) -> None:
    owner = _auth(client, 1203001)
    other = _auth(client, 1203002, coach=True)
    path = "/api/v1/me/equipment-profiles"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=owner).json() == {
        "revision": 0,
        "active_profile_id": None,
        "profiles": [],
    }

    created = client.put(
        path,
        headers=owner,
        json={
            "revision": 0,
            "profiles": [
                {"name": "  Дом  ", "equipment_ids": ["dumbbell", "bench", "pullup_bar"]},
                {"name": "Поездка", "equipment_ids": []},
                {"name": "Зал", "equipment_ids": ["rack", "barbell"]},
            ],
        },
    )
    assert created.status_code == 200, created.text
    state = created.json()
    assert state["revision"] == 1
    assert [item["name"] for item in state["profiles"]] == ["Дом", "Поездка", "Зал"]
    assert state["profiles"][0]["equipment_ids"] == ["bench", "dumbbell", "pullup_bar"]
    assert state["profiles"][1]["equipment_ids"] == []
    home_id, travel_id, _gym_id = [item["id"] for item in state["profiles"]]

    state["active_profile_id"] = home_id
    state["profiles"][0]["name"] = "Домашний зал"
    state["profiles"][0]["equipment_ids"] = ["dumbbell", "bench", "dip_bars"]
    updated = client.put(path, headers=owner, json=state)
    assert updated.status_code == 200, updated.text
    state = updated.json()
    assert state["revision"] == 2
    assert state["active_profile_id"] == home_id
    assert state["profiles"][0]["name"] == "Домашний зал"
    assert client.get(path, headers=owner).json() == state
    assert client.get(path, headers=other).json()["profiles"] == []

    exported = client.get("/api/v1/me/export", headers=owner)
    assert exported.status_code == 200
    assert exported.json()["profile"]["equipment_profiles"] == {
        "active_profile_id": home_id,
        "profiles": state["profiles"],
    }

    state["profiles"] = [item for item in state["profiles"] if item["id"] != home_id]
    state["active_profile_id"] = travel_id
    deleted = client.put(path, headers=owner, json=state)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["active_profile_id"] == travel_id
    assert len(deleted.json()["profiles"]) == 2
    assert client.get(path, headers=other).json()["profiles"] == []


def test_profiles_validate_revision_ids_and_equipment_without_overwriting_preferences(
    client,
) -> None:
    owner = _auth(client, 1203003)
    other = _auth(client, 1203004)
    path = "/api/v1/me/equipment-profiles"
    pref = client.patch(
        "/api/v1/me/profile",
        headers=owner,
        json={
            "training_preferences": {
                "location_profiles": [{"location": "home", "equipment_ids": ["dumbbell"]}]
            }
        },
    )
    assert pref.status_code == 200
    foreign = client.put(path, headers=other, json={"revision": 0, "profiles": [{"name": "Зал"}]})
    foreign_id = foreign.json()["profiles"][0]["id"]
    for profile in [
        {"id": foreign_id, "name": "Чужой"},
        {"name": "  "},
        {"name": "Дом", "equipment_ids": ["dumbbell", "dumbbell"]},
        {"name": "Дом", "equipment_ids": ["unknown"]},
    ]:
        assert (
            client.put(path, headers=owner, json={"revision": 0, "profiles": [profile]}).status_code
            == 422
        )
    assert (
        client.put(
            path,
            headers=owner,
            json={"revision": 0, "active_profile_id": str(uuid4()), "profiles": []},
        ).status_code
        == 422
    )

    created = client.put(path, headers=owner, json={"revision": 0, "profiles": [{"name": "Дом"}]})
    assert created.status_code == 200
    stale = client.put(path, headers=owner, json={"revision": 0, "profiles": []})
    assert stale.status_code == 409
    assert client.get(path, headers=owner).json() == created.json()
    assert client.get("/api/v1/me", headers=owner).json()["profile"]["training_preferences"][
        "location_profiles"
    ] == [{"location": "home", "equipment_ids": ["dumbbell"]}]
    assert client.get(path, headers=other).json() == foreign.json()


def test_catalog_distinguishes_reviewed_requirements_from_unknown_and_custom(client) -> None:
    headers = _auth(client, 1203005)
    response = client.get("/api/v1/programs/exercises", headers=headers)
    assert response.status_code == 200
    catalog = {item["slug"]: item for item in response.json()}
    assert catalog["bench-press"]["required_equipment_ids"] == ["barbell", "bench", "rack"]
    assert catalog["dumbbell-bench-press"]["required_equipment_ids"] == ["bench", "dumbbell"]
    assert catalog["pull-up"]["required_equipment_ids"] == ["pullup_bar"]
    assert catalog["bodyweight-squat"]["required_equipment_ids"] == []
    assert catalog["mountain-climber"]["required_equipment_ids"] == []
    assert catalog["weighted-dip"]["required_equipment_ids"] is None
    assert catalog["leg-press"]["required_equipment_ids"] is None
    created = client.post(
        "/api/v1/programs/exercises",
        headers=headers,
        json={"title": "Моё упражнение", "equipment": "Гантели", "difficulty_level": "beginner"},
    )
    assert created.status_code == 201
    assert created.json()["required_equipment_ids"] is None


def test_profile_accepts_the_complete_canonical_equipment_set(client) -> None:
    headers = _auth(client, 1203007)
    equipment = [
        "bodyweight",
        "dumbbell",
        "barbell",
        "bench",
        "cable",
        "machine",
        "kettlebell",
        "cardio",
        "other",
        "rack",
        "pullup_bar",
        "dip_bars",
    ]
    response = client.put(
        "/api/v1/me/equipment-profiles",
        headers=headers,
        json={
            "revision": 0,
            "profiles": [{"name": "Всё оборудование", "equipment_ids": equipment}],
        },
    )
    assert response.status_code == 200, response.text
    assert set(response.json()["profiles"][0]["equipment_ids"]) == set(equipment)


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL row locking required")
def test_concurrent_profile_updates_do_not_lose_the_winner(client) -> None:
    headers = _auth(client, 1203006)
    path = "/api/v1/me/equipment-profiles"
    created = client.put(path, headers=headers, json={"revision": 0, "profiles": [{"name": "Дом"}]})
    state = created.json()
    barrier = Barrier(2)

    def update(name: str) -> tuple[int, dict]:
        payload = {**state, "profiles": [{**state["profiles"][0], "name": name}]}
        isolated_client = TestClient(app)
        try:
            barrier.wait(timeout=10)
            response = isolated_client.put(path, headers=headers, json=payload)
            return response.status_code, response.json()
        finally:
            isolated_client.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, ["Дом A", "Дом Б"]))
    assert sorted(status for status, _ in results) == [200, 409]
    winner = next(body for status, body in results if status == 200)
    assert client.get(path, headers=headers).json() == winner
    assert winner["revision"] == 2
