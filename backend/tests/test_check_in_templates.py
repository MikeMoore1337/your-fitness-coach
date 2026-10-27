from datetime import timedelta

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.user import CoachClient, User


def _auth(client, telegram_user_id: int, *, is_coach: bool) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "is_coach": is_coach,
            "is_admin": False,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _link_coach_client(coach_telegram_id: int, client_telegram_id: int) -> None:
    with get_session_context() as db:
        coach = db.query(User).filter(User.telegram_user_id == coach_telegram_id).one()
        client = db.query(User).filter(User.telegram_user_id == client_telegram_id).one()
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=client.id))
        db.commit()


def test_check_in_templates_version_assignment_and_history(client):
    coach_headers = _auth(client, 751001, is_coach=True)
    client_headers = _auth(client, 751002, is_coach=False)
    other_coach_headers = _auth(client, 751003, is_coach=True)
    other_client_headers = _auth(client, 751004, is_coach=False)
    _link_coach_client(751001, 751002)

    create_payload = {
        "name": "Еженедельное самочувствие",
        "description": "Поля для регулярной сверки",
        "cadence": "weekly",
        "fields": [
            {"key": "recovery", "required": True},
            {"key": "hunger", "required": False},
        ],
    }
    created = client.post(
        "/api/v1/coach/check-in-templates",
        json=create_payload,
        headers={**coach_headers, "Idempotency-Key": "template-751-1"},
    )
    assert created.status_code == 201
    template = created.json()
    template_id = template["id"]
    assert template["current_version"]["version"] == 1
    assert {field["key"] for field in template["current_version"]["fields"]} == {
        "recovery",
        "hunger",
    }

    replay = client.post(
        "/api/v1/coach/check-in-templates",
        json=create_payload,
        headers={**coach_headers, "Idempotency-Key": "template-751-1"},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == template_id

    conflict = client.post(
        "/api/v1/coach/check-in-templates",
        json={**create_payload, "name": "Другой шаблон"},
        headers={**coach_headers, "Idempotency-Key": "template-751-1"},
    )
    assert conflict.status_code == 409

    assignment = client.post(
        f"/api/v1/coach/check-in-templates/{template_id}/assignments",
        json={"client_id": _user_id(751002)},
        headers={**coach_headers, "Idempotency-Key": "assignment-751-1"},
    )
    assert assignment.status_code == 201
    assignment_id = assignment.json()["id"]
    assert assignment.json()["version"] == 1

    assigned = client.get(
        "/api/v1/check-ins/templates/assigned",
        headers=client_headers,
    )
    assert assigned.status_code == 200
    assert assigned.json()["items"][0]["assignment_id"] == assignment_id
    assert "coach_user_id" not in assigned.json()["items"][0]
    assert client.get(
        "/api/v1/check-ins/templates/assigned",
        headers=other_client_headers,
    ).json() == {"items": []}

    missing_required = client.post(
        f"/api/v1/check-ins/templates/assignments/{assignment_id}/responses",
        json={"values": {"hunger": 3}},
        headers={**client_headers, "Idempotency-Key": "response-751-1"},
    )
    assert missing_required.status_code == 422

    assert (
        client.post(
            f"/api/v1/check-ins/templates/assignments/{assignment_id}/responses",
            json={"values": {"recovery": 4}},
            headers={**other_client_headers, "Idempotency-Key": "response-751-other"},
        ).status_code
        == 404
    )

    submitted = client.post(
        f"/api/v1/check-ins/templates/assignments/{assignment_id}/responses",
        json={"values": {"recovery": 4, "hunger": 2}},
        headers={**client_headers, "Idempotency-Key": "response-751-1"},
    )
    assert submitted.status_code == 201
    assert submitted.json()["version"] == 1
    assert submitted.json()["replayed"] is False

    replayed = client.post(
        f"/api/v1/check-ins/templates/assignments/{assignment_id}/responses",
        json={"values": {"recovery": 4, "hunger": 2}},
        headers={**client_headers, "Idempotency-Key": "response-751-1"},
    )
    assert replayed.status_code == 201
    assert replayed.json()["replayed"] is True

    duplicate_period = client.post(
        f"/api/v1/check-ins/templates/assignments/{assignment_id}/responses",
        json={"values": {"recovery": 5}},
        headers={**client_headers, "Idempotency-Key": "response-751-2"},
    )
    assert duplicate_period.status_code == 409

    version = client.post(
        f"/api/v1/coach/check-in-templates/{template_id}/versions",
        json={
            "fields": [
                {"key": "recovery", "required": True},
                {"key": "training_load", "required": False},
            ]
        },
        headers={**coach_headers, "Idempotency-Key": "version-751-2"},
    )
    assert version.status_code == 201
    assert version.json()["version"] == 2

    reassigned = client.post(
        f"/api/v1/coach/check-in-templates/{template_id}/assignments",
        json={
            "client_id": _user_id(751002),
            "version": 2,
            "due_on": str(today_msk() + timedelta(days=7)),
        },
        headers={**coach_headers, "Idempotency-Key": "assignment-751-2"},
    )
    assert reassigned.status_code == 201
    assert reassigned.json()["version"] == 2

    historical_replay = client.post(
        f"/api/v1/check-ins/templates/assignments/{assignment_id}/responses",
        json={"values": {"recovery": 4, "hunger": 2}},
        headers={**client_headers, "Idempotency-Key": "response-751-1"},
    )
    assert historical_replay.status_code == 201
    assert historical_replay.json()["version"] == 1
    assert historical_replay.json()["replayed"] is True

    history = client.get(
        f"/api/v1/coach/check-in-templates/{template_id}/responses",
        headers=coach_headers,
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["version"] == 1
    assert history.json()["items"][0]["values"] == {"recovery": 4, "hunger": 2}

    deactivated = client.patch(
        f"/api/v1/coach/check-in-templates/{template_id}",
        json={"is_active": False},
        headers=coach_headers,
    )
    assert deactivated.status_code == 200
    assert client.get("/api/v1/check-ins/templates/assigned", headers=client_headers).json() == {
        "items": []
    }

    assert (
        client.patch(
            f"/api/v1/coach/check-in-templates/{template_id}",
            json={"is_active": True},
            headers=coach_headers,
        ).status_code
        == 200
    )
    assert (
        client.get("/api/v1/check-ins/templates/assigned", headers=client_headers).json()["items"][
            0
        ]["version"]
        == 2
    )

    assert (
        client.get(
            f"/api/v1/coach/check-in-templates/{template_id}/responses",
            headers=other_coach_headers,
        ).status_code
        == 404
    )


def _user_id(telegram_user_id: int) -> int:
    with get_session_context() as db:
        return db.query(User.id).filter(User.telegram_user_id == telegram_user_id).scalar()
