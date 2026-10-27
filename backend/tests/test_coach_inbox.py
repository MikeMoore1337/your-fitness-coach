from __future__ import annotations

import json
from datetime import timedelta

from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.performance import begin_sql_metrics, current_sql_metrics, reset_sql_metrics
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services.coach_inbox import build_coach_inbox


def _login(client, telegram_user_id: int, *, is_coach: bool) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "username": f"inbox_{telegram_user_id}",
            "is_coach": is_coach,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user(db, telegram_user_id: int) -> User:
    return db.query(User).filter(User.telegram_user_id == telegram_user_id).one()


def test_coach_inbox_composes_sources_without_duplicate_or_private_notes(client) -> None:
    coach_headers = _login(client, 986_001, is_coach=True)
    _login(client, 986_010, is_coach=False)
    today = today_msk()
    now = now_msk_naive()

    with get_session_context() as db:
        coach = _user(db, 986_001)
        managed = _user(db, 986_010)
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=managed.id))
        db.add(
            WeeklyCheckIn(
                user_id=managed.id,
                week_start=today - timedelta(days=7),
                week_end=today - timedelta(days=1),
                submitted_on=today - timedelta(days=1),
                timezone="Europe/Moscow",
                status="completed",
                summary_version="test-v1",
                summary={"private": "Секретный итог"},
                note="Секретная заметка клиента",
                created_at=now,
            )
        )
        db.commit()

    task = client.post(
        "/api/v1/coach/tasks",
        headers={**coach_headers, "Idempotency-Key": "inbox-task-0001"},
        json={
            "client_id": _user_id(client, 986_010),
            "title": "Проверить следующий шаг",
            "due_at": f"{today}T12:00:00",
            "timezone": "Europe/Moscow",
            "kind": "other",
        },
    )
    assert task.status_code == 201, task.text

    package = client.post(
        "/api/v1/coach/packages",
        headers={**coach_headers, "Idempotency-Key": "inbox-package-0001"},
        json={
            "client_id": _user_id(client, 986_010),
            "name": "Сопровождение",
            "counts_sessions": True,
            "included_sessions": 2,
        },
    )
    assert package.status_code == 201, package.text
    package_id = package.json()["id"]

    session = client.post(
        "/api/v1/coach/sessions",
        headers={**coach_headers, "Idempotency-Key": "inbox-session-0001"},
        json={
            "client_id": _user_id(client, 986_010),
            "starts_at": f"{today}T23:00:00",
            "timezone": "Europe/Moscow",
            "duration_minutes": 60,
            "format": "online",
            "private_note": "Секретная заметка тренера",
            "package_id": package_id,
        },
    )
    assert session.status_code == 201, session.text

    payment = client.post(
        "/api/v1/coach/payments",
        headers={**coach_headers, "Idempotency-Key": "inbox-payment-0001"},
        json={
            "client_id": _user_id(client, 986_010),
            "expected_amount_minor": 100000,
            "paid_amount_minor": 0,
            "currency": "RUB",
            "note": "Секретная финансовая заметка",
        },
    )
    assert payment.status_code == 201, payment.text

    response = client.get("/api/v1/coach/inbox?limit=100", headers=coach_headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["counts"] == {
        "attention": 2,
        "pending_reviews": 1,
        "tasks": 1,
        "sessions": 1,
        "packages": 1,
        "payments": 1,
    }
    assert {item["kind"] for item in payload["items"]} == {
        "attention",
        "task",
        "session",
        "package",
        "payment",
    }
    assert len({item["key"] for item in payload["items"]}) == len(payload["items"])
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "Секретный" not in encoded
    assert "private_note" not in encoded
    assert "summary" not in encoded


def _user_id(client, telegram_user_id: int) -> int:
    del client
    with get_session_context() as db:
        return int(_user(db, telegram_user_id).id)


def test_coach_inbox_query_count_is_bounded_for_10_30_and_100_clients(client) -> None:
    query_counts: list[int] = []
    for index, client_count in enumerate((10, 30, 100), start=1):
        coach_telegram_id = 986_100 + index
        _login(client, coach_telegram_id, is_coach=True)
        with get_session_context() as db:
            coach = _user(db, coach_telegram_id)
            managed_clients = [
                User(
                    telegram_user_id=986_200 + index * 1_000 + client_index,
                    username=f"inbox_scale_{index}_{client_index}",
                )
                for client_index in range(client_count)
            ]
            db.add_all(managed_clients)
            db.flush()
            db.add_all(
                [
                    CoachClient(coach_user_id=coach.id, client_user_id=managed.id)
                    for managed in managed_clients
                ]
            )
            db.commit()
            db.refresh(coach)

            token = begin_sql_metrics()
            try:
                result = build_coach_inbox(db, coach, limit=100)
                metrics = current_sql_metrics()
            finally:
                reset_sql_metrics(token)

        query_counts.append(metrics.query_count)
        assert result["counts"]["attention"] == client_count

    assert max(query_counts) <= 24
    assert max(query_counts) - min(query_counts) <= 2
