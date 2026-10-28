from __future__ import annotations

import pytest

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserProgram
from fitminiapp_api.models.user import User


def _auth(client, user_id, *, is_coach=False):
    response = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": user_id, "is_coach": is_coach}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _payload(client, headers):
    exercises = client.get("/api/v1/programs/exercises", headers=headers).json()
    return {
        "title": "Тестовая программа",
        "goal": "strength",
        "level": "beginner",
        "assign_after_create": False,
        "days": [
            {
                "title": "День",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 2,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize("weeks", [1, 2, 3, 5, 7, 12, 24, 30])
def test_week_cycle_persists_without_materializing_workouts(client, weeks):
    headers = _auth(client, 916000 + weeks)
    payload = _payload(client, headers)
    cycle = {
        "length_weeks": weeks,
        "week_types": ["heavy", "light", "medium"] * weeks,
        "repeat": False,
    }
    cycle["week_types"] = cycle["week_types"][:weeks]
    payload["week_cycle"] = cycle
    response = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["template"]["program_metadata"]["week_cycle"] == {"schema_version": 1, **cycle}
    assert body["assigned_program_id"] is None and body["workouts_created"] == 0
    template_id = body["template"]["id"]
    assert client.get(f"/api/v1/programs/templates/{template_id}", headers=headers).json()[
        "program_metadata"
    ]["week_cycle"] == {"schema_version": 1, **cycle}
    for _ in range(2):
        blocked = client.post(
            f"/api/v1/programs/templates/{template_id}/assign-to-me", headers=headers
        )
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "Назначение программы с циклом недель пока недоступно"
    with get_session_context() as db:
        user = db.query(User).filter_by(telegram_user_id=916000 + weeks).one()
        assert db.query(UserProgram).filter_by(user_id=user.id).count() == 0


def test_invalid_cycles_and_assignment_are_rejected_without_partial_creation(client):
    headers = _auth(client, 916100)
    payload = _payload(client, headers)
    before = client.get("/api/v1/programs/templates/mine", headers=headers).json()
    for cycle in (
        {"length_weeks": 0, "repeat": True},
        {"length_weeks": True, "repeat": True},
        {"length_weeks": 3, "week_types": ["light", "heavy"], "repeat": True},
        {"length_weeks": 1, "week_types": [], "repeat": False},
        {"length_weeks": 1, "week_types": ["deload"], "repeat": False},
        {"length_weeks": 1, "week_types": ["light"], "repeat": "true"},
        {"length_weeks": 1, "week_types": ["heavy"], "repeat": False, "unknown": 1},
    ):
        response = client.post(
            "/api/v1/programs/templates", headers=headers, json={**payload, "week_cycle": cycle}
        )
        assert response.status_code == 422
    response = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            **payload,
            "assign_after_create": True,
            "week_cycle": {"length_weeks": 1, "week_types": ["light"], "repeat": False},
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Назначение программы с циклом недель пока недоступно"
    assert client.get("/api/v1/programs/templates/mine", headers=headers).json() == before


def test_cycle_without_week_types_is_preserved_and_not_assigned(client):
    headers = _auth(client, 916105)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 3, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    cycle = created.json()["template"]["program_metadata"]["week_cycle"]
    assert cycle == {"schema_version": 1, "length_weeks": 3, "week_types": None, "repeat": True}
    template_id = created.json()["template"]["id"]
    blocked = client.post(f"/api/v1/programs/templates/{template_id}/assign-to-me", headers=headers)
    assert blocked.status_code == 403


def test_other_user_cannot_read_cycle_and_edit_cannot_replace_it(client):
    owner = _auth(client, 916101)
    other = _auth(client, 916102)
    payload = _payload(client, owner)
    payload["week_cycle"] = {"length_weeks": 2, "week_types": ["heavy", "light"], "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=owner, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    assert (
        client.post(
            "/api/v1/shares/program/preview", headers=owner, json={"template_id": template_id}
        ).status_code
        == 422
    )
    assert client.get(f"/api/v1/programs/templates/{template_id}", headers=other).status_code in (
        403,
        404,
    )
    assert (
        client.patch(
            f"/api/v1/programs/templates/{template_id}", headers=owner, json=payload
        ).status_code
        == 400
    )
    assert client.get(f"/api/v1/programs/templates/{template_id}", headers=owner).json()[
        "program_metadata"
    ]["week_cycle"]["week_types"] == ["heavy", "light"]
    del payload["week_cycle"]
    edited = client.patch(f"/api/v1/programs/templates/{template_id}", headers=owner, json=payload)
    assert edited.status_code == 200, edited.text
    assert edited.json()["program_metadata"]["week_cycle"]["week_types"] == ["heavy", "light"]


def test_legacy_template_remains_assignable_without_week_cycle(client):
    headers = _auth(client, 916104)
    payload = _payload(client, headers)
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["template"]["program_metadata"] is None
    template_id = created.json()["template"]["id"]
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me", headers=headers
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["workouts_created"] > 0


def test_coach_clone_preserves_cycle_and_cannot_assign_it(client):
    headers = _auth(client, 916103, is_coach=True)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 2, "week_types": ["light", "heavy"], "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    clone = client.post(f"/api/v1/programs/templates/{template_id}/clone", headers=headers)
    assert clone.status_code == 201, clone.text
    assert clone.json()["program_metadata"]["week_cycle"] == {
        "schema_version": 1,
        "length_weeks": 2,
        "week_types": ["light", "heavy"],
        "repeat": True,
    }
    blocked = client.post(
        f"/api/v1/programs/templates/{clone.json()['id']}/assign-to-me", headers=headers
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Назначение программы с циклом недель пока недоступно"
