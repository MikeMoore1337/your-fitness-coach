from __future__ import annotations

from datetime import timedelta

import pytest

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.coach_crm import CoachTask
from fitminiapp_api.models.user import CoachClient, User, UserProfile


def _login(client, telegram_user_id: int, *, is_coach: bool, is_admin: bool = False):
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "username": f"capacity_{telegram_user_id}",
            "is_coach": is_coach,
            "is_admin": is_admin,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user(db, telegram_user_id: int) -> User:
    return db.query(User).filter(User.telegram_user_id == telegram_user_id).one()


def _add_clients(db, coach: User, *, count: int, telegram_start: int) -> list[User]:
    clients = [
        User(
            telegram_user_id=telegram_start + index,
            username=f"capacity_client_{telegram_start + index}",
        )
        for index in range(count)
    ]
    db.add_all(clients)
    db.flush()
    db.add_all(
        [UserProfile(user_id=client.id, full_name=f"Клиент {client.id}") for client in clients]
    )
    db.add_all(
        [CoachClient(coach_user_id=coach.id, client_user_id=client.id) for client in clients]
    )
    return clients


@pytest.mark.parametrize(
    ("client_count", "expected_band"),
    ((9, "0_9"), (10, "10_29"), (30, "30_99"), (100, "100_plus")),
)
def test_capacity_reports_scale_boundaries_from_authorized_roster(
    client, client_count: int, expected_band: str
) -> None:
    headers = _login(client, 539_001 + client_count, is_coach=True)
    with get_session_context() as db:
        coach = _user(db, 539_001 + client_count)
        _add_clients(db, coach, count=client_count, telegram_start=540_000 + client_count * 100)
        db.commit()

    response = client.get("/api/v1/coach/capacity", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["active_client_count"] == client_count
    assert payload["capacity_band"] == expected_band
    assert payload["scale_boundaries"] == [10, 30, 100]
    assert payload["attention_item_count"] == client_count
    assert payload["attention_client_count"] == client_count
    assert payload["attention_items_truncated"] is False
    assert payload["roster_coverage_percent"] == 0
    assert "client_id" not in response.text


def test_capacity_is_scoped_to_one_coach_and_rejects_client_access(client) -> None:
    first_headers = _login(client, 541_001, is_coach=True)
    second_headers = _login(client, 541_002, is_coach=True)
    client_headers = _login(client, 541_010, is_coach=False)

    with get_session_context() as db:
        first_coach = _user(db, 541_001)
        second_coach = _user(db, 541_002)
        first_client = _add_clients(db, first_coach, count=1, telegram_start=541_100)[0]
        _add_clients(db, second_coach, count=1, telegram_start=541_200)
        db.add(
            CoachTask(
                coach_user_id=first_coach.id,
                client_user_id=first_client.id,
                title="Проверить следующий шаг",
                due_at_utc=now_msk_naive() + timedelta(days=1),
                timezone="Europe/Moscow",
                kind="other",
            )
        )
        db.commit()

    first = client.get("/api/v1/coach/capacity", headers=first_headers)
    second = client.get("/api/v1/coach/capacity", headers=second_headers)
    forbidden = client.get("/api/v1/coach/capacity", headers=client_headers)

    assert first.status_code == 200
    assert first.json()["active_client_count"] == 1
    assert first.json()["open_task_count"] == 1
    assert second.status_code == 200
    assert second.json()["active_client_count"] == 1
    assert second.json()["open_task_count"] == 0
    assert forbidden.status_code == 403


def test_root_trainer_capacity_report_is_separate_from_client_funnel(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "542001")
    root_headers = _login(client, 542_001, is_coach=False, is_admin=True)
    trainer_headers = _login(client, 542_002, is_coach=True)
    _login(client, 542_010, is_coach=False)

    with get_session_context() as db:
        trainer = _user(db, 542_002)
        managed = _user(db, 542_010)
        relation = CoachClient(coach_user_id=trainer.id, client_user_id=managed.id)
        db.add(relation)
        db.flush()
        activation_at = now_msk_naive() - timedelta(hours=2)
        db.add(
            AuditEvent(
                actor_user_id=trainer.id,
                target_user_id=trainer.id,
                action="trainer_capability.activated",
                resource_type="user",
                resource_id=str(trainer.id),
                details={"terms_version": "trainer-capability-v1"},
                created_at=activation_at,
            )
        )
        db.add(
            AuditEvent(
                actor_user_id=trainer.id,
                target_user_id=trainer.id,
                action="trainer_capability.activated",
                resource_type="user",
                resource_id=str(trainer.id),
                details={"terms_version": "trainer-capability-v1"},
                created_at=activation_at + timedelta(minutes=5),
            )
        )
        db.add(
            AuditEvent(
                actor_user_id=trainer.id,
                target_user_id=managed.id,
                action="coach.task_created",
                resource_type="coach_task",
                resource_id="539001",
                details={"state": "open"},
                created_at=activation_at + timedelta(minutes=15),
            )
        )
        db.commit()

    report = client.get("/api/v1/admin/trainer-capacity?period_days=30", headers=root_headers)
    forbidden = client.get("/api/v1/admin/trainer-capacity", headers=trainer_headers)

    assert report.status_code == 200, report.text
    payload = report.json()
    assert payload["activated_trainer_count"] == 1
    assert payload["trainer_activation_rate_percent"] is not None
    assert 0 < payload["trainer_activation_rate_percent"] <= 100
    assert payload["active_trainer_count"] == 1
    assert payload["active_client_count"] == 1
    assert payload["authorized_client_action_success_count"] == 1
    assert payload["time_to_first_client_action_median_seconds"] == 900
    assert payload["authorized_client_action_failure_count"] is None
    assert payload["response_time_status"] == "not_measured"
    assert payload["capacity_bands"][0]["trainer_count"] == 1
    assert payload["capacity_bands"][0]["active_client_count"] == 1
    assert "kpis" not in payload
    assert "Клиентский funnel" in payload["coverage_note"]
    assert forbidden.status_code == 403
