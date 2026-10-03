from datetime import timedelta

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.account import AccountDataExport
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.auth_identity import AuthIdentity
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.notification import Notification
from fitminiapp_api.models.program import ProgramTemplate
from fitminiapp_api.models.token import RefreshToken
from fitminiapp_api.models.user import CoachClient, User


def _auth(
    client,
    telegram_user_id: int,
    *,
    is_coach: bool = False,
    is_admin: bool = False,
    username: str | None = None,
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "is_coach": is_coach,
            "is_admin": is_admin,
            "username": username,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _root(client, monkeypatch, telegram_user_id: int = 71_001) -> dict[str, str]:
    monkeypatch.setattr(settings, "admin_telegram_user_ids", str(telegram_user_id))
    return _auth(client, telegram_user_id, is_admin=True, username="root_owner")


def test_only_verified_configured_root_can_open_operational_endpoints(client, monkeypatch):
    delegated = _auth(client, 71_010, is_admin=True)
    ordinary = _auth(client, 71_011)
    root = _root(client, monkeypatch)

    protected_paths = (
        "/api/v1/admin/users?q=71011",
        "/api/v1/admin/jobs",
        "/api/v1/admin/funnel",
        "/api/v1/admin/audit",
    )
    for path in protected_paths:
        assert client.get(path, headers=ordinary).status_code == 403
        assert client.get(path, headers=delegated).status_code == 403
        assert client.get(path, headers=root).status_code == 200

    current = client.get("/api/v1/me", headers=root).json()
    assert current["is_root"] is True
    assert current["is_coach"] is False


def test_configured_id_without_verified_identity_gets_no_global_content_privilege(
    client, monkeypatch
):
    headers = _root(client, monkeypatch, telegram_user_id=71_002)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    with get_session_context() as db:
        db.query(AuthIdentity).filter(
            AuthIdentity.user_id == user_id,
            AuthIdentity.provider == "telegram",
        ).delete(synchronize_session=False)
        db.commit()

    exercise = client.post(
        "/api/v1/programs/exercises",
        json={
            "title": "Identity boundary exercise",
            "primary_muscle": "legs",
            "equipment": "bodyweight",
        },
        headers=headers,
    )
    assert exercise.status_code == 201
    exercise_id = exercise.json()["id"]
    template = client.post(
        "/api/v1/programs/templates",
        json={
            "title": "Identity boundary template",
            "goal": "maintenance",
            "level": "beginner",
            "mode": "self",
            "assign_after_create": False,
            "days": [
                {
                    "title": "День 1",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": 1,
                            "prescribed_reps": "8",
                            "rest_seconds": 60,
                        }
                    ],
                }
            ],
        },
        headers=headers,
    )
    assert template.status_code == 200

    with get_session_context() as db:
        created_exercise = db.query(Exercise).filter(Exercise.id == exercise_id).one()
        created_template = (
            db.query(ProgramTemplate)
            .filter(ProgramTemplate.id == template.json()["template"]["id"])
            .one()
        )
        assert created_exercise.created_by_user_id == user_id
        assert created_template.is_public is False


def test_root_search_and_detail_minimize_linked_identity_and_job_data(client, monkeypatch):
    root = _root(client, monkeypatch)
    target_headers = _auth(client, 71_020, username="very_long_support_identifier")
    target = client.get("/api/v1/me", headers=target_headers).json()
    with get_session_context() as db:
        db.add(
            AuthIdentity(
                user_id=target["id"],
                provider="google",
                subject="provider-secret-subject-must-not-leak",
                email="long.support.identifier@example.com",
                email_verified=True,
            )
        )
        db.add(
            Notification(
                user_id=target["id"],
                channel="telegram",
                title="Private notification title",
                body="Private notification body",
                scheduled_for=now_msk_naive(),
                scheduled_for_utc=now_msk_naive(),
                status="failed",
                last_error="raw provider error must not leak",
                attempt_count=3,
            )
        )
        db.add(
            AccountDataExport(
                user_id=target["id"],
                export_id="71020000-0000-0000-0000-000000000000",
                status="error",
                error_code="generation_failed",
            )
        )
        db.commit()

    by_username = client.get("/api/v1/admin/users?q=very_long_support", headers=root)
    assert by_username.status_code == 200
    assert by_username.json()[0]["id"] == target["id"]
    by_email = client.get(
        "/api/v1/admin/users?q=long.support.identifier%40example.com", headers=root
    )
    assert by_email.status_code == 200
    assert by_email.json()[0]["id"] == target["id"]

    detail = client.get(f"/api/v1/admin/users/{target['id']}", headers=root)
    assert detail.status_code == 200
    payload = detail.json()
    google = next(item for item in payload["identities"] if item["provider"] == "google")
    assert google["identifier"] == "l***@example.com"
    assert "provider-secret-subject" not in detail.text
    assert "Private notification" not in detail.text
    assert "raw provider error" not in detail.text
    notification = next(item for item in payload["jobs"] if item["kind"] == "notification")
    export = next(item for item in payload["jobs"] if item["kind"] == "account_export")
    assert notification["retry_allowed"] is False
    assert export["retry_allowed"] is True


def test_root_block_revokes_sessions_ends_relationships_and_audits_reason(client, monkeypatch):
    root = _root(client, monkeypatch)
    trainer_headers = _auth(client, 71_030, is_coach=True)
    client_headers = _auth(client, 71_031)
    trainer = client.get("/api/v1/me", headers=trainer_headers).json()
    client_user = client.get("/api/v1/me", headers=client_headers).json()
    with get_session_context() as db:
        db.add(
            CoachClient(
                coach_user_id=trainer["id"],
                client_user_id=client_user["id"],
                status="active",
            )
        )
        db.commit()

    blocked = client.patch(
        f"/api/v1/admin/users/{trainer['id']}/status",
        json={"is_active": False, "reason": "security_incident"},
        headers=root,
    )
    assert blocked.status_code == 200
    assert blocked.json()["is_active"] is False
    assert client.get("/api/v1/me", headers=trainer_headers).status_code == 401

    with get_session_context() as db:
        assert (
            db.query(RefreshToken)
            .filter(RefreshToken.user_id == trainer["id"], RefreshToken.is_revoked.is_(False))
            .count()
            == 0
        )
        relation = db.query(CoachClient).filter(CoachClient.coach_user_id == trainer["id"]).one()
        assert relation.status == "ended"
        event = db.query(AuditEvent).filter(AuditEvent.action == "root.account_blocked").one()
        assert event.details == {"reason": "security_incident"}

    restored = client.patch(
        f"/api/v1/admin/users/{trainer['id']}/status",
        json={"is_active": True, "reason": "account_recovery"},
        headers=root,
    )
    assert restored.status_code == 200
    assert restored.json()["is_active"] is True
    assert restored.json()["relationships"][0]["status"] == "ended"


def test_root_can_revoke_restore_trainer_and_end_specific_relationship(client, monkeypatch):
    root = _root(client, monkeypatch)
    trainer_headers = _auth(client, 71_040, is_coach=True)
    first_client_headers = _auth(client, 71_041)
    second_client_headers = _auth(client, 71_042)
    trainer_id = client.get("/api/v1/me", headers=trainer_headers).json()["id"]
    first_client_id = client.get("/api/v1/me", headers=first_client_headers).json()["id"]
    second_client_id = client.get("/api/v1/me", headers=second_client_headers).json()["id"]
    with get_session_context() as db:
        first = CoachClient(
            coach_user_id=trainer_id,
            client_user_id=first_client_id,
            status="active",
        )
        second = CoachClient(
            coach_user_id=trainer_id,
            client_user_id=second_client_id,
            status="active",
        )
        db.add_all([first, second])
        db.commit()
        first_id = first.id

    ended = client.post(
        f"/api/v1/admin/relationships/{first_id}/end",
        json={"reason": "relationship_safety"},
        headers=root,
    )
    assert ended.status_code == 200
    assert (
        next(item for item in ended.json()["relationships"] if item["id"] == first_id)["status"]
        == "ended"
    )

    revoked = client.patch(
        f"/api/v1/admin/users/{trainer_id}/trainer-capability",
        json={"is_active": False, "reason": "abuse"},
        headers=root,
    )
    assert revoked.status_code == 200
    assert revoked.json()["is_trainer"] is False
    assert all(item["status"] == "ended" for item in revoked.json()["relationships"])

    restored = client.patch(
        f"/api/v1/admin/users/{trainer_id}/trainer-capability",
        json={"is_active": True, "reason": "support_request"},
        headers=root,
    )
    assert restored.status_code == 200
    assert restored.json()["is_trainer"] is True
    assert all(item["status"] == "ended" for item in restored.json()["relationships"])


def test_relationship_with_root_counterparty_is_protected_in_detail_and_endpoint(
    client, monkeypatch
):
    root = _root(client, monkeypatch)
    root_id = client.get("/api/v1/me", headers=root).json()["id"]
    trainer_headers = _auth(client, 71_043, is_coach=True)
    trainer_id = client.get("/api/v1/me", headers=trainer_headers).json()["id"]
    with get_session_context() as db:
        relation = CoachClient(
            coach_user_id=trainer_id,
            client_user_id=root_id,
            status="active",
        )
        db.add(relation)
        db.commit()
        relationship_id = relation.id

    detail = client.get(f"/api/v1/admin/users/{trainer_id}", headers=root)
    assert detail.status_code == 200
    relationship = next(
        item for item in detail.json()["relationships"] if item["id"] == relationship_id
    )
    assert relationship["can_end"] is False
    assert (
        client.post(
            f"/api/v1/admin/relationships/{relationship_id}/end",
            json={"reason": "relationship_safety"},
            headers=root,
        ).status_code
        == 403
    )


def test_root_self_target_and_removed_broad_admin_routes_are_blocked(client, monkeypatch):
    root = _root(client, monkeypatch)
    current = client.get("/api/v1/me", headers=root).json()

    assert (
        client.patch(
            f"/api/v1/admin/users/{current['id']}/status",
            json={"is_active": False, "reason": "security_incident"},
            headers=root,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/admin/users/{current['id']}/trainer-capability",
            json={"is_active": True, "reason": "support_request"},
            headers=root,
        ).status_code
        == 403
    )
    removed_routes = (
        ("PATCH", f"/api/v1/admin/users/{current['id']}/admin-capability"),
        ("DELETE", f"/api/v1/admin/users/{current['id']}"),
        ("GET", "/api/v1/admin/templates"),
        ("GET", "/api/v1/admin/notifications"),
    )
    for method, path in removed_routes:
        assert client.request(method, path, headers=root).status_code in {404, 405}


def test_export_retry_is_bounded_to_error_or_expired_and_notification_has_no_retry(
    client, monkeypatch
):
    root = _root(client, monkeypatch)
    target_headers = _auth(client, 71_050)
    target = client.get("/api/v1/me", headers=target_headers).json()
    export_id = "71050000-0000-0000-0000-000000000000"
    with get_session_context() as db:
        db.add(
            AccountDataExport(
                user_id=target["id"],
                export_id=export_id,
                status="error",
                error_code="generation_failed",
            )
        )
        db.add(
            Notification(
                user_id=target["id"],
                channel="telegram",
                title="Never exposed",
                body="Never exposed",
                scheduled_for=now_msk_naive(),
                scheduled_for_utc=now_msk_naive(),
                status="failed",
            )
        )
        db.commit()

    retried = client.post(f"/api/v1/admin/exports/{export_id}/retry", headers=root)
    assert retried.status_code == 200
    assert retried.json()["status"] == "ready"
    assert retried.json()["retry_allowed"] is False
    assert (
        client.post(
            f"/api/v1/admin/exports/{retried.json()['job_id'][7:]}/retry", headers=root
        ).status_code
        == 409
    )
    assert client.post("/api/v1/admin/notifications/1/retry", headers=root).status_code == 404


def test_funnel_returns_only_server_confirmed_kpis_without_raw_events(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "prod")
    root = _root(client, monkeypatch)
    _auth(client, 71_060)

    response = client.get("/api/v1/admin/funnel?period_days=30", headers=root)
    assert response.status_code == 200
    payload = response.json()
    assert payload["analytics_provider_status"] == "not_connected"
    assert [kpi["key"] for kpi in payload["kpis"]] == [
        "activation_rate",
        "time_to_first_useful_action",
        "first_workout_completion_rate",
        "first_week_value_rate",
        "d1_meaningful_return",
        "d7_meaningful_return",
        "d30_meaningful_return",
        "missed_workout_recovery_conversion",
        "nutrition_repeat_rate",
        "weekly_loop_completion",
    ]
    assert payload["kpis"][0]["denominator"] >= 2
    assert "Демо-сессии" in payload["coverage_note"]
    assert "user_id" not in response.text


def test_funnel_excludes_trainer_and_admin_accounts_from_user_cohort(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "prod")
    root = _root(client, monkeypatch, telegram_user_id=71_061)
    before = client.get("/api/v1/admin/funnel?period_days=30", headers=root).json()

    _auth(client, 71_062)
    _auth(client, 71_063, is_coach=True)
    _auth(client, 71_064, is_admin=True)

    after = client.get("/api/v1/admin/funnel?period_days=30", headers=root).json()
    assert after["kpis"][0]["denominator"] == before["kpis"][0]["denominator"] + 1


def test_invalid_reason_is_rejected_before_operation(client, monkeypatch):
    root = _root(client, monkeypatch)
    target_headers = _auth(client, 71_070)
    target = client.get("/api/v1/me", headers=target_headers).json()

    response = client.patch(
        f"/api/v1/admin/users/{target['id']}/status",
        json={"is_active": False, "reason": "free text with personal data"},
        headers=root,
    )
    assert response.status_code == 422
    with get_session_context() as db:
        assert db.query(User).filter(User.id == target["id"]).one().is_active is True


def test_search_escapes_wildcards_instead_of_enumerating_accounts(client, monkeypatch):
    root = _root(client, monkeypatch)
    _auth(client, 71_080, username="literal_percent")

    response = client.get("/api/v1/admin/users?q=%25%25", headers=root)
    assert response.status_code == 200
    assert response.json() == []


def test_audit_endpoint_never_returns_details_payload(client, monkeypatch):
    root = _root(client, monkeypatch)
    target_headers = _auth(client, 71_090)
    target = client.get("/api/v1/me", headers=target_headers).json()
    with get_session_context() as db:
        db.add(
            AuditEvent(
                actor_user_id=target["id"],
                target_user_id=target["id"],
                action="support.raw_case",
                resource_type="support",
                details={"raw_content": "must not leak", "reason": "support_request"},
                created_at=now_msk_naive() - timedelta(minutes=1),
            )
        )
        db.commit()

    response = client.get("/api/v1/admin/audit", headers=root)
    assert response.status_code == 200
    assert "must not leak" not in response.text
    assert "details" not in response.text
    event = next(item for item in response.json() if item["action"] == "support.raw_case")
    assert event["reason"] == "support_request"
