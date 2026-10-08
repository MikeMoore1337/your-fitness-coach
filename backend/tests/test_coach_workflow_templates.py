from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.notification import Notification
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
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _link_coach_client(coach_telegram_id: int, client_telegram_id: int) -> int:
    with get_session_context() as db:
        coach = db.query(User).filter(User.telegram_user_id == coach_telegram_id).one()
        client = db.query(User).filter(User.telegram_user_id == client_telegram_id).one()
        db.add(
            CoachClient(
                coach_user_id=coach.id,
                client_user_id=client.id,
                status="active",
            )
        )
        db.commit()
        return client.id


def _create_check_in_template(client, headers: dict[str, str]) -> int:
    response = client.post(
        "/api/v1/coach/check-in-templates",
        json={
            "name": "Проверка самочувствия",
            "description": "Первая проверка",
            "cadence": "weekly",
            "fields": [{"key": "recovery", "required": True}],
        },
        headers={**headers, "Idempotency-Key": "check-in-756-1"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_onboarding_workflow_templates_keep_versions_history_and_access(client):
    coach_headers = _auth(client, 756001, is_coach=True)
    _auth(client, 756002, is_coach=False)
    other_coach_headers = _auth(client, 756003, is_coach=True)
    client_id = _link_coach_client(756001, 756002)
    check_in_template_id = _create_check_in_template(client, coach_headers)

    payload = {
        "name": "Подключение нового клиента",
        "description": "Единый порядок первых шагов",
        "steps": ["invite", "goals", "first_check_in"],
        "check_in_template_id": check_in_template_id,
    }
    created = client.post(
        "/api/v1/coach/workflow-templates/onboarding",
        json=payload,
        headers={**coach_headers, "Idempotency-Key": "onboarding-756-1"},
    )
    assert created.status_code == 201, created.text
    template = created.json()
    template_id = template["id"]
    assert template["current_version"]["version"] == 1
    assert template["assignments"] == []

    replay = client.post(
        "/api/v1/coach/workflow-templates/onboarding",
        json=payload,
        headers={**coach_headers, "Idempotency-Key": "onboarding-756-1"},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == template_id

    conflict = client.post(
        "/api/v1/coach/workflow-templates/onboarding",
        json={**payload, "name": "Другой порядок"},
        headers={**coach_headers, "Idempotency-Key": "onboarding-756-1"},
    )
    assert conflict.status_code == 409

    version = client.post(
        f"/api/v1/coach/workflow-templates/onboarding/{template_id}/versions",
        json={"steps": ["invite", "goals"]},
        headers={**coach_headers, "Idempotency-Key": "onboarding-version-756-2"},
    )
    assert version.status_code == 201, version.text
    assert version.json()["version"] == 2

    first_assignment = client.post(
        f"/api/v1/coach/workflow-templates/onboarding/{template_id}/assignments",
        json={"client_id": client_id, "version": 1},
        headers={**coach_headers, "Idempotency-Key": "onboarding-assignment-756-1"},
    )
    assert first_assignment.status_code == 201, first_assignment.text
    assert first_assignment.json()["version"] == 1

    assignment_replay = client.post(
        f"/api/v1/coach/workflow-templates/onboarding/{template_id}/assignments",
        json={"client_id": client_id, "version": 1},
        headers={**coach_headers, "Idempotency-Key": "onboarding-assignment-756-1"},
    )
    assert assignment_replay.status_code == 201
    assert assignment_replay.json()["id"] == first_assignment.json()["id"]

    second_assignment = client.post(
        f"/api/v1/coach/workflow-templates/onboarding/{template_id}/assignments",
        json={"client_id": client_id, "version": 2},
        headers={**coach_headers, "Idempotency-Key": "onboarding-assignment-756-2"},
    )
    assert second_assignment.status_code == 201, second_assignment.text
    assert second_assignment.json()["version"] == 2

    history = client.get(
        "/api/v1/coach/workflow-templates/onboarding",
        headers=coach_headers,
    )
    assert history.status_code == 200
    assert [row["version"] for row in history.json()["items"][0]["assignments"]] == [2, 1]

    assert client.get(
        "/api/v1/coach/workflow-templates/onboarding",
        headers=other_coach_headers,
    ).json() == {"items": []}
    assert (
        client.post(
            f"/api/v1/coach/workflow-templates/onboarding/{template_id}/assignments",
            json={"client_id": client_id},
            headers={**other_coach_headers, "Idempotency-Key": "other-coach-756"},
        ).status_code
        == 404
    )


def test_communication_workflow_requires_explicit_confirmation_and_isolated_access(client):
    coach_headers = _auth(client, 756101, is_coach=True)
    client_headers = _auth(client, 756102, is_coach=False)
    other_coach_headers = _auth(client, 756103, is_coach=True)
    client_id = _link_coach_client(756101, 756102)

    created = client.post(
        "/api/v1/coach/workflow-templates/communication",
        json={
            "name": "Первое сообщение",
            "description": "Короткая связь после подключения",
            "subject": "Ваши первые шаги",
            "body": "Проверьте цели и напишите, если нужна помощь.",
        },
        headers={**coach_headers, "Idempotency-Key": "communication-756-1"},
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    assert created.json()["current_version"]["subject"] == "Ваши первые шаги"

    draft = client.post(
        f"/api/v1/coach/workflow-templates/communication/{template_id}/drafts",
        json={"client_id": client_id},
        headers={**coach_headers, "Idempotency-Key": "communication-draft-756-1"},
    )
    assert draft.status_code == 201, draft.text
    draft_id = draft.json()["id"]
    assert draft.json()["status"] == "draft"
    loaded = client.get(
        f"/api/v1/coach/communication-drafts/{draft_id}",
        headers=coach_headers,
    )
    assert loaded.status_code == 200
    assert loaded.json()["body"] == "Проверьте цели и напишите, если нужна помощь."
    assert (
        client.get(
            f"/api/v1/coach/communication-drafts/{draft_id}",
            headers=other_coach_headers,
        ).status_code
        == 404
    )
    with get_session_context() as db:
        assert db.query(Notification).filter(Notification.user_id == client_id).count() == 0

    updated = client.patch(
        f"/api/v1/coach/communication-drafts/{draft_id}",
        json={
            "subject": "Проверьте первые шаги",
            "body": "Откройте план и напишите тренеру о вопросах.",
        },
        headers=coach_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["subject"] == "Проверьте первые шаги"

    assert (
        client.post(
            f"/api/v1/coach/communication-drafts/{draft_id}/confirm",
            headers={**other_coach_headers, "Idempotency-Key": "communication-confirm-756"},
        ).status_code
        == 404
    )

    confirmed = client.post(
        f"/api/v1/coach/communication-drafts/{draft_id}/confirm",
        headers={**coach_headers, "Idempotency-Key": "communication-confirm-756"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    notification_id = confirmed.json()["notification_id"]

    replay = client.post(
        f"/api/v1/coach/communication-drafts/{draft_id}/confirm",
        headers={**coach_headers, "Idempotency-Key": "communication-confirm-756"},
    )
    assert replay.status_code == 200
    assert replay.json()["notification_id"] == notification_id

    notifications = client.get("/api/v1/notifications", headers=client_headers)
    assert notifications.status_code == 200
    assert any(
        item["id"] == notification_id
        and item["title"] == "Проверьте первые шаги"
        and item["body"] == "Откройте план и напишите тренеру о вопросах."
        for item in notifications.json()
    )
    assert client.get(
        "/api/v1/coach/workflow-templates/communication",
        headers=other_coach_headers,
    ).json() == {"items": []}
