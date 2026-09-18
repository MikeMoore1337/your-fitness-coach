from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.notification import Notification
from fitminiapp_api.models.report_handoff import ReportHandoff
from fitminiapp_api.models.user import BodyMeasurement, CoachClient, User
from fitminiapp_api.services.account_export import build_account_export
from fitminiapp_api.services.accounts import delete_user_cascade
from fitminiapp_api.services.notifications import prune_terminal_records


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_id(telegram_user_id: int) -> int:
    with get_session_context() as db:
        return db.query(User.id).filter(User.telegram_user_id == telegram_user_id).scalar()


def _link(sender_id: int, trainer_id: int) -> int:
    with get_session_context() as db:
        relation = CoachClient(
            coach_user_id=trainer_id,
            client_user_id=sender_id,
            status="active",
        )
        db.add(relation)
        db.flush()
        return relation.id


def _period(days: int = 7) -> dict[str, str]:
    today = today_msk()
    return {
        "period": "custom",
        "date_from": (today - timedelta(days=days - 1)).isoformat(),
        "date_to": today.isoformat(),
    }


def _add_private_check_in(user_id: int) -> str:
    today = today_msk()
    secret = "PRIVATE_CHECK_IN_NOTE_83"
    with get_session_context() as db:
        db.add(
            WeeklyCheckIn(
                user_id=user_id,
                week_start=today - timedelta(days=today.weekday()),
                week_end=today - timedelta(days=today.weekday()) + timedelta(days=6),
                submitted_on=today,
                timezone="Europe/Moscow",
                status="completed",
                summary_version="weekly-check-in-summary-v1",
                summary={},
                training_load=4,
                recovery=3,
                hunger=2,
                adherence_difficulty=2,
                note=secret,
            )
        )
    return secret


def test_handoff_is_explicit_live_authorized_and_idempotent(client) -> None:
    sender_headers = _auth(client, 83_001)
    trainer_headers = _auth(client, 83_002, is_coach=True)
    wrong_trainer_headers = _auth(client, 83_003, is_coach=True)
    sender_id = _user_id(83_001)
    trainer_id = _user_id(83_002)
    relation_id = _link(sender_id, trainer_id)
    secret = _add_private_check_in(sender_id)
    period = _period()
    client_comment = "Комментарий клиента для тренера"
    definition = client.post(
        "/api/v1/workouts/diary/custom-definitions",
        json={"label": "Живот"},
        headers=sender_headers,
    )
    assert definition.status_code == 201, definition.text
    measurement = client.post(
        "/api/v1/workouts/diary",
        json={
            "measured_on": today_msk().isoformat(),
            "custom_values": [{"definition_id": definition.json()["id"], "value": 86}],
        },
        headers=sender_headers,
    )
    assert measurement.status_code == 200, measurement.text

    created = client.post(
        "/api/v1/report-handoffs",
        json={**period, "client_comment": client_comment},
        headers={**sender_headers, "Idempotency-Key": "handoff-83-first"},
    )

    assert created.status_code == 201, created.text
    handoff = created.json()
    assert handoff["period"] == "custom"
    assert handoff["period_start"] == period["date_from"]
    assert handoff["period_end"] == period["date_to"]
    assert handoff["trainer"]["id"] == trainer_id
    assert handoff["delivery_status"] == "delivered"
    assert handoff["live"] is True
    assert handoff["client_comment"] == client_comment
    assert "report" not in handoff
    assert "overview" in handoff["included_section_ids"]

    with get_session_context() as db:
        stored = db.get(ReportHandoff, handoff["id"])
        assert stored is not None
        assert stored.sender_user_id == sender_id
        assert stored.trainer_user_id == trainer_id
        assert stored.relationship_id == relation_id
        assert stored.client_comment == client_comment
        notification = db.get(Notification, stored.notification_id)
        assert notification is not None
        assert notification.channel == "in_app"
        assert notification.status == "sent"
        assert secret not in notification.body
        query = parse_qs(urlsplit(notification.action_url).query)
        assert query["section"] == ["progress"]
        assert query["report_handoff_id"] == [str(handoff["id"])]
        assert query["return_to"] == ["/app?section=profile#profile-notifications"]

    repeated_key = client.post(
        "/api/v1/report-handoffs",
        json={**period, "client_comment": client_comment},
        headers={**sender_headers, "Idempotency-Key": "handoff-83-first"},
    )
    repeated_revision = client.post(
        "/api/v1/report-handoffs",
        json={**period, "client_comment": client_comment},
        headers={**sender_headers, "Idempotency-Key": "handoff-83-second"},
    )
    conflicting_key = client.post(
        "/api/v1/report-handoffs",
        json={
            **period,
            "date_from": (today_msk() - timedelta(days=5)).isoformat(),
            "client_comment": client_comment,
        },
        headers={**sender_headers, "Idempotency-Key": "handoff-83-first"},
    )

    assert repeated_key.status_code == 201
    assert repeated_key.json()["id"] == handoff["id"]
    assert repeated_revision.status_code == 201
    assert repeated_revision.json()["id"] == handoff["id"]
    assert conflicting_key.status_code == 409
    with get_session_context() as db:
        assert (
            db.query(ReportHandoff).filter(ReportHandoff.sender_user_id == sender_id).count() == 1
        )
        assert db.query(Notification).filter(Notification.user_id == trainer_id).count() == 1

    trainer_view = client.get(
        f"/api/v1/report-handoffs/{handoff['id']}",
        headers=trainer_headers,
    )
    sender_view = client.get(
        f"/api/v1/report-handoffs/{handoff['id']}",
        headers=sender_headers,
    )
    wrong_view = client.get(
        f"/api/v1/report-handoffs/{handoff['id']}",
        headers=wrong_trainer_headers,
    )

    assert trainer_view.status_code == 200, trainer_view.text
    assert sender_view.status_code == 200, sender_view.text
    assert wrong_view.status_code == 404
    assert trainer_view.json()["report"]["subject"]["role"] == "client"
    assert trainer_view.json()["handoff"]["client_comment"] == client_comment
    assert trainer_view.json()["report"]["nutrition"]["period"] == "custom"
    assert any(
        trend["label"] == "Живот" and trend["latest_value"] == 86
        for trend in trainer_view.json()["report"]["body"]["trends"]
    )
    assert "note" not in trainer_view.text
    assert secret not in trainer_view.text
    assert trainer_view.json()["data_changed_since_send"] is False

    with get_session_context() as db:
        db.add(
            BodyMeasurement(
                user_id=sender_id,
                measured_on=today_msk() - timedelta(days=1),
                weight_kg=81.2,
            )
        )

    changed_view = client.get(
        f"/api/v1/report-handoffs/{handoff['id']}",
        headers=trainer_headers,
    )
    assert changed_view.status_code == 200
    assert changed_view.json()["data_changed_since_send"] is True

    history = client.get("/api/v1/report-handoffs", headers=sender_headers)
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [handoff["id"]]


def test_handoff_comment_is_plain_text_versioned_and_bounded(client) -> None:
    sender_headers = _auth(client, 83_051)
    trainer_headers = _auth(client, 83_052, is_coach=True)
    sender_id = _user_id(83_051)
    trainer_id = _user_id(83_052)
    _link(sender_id, trainer_id)
    period = {"period": "days_7"}

    first = client.post(
        "/api/v1/report-handoffs",
        json={**period, "client_comment": "Версия один"},
        headers={**sender_headers, "Idempotency-Key": "handoff-83-comment-a"},
    )
    second = client.post(
        "/api/v1/report-handoffs",
        json={**period, "client_comment": "Версия два"},
        headers={**sender_headers, "Idempotency-Key": "handoff-83-comment-b"},
    )
    conflicting_key = client.post(
        "/api/v1/report-handoffs",
        json={**period, "client_comment": "Другое содержание"},
        headers={**sender_headers, "Idempotency-Key": "handoff-83-comment-a"},
    )
    too_long = client.post(
        "/api/v1/report-handoffs",
        json={**period, "client_comment": "x" * 2001},
        headers={**sender_headers, "Idempotency-Key": "handoff-83-comment-long"},
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] != second.json()["id"]
    assert conflicting_key.status_code == 409
    assert too_long.status_code == 422

    trainer_view = client.get(
        f"/api/v1/report-handoffs/{second.json()['id']}",
        headers=trainer_headers,
    )
    assert trainer_view.status_code == 200
    assert trainer_view.json()["handoff"]["client_comment"] == "Версия два"
    assert trainer_id == trainer_view.json()["handoff"]["trainer"]["id"]


def test_handoff_retry_and_stale_notification_are_safe(client) -> None:
    sender_headers = _auth(client, 83_101)
    trainer_headers = _auth(client, 83_102, is_coach=True)
    sender_id = _user_id(83_101)
    trainer_id = _user_id(83_102)
    _link(sender_id, trainer_id)

    created = client.post(
        "/api/v1/report-handoffs",
        json={"period": "days_7"},
        headers={**sender_headers, "Idempotency-Key": "handoff-83-retry"},
    )
    assert created.status_code == 201, created.text
    handoff_id = created.json()["id"]

    with get_session_context() as db:
        handoff = db.get(ReportHandoff, handoff_id)
        assert handoff is not None and handoff.notification_id is not None
        notification = db.get(Notification, handoff.notification_id)
        assert notification is not None
        notification.status = "failed"

    retry = client.post(
        f"/api/v1/report-handoffs/{handoff_id}/retry",
        headers={**sender_headers, "Idempotency-Key": "handoff-83-retry-1"},
    )
    retry_again = client.post(
        f"/api/v1/report-handoffs/{handoff_id}/retry",
        headers={**sender_headers, "Idempotency-Key": "handoff-83-retry-1"},
    )

    assert retry.status_code == 200, retry.text
    assert retry.json()["id"] == handoff_id
    assert retry.json()["delivery_status"] == "delivered"
    assert retry.json()["delivery_attempt"] == 2
    assert retry_again.status_code == 200
    with get_session_context() as db:
        assert db.query(Notification).filter(Notification.user_id == trainer_id).count() == 2
        retried_handoff = db.get(ReportHandoff, handoff_id)
        assert retried_handoff is not None and retried_handoff.notification_id is not None
        retried_notification_id = retried_handoff.notification_id

    with get_session_context() as db:
        relation = db.query(CoachClient).filter(CoachClient.client_user_id == sender_id).one()
        relation.status = "ended"

    stale_open = client.post(
        f"/api/v1/notifications/{retried_notification_id}/open",
        headers=trainer_headers,
    )
    revoked_view = client.get(
        f"/api/v1/report-handoffs/{handoff_id}",
        headers=trainer_headers,
    )
    revoked_retry = client.post(
        f"/api/v1/report-handoffs/{handoff_id}/retry",
        headers={**sender_headers, "Idempotency-Key": "handoff-83-retry-2"},
    )

    assert stale_open.status_code == 200
    assert stale_open.json()["stale"] is True
    assert stale_open.json()["destination"] == "/app?section=profile#profile-notifications"
    assert revoked_view.status_code == 404
    assert revoked_retry.status_code == 404


def test_handoff_delivery_status_survives_notification_retention(client) -> None:
    sender_headers = _auth(client, 83_151)
    trainer_headers = _auth(client, 83_152, is_coach=True)
    sender_id = _user_id(83_151)
    trainer_id = _user_id(83_152)
    _link(sender_id, trainer_id)

    created = client.post(
        "/api/v1/report-handoffs",
        json={"period": "days_7"},
        headers={**sender_headers, "Idempotency-Key": "handoff-83-retention"},
    )
    assert created.status_code == 201, created.text
    handoff_id = created.json()["id"]

    with get_session_context() as db:
        handoff = db.get(ReportHandoff, handoff_id)
        assert handoff is not None and handoff.notification_id is not None
        notification = db.get(Notification, handoff.notification_id)
        assert notification is not None
        notification.created_at = now_msk_naive() - timedelta(days=91)

    with get_session_context() as db:
        assert prune_terminal_records(db) == 1
        retained = db.get(ReportHandoff, handoff_id)
        assert retained is not None
        assert retained.notification_id is None
        assert retained.delivery_status == "delivered"

    view = client.get(f"/api/v1/report-handoffs/{handoff_id}", headers=trainer_headers)
    assert view.status_code == 200, view.text
    assert view.json()["handoff"]["delivery_status"] == "delivered"

    retry = client.post(
        f"/api/v1/report-handoffs/{handoff_id}/retry",
        headers={**sender_headers, "Idempotency-Key": "handoff-83-retention-retry"},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["delivery_status"] == "delivered"
    assert retry.json()["delivery_attempt"] == 1


def test_handoff_requires_active_trainer_and_valid_period(client) -> None:
    sender_headers = _auth(client, 83_201)
    sender_id = _user_id(83_201)
    today = today_msk()

    no_trainer = client.post(
        "/api/v1/report-handoffs",
        json={"period": "days_7"},
        headers={**sender_headers, "Idempotency-Key": "handoff-83-no-trainer"},
    )
    assert no_trainer.status_code == 409

    trainer_headers = _auth(client, 83_202, is_coach=True)
    trainer_id = _user_id(83_202)
    _link(sender_id, trainer_id)
    too_long = client.post(
        "/api/v1/report-handoffs",
        json={
            "period": "custom",
            "date_from": (today - timedelta(days=366)).isoformat(),
            "date_to": today.isoformat(),
        },
        headers={**sender_headers, "Idempotency-Key": "handoff-83-too-long"},
    )
    future = client.post(
        "/api/v1/report-handoffs",
        json={
            "period": "custom",
            "date_from": today.isoformat(),
            "date_to": (today + timedelta(days=1)).isoformat(),
        },
        headers={**sender_headers, "Idempotency-Key": "handoff-83-future"},
    )
    invalid_path = client.get("/api/v1/report-handoffs/0", headers=trainer_headers)

    assert too_long.status_code == 422
    assert future.status_code == 422
    assert invalid_path.status_code == 422


def test_handoff_metadata_is_exported_without_payload_and_deleted_with_sender(client) -> None:
    sender_headers = _auth(client, 83_301)
    trainer_headers = _auth(client, 83_302, is_coach=True)
    sender_id = _user_id(83_301)
    trainer_id = _user_id(83_302)
    _link(sender_id, trainer_id)

    created = client.post(
        "/api/v1/report-handoffs",
        json={"period": "days_7"},
        headers={**sender_headers, "Idempotency-Key": "handoff-83-export"},
    )
    assert created.status_code == 201, created.text
    handoff_id = created.json()["id"]

    with get_session_context() as db:
        sender = db.get(User, sender_id)
        assert sender is not None
        exported = build_account_export(db, sender)
        rows = exported["report_handoffs"]
        assert isinstance(rows, list)
        assert rows[0]["id"] == handoff_id
        assert rows[0]["role"] == "sender"
        assert "report_revision" not in rows[0]
        assert "request_fingerprint" not in rows[0]
        assert "report" not in rows[0]

    with get_session_context() as db:
        sender = db.get(User, sender_id)
        assert sender is not None
        delete_user_cascade(db, sender)

    with get_session_context() as db:
        assert db.get(User, sender_id) is None
        assert db.get(User, trainer_id) is not None
        assert db.get(ReportHandoff, handoff_id) is None
        assert db.query(CoachClient).filter_by(client_user_id=sender_id).count() == 0
    assert (
        client.get(f"/api/v1/report-handoffs/{handoff_id}", headers=trainer_headers).status_code
        == 404
    )
