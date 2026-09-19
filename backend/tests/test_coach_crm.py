from datetime import date, datetime

import pytest

from fitminiapp_api.core.timezone import local_naive_to_utc_naive_strict
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.coach_crm import (
    CoachBusinessSession,
    CoachPackage,
    CoachPackageLedgerEntry,
    CoachPayment,
    CoachSessionSeries,
    CoachTask,
)
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services.accounts import delete_user_cascade


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_id(telegram_user_id: int) -> int:
    with get_session_context() as db:
        return db.query(User.id).filter(User.telegram_user_id == telegram_user_id).one()[0]


def _link(coach_telegram_id: int, client_telegram_id: int) -> tuple[int, int]:
    coach_id = _user_id(coach_telegram_id)
    client_id = _user_id(client_telegram_id)
    with get_session_context() as db:
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=client_id))
    return coach_id, client_id


def test_crm_sessions_are_separate_from_workouts_and_package_ledger_is_traceable(client) -> None:
    coach_headers = _auth(client, 29_201, is_coach=True)
    client_headers = _auth(client, 29_202)
    _coach_id, client_id = _link(29_201, 29_202)
    with get_session_context() as db:
        db.query(CoachClient).filter(
            CoachClient.coach_user_id == _coach_id,
            CoachClient.client_user_id == client_id,
        ).update({CoachClient.operational_status: None})

    roster = client.get("/api/v1/coach/clients", headers=coach_headers)
    assert roster.status_code == 200, roster.text
    assert (
        next(row for row in roster.json() if row["id"] == client_id)["operational_status"]
        == "active"
    )

    package = client.post(
        "/api/v1/coach/packages",
        headers={**coach_headers, "Idempotency-Key": "package-crm-0001"},
        json={
            "client_id": client_id,
            "name": "8 занятий",
            "counts_sessions": True,
            "included_sessions": 8,
            "starts_on": "2026-09-01",
        },
    )
    assert package.status_code == 201, package.text
    package_payload = package.json()
    assert package_payload["balance"] == 8
    replay_package = client.post(
        "/api/v1/coach/packages",
        headers={**coach_headers, "Idempotency-Key": "package-crm-0001"},
        json={
            "client_id": client_id,
            "name": "8 занятий",
            "counts_sessions": True,
            "included_sessions": 8,
        },
    )
    assert replay_package.status_code == 201
    assert replay_package.json()["id"] == package_payload["id"]

    session_payload = {
        "client_id": client_id,
        "starts_at": "2026-09-21T10:00:00",
        "timezone": "Europe/Moscow",
        "duration_minutes": 60,
        "format": "gym",
        "location": "Зал 1",
        "private_note": "Проверить технику приседа",
        "package_id": package_payload["id"],
    }
    created = client.post(
        "/api/v1/coach/sessions",
        headers={**coach_headers, "Idempotency-Key": "session-crm-0001"},
        json=session_payload,
    )
    assert created.status_code == 201, created.text
    session = created.json()[0]
    assert session["user_workout_id"] is None
    assert session["starts_at"].endswith("+03:00")

    replay = client.post(
        "/api/v1/coach/sessions",
        headers={**coach_headers, "Idempotency-Key": "session-crm-0001"},
        json=session_payload,
    )
    assert replay.status_code == 201
    assert [item["id"] for item in replay.json()] == [session["id"]]

    overlap = client.post(
        "/api/v1/coach/sessions",
        headers=coach_headers,
        json={**session_payload, "starts_at": "2026-09-21T10:30:00"},
    )
    assert overlap.status_code == 409, overlap.text

    completed = client.patch(
        f"/api/v1/coach/sessions/{session['id']}",
        headers=coach_headers,
        json={"status": "completed"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["package_balance"] == 7
    repeated = client.patch(
        f"/api/v1/coach/sessions/{session['id']}",
        headers=coach_headers,
        json={"status": "completed"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["package_balance"] == 7

    cancelled = client.patch(
        f"/api/v1/coach/sessions/{session['id']}",
        headers=coach_headers,
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["package_balance"] == 8

    completed_to_no_show = client.patch(
        f"/api/v1/coach/sessions/{session['id']}",
        headers=coach_headers,
        json={"status": "completed"},
    )
    assert completed_to_no_show.status_code == 200
    assert completed_to_no_show.json()["package_balance"] == 7
    no_show_without_charge = client.patch(
        f"/api/v1/coach/sessions/{session['id']}",
        headers=coach_headers,
        json={"status": "no_show"},
    )
    assert no_show_without_charge.status_code == 200
    assert no_show_without_charge.json()["package_balance"] == 8
    no_show_with_charge = client.patch(
        f"/api/v1/coach/sessions/{session['id']}",
        headers=coach_headers,
        json={"status": "no_show", "charge_package": True},
    )
    assert no_show_with_charge.status_code == 200
    assert no_show_with_charge.json()["package_balance"] == 7

    no_show = client.post(
        "/api/v1/coach/sessions",
        headers=coach_headers,
        json={**session_payload, "starts_at": "2026-09-21T12:00:00"},
    )
    assert no_show.status_code == 201, no_show.text
    no_show_id = no_show.json()[0]["id"]
    no_show_result = client.patch(
        f"/api/v1/coach/sessions/{no_show_id}",
        headers=coach_headers,
        json={"status": "no_show"},
    )
    assert no_show_result.status_code == 200
    assert no_show_result.json()["package_balance"] == 7
    charged_no_show = client.patch(
        f"/api/v1/coach/sessions/{no_show_id}",
        headers=coach_headers,
        json={"status": "completed"},
    )
    assert charged_no_show.status_code == 200
    assert charged_no_show.json()["package_balance"] == 6

    recurrence = client.post(
        "/api/v1/coach/sessions",
        headers={**coach_headers, "Idempotency-Key": "series-crm-0001"},
        json={
            "client_id": client_id,
            "starts_at": "2026-09-22T09:00:00",
            "timezone": "Europe/Moscow",
            "duration_minutes": 45,
            "format": "online",
            "recurrence": {"weekdays": [1], "occurrence_count": 3},
        },
    )
    assert recurrence.status_code == 201, recurrence.text
    assert len(recurrence.json()) == 3
    series_id = recurrence.json()[0]["series_id"]
    replay_series = client.post(
        "/api/v1/coach/sessions",
        headers={**coach_headers, "Idempotency-Key": "series-crm-0001"},
        json={
            "client_id": client_id,
            "starts_at": "2026-09-22T09:00:00",
            "timezone": "Europe/Moscow",
            "duration_minutes": 45,
            "format": "online",
            "recurrence": {"weekdays": [1], "occurrence_count": 3},
        },
    )
    assert replay_series.status_code == 201
    assert [item["id"] for item in replay_series.json()] == [
        item["id"] for item in recurrence.json()
    ]
    assert all(item["series_id"] == series_id for item in recurrence.json())

    payment = client.post(
        "/api/v1/coach/payments",
        headers={**coach_headers, "Idempotency-Key": "payment-crm-0001"},
        json={
            "client_id": client_id,
            "package_id": package_payload["id"],
            "expected_amount_minor": 12_500,
            "paid_amount_minor": 5_000,
            "currency": "RUB",
            "payment_date": "2026-09-19",
            "method": "перевод",
        },
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["status"] == "partial"
    assert payment.json()["expected_amount_minor"] == 12_500
    edited_payment = client.patch(
        f"/api/v1/coach/payments/{payment.json()['id']}",
        headers=coach_headers,
        json={"paid_amount_minor": 12_500},
    )
    assert edited_payment.status_code == 200, edited_payment.text
    assert edited_payment.json()["status"] == "paid"

    task = client.post(
        "/api/v1/coach/tasks",
        headers={**coach_headers, "Idempotency-Key": "task-crm-0001"},
        json={
            "client_id": client_id,
            "title": "Проверить дневник питания",
            "due_at": "2026-09-21T08:00:00",
            "timezone": "Europe/Moscow",
        },
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]
    closed_task = client.patch(
        f"/api/v1/coach/tasks/{task_id}/state",
        headers=coach_headers,
        json={"state": "completed"},
    )
    assert closed_task.status_code == 200
    assert closed_task.json()["state"] == "completed"

    operations = client.get(f"/api/v1/coach/clients/{client_id}/operations", headers=coach_headers)
    assert operations.status_code == 200, operations.text
    assert operations.json()["packages"][0]["balance"] == 6
    assert operations.json()["payments"][0]["status"] == "paid"

    export = client.get("/api/v1/me/export", headers=coach_headers)
    assert export.status_code == 200, export.text
    assert export.json()["coaching_relationships"][0]["operational_status"] == "active"
    assert export.json()["coach_business_sessions"]
    assert export.json()["coach_package_ledger"]
    assert export.json()["coach_payments"]
    assert export.json()["coach_tasks"]

    client_export = client.get("/api/v1/me/export", headers=client_headers)
    assert client_export.status_code == 200, client_export.text
    client_payload = client_export.json()
    assert client_payload["coach_package_ledger"] == []
    assert client_payload["coach_tasks"] == []
    assert all("private_note" not in item for item in client_payload["coach_business_sessions"])
    assert all("note" not in item for item in client_payload["coach_payments"])
    assert all("note" not in item for item in client_payload["coach_packages"])
    assert all(
        "operational_status" not in item for item in client_payload["coaching_relationships"]
    )

    with get_session_context() as db:
        assert (
            db.query(CoachPackageLedgerEntry).filter_by(package_id=package_payload["id"]).count()
            == 6
        )


def test_client_profile_weight_preserves_fractional_values_and_missing_state(client) -> None:
    coach_headers = _auth(client, 29_231, is_coach=True)
    client_headers = _auth(client, 29_232)
    other_coach_headers = _auth(client, 29_233, is_coach=True)
    _coach_id, client_id = _link(29_231, 29_232)

    measurement = client.post(
        f"/api/v1/coach/clients/{client_id}/measurements",
        headers=coach_headers,
        json={"measured_on": date.today().isoformat(), "weight_kg": 78.4, "waist_cm": 82.0},
    )
    assert measurement.status_code == 200, measurement.text
    assert measurement.json()["weight_kg"] == 78.4

    fractional_profile = client.patch(
        f"/api/v1/coach/clients/{client_id}/profile",
        headers=coach_headers,
        json={"weight_kg": 78.4},
    )
    assert fractional_profile.status_code == 200, fractional_profile.text
    assert fractional_profile.json()["weight_kg"] == 78.4

    roster = client.get("/api/v1/coach/clients", headers=coach_headers)
    assert roster.status_code == 200, roster.text
    listed_client = next(row for row in roster.json() if row["id"] == client_id)
    assert listed_client["weight_kg"] == 78.4
    assert client.get("/api/v1/me", headers=client_headers).json()["profile"]["weight_kg"] == 78.4

    integer_profile = client.patch(
        f"/api/v1/coach/clients/{client_id}/profile",
        headers=coach_headers,
        json={"weight_kg": 78},
    )
    assert integer_profile.status_code == 200, integer_profile.text
    assert integer_profile.json()["weight_kg"] == 78

    missing_profile = client.patch(
        f"/api/v1/coach/clients/{client_id}/profile",
        headers=coach_headers,
        json={"weight_kg": None},
    )
    assert missing_profile.status_code == 200, missing_profile.text
    assert missing_profile.json()["weight_kg"] is None
    missing_roster = client.get("/api/v1/coach/clients", headers=coach_headers)
    assert missing_roster.status_code == 200, missing_roster.text
    assert next(row for row in missing_roster.json() if row["id"] == client_id)["weight_kg"] is None

    history = client.get(f"/api/v1/coach/clients/{client_id}/measurements", headers=coach_headers)
    assert history.status_code == 200, history.text
    assert history.json()[0]["weight_kg"] == 78.4
    assert history.json()[0]["waist_cm"] == 82.0

    assert (
        client.patch(
            f"/api/v1/coach/clients/{client_id}/profile",
            headers=other_coach_headers,
            json={"weight_kg": 79.2},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/coach/clients/{client_id}/measurements",
            headers=other_coach_headers,
        ).status_code
        == 404
    )


def test_crm_rejects_nonexistent_dst_wall_time_and_isolates_coaches(client) -> None:
    with pytest.raises(ValueError):
        local_naive_to_utc_naive_strict(datetime(2026, 3, 8, 2, 30), "America/New_York")

    coach_headers = _auth(client, 29_211, is_coach=True)
    other_coach_headers = _auth(client, 29_212, is_coach=True)
    _auth(client, 29_213)
    _link(29_211, 29_213)
    client_id = _user_id(29_213)
    payload = {
        "client_id": client_id,
        "starts_at": "2026-09-23T10:00:00",
        "timezone": "Europe/Moscow",
        "duration_minutes": 60,
    }
    created = client.post("/api/v1/coach/sessions", headers=coach_headers, json=payload)
    assert created.status_code == 201, created.text
    assert client.get("/api/v1/coach/agenda", headers=other_coach_headers).status_code == 200
    assert (
        client.get(
            f"/api/v1/coach/clients/{client_id}/operations", headers=other_coach_headers
        ).status_code
        == 404
    )


def test_crm_records_are_removed_with_account(client) -> None:
    coach_headers = _auth(client, 29_221, is_coach=True)
    _auth(client, 29_222)
    coach_id, client_id = _link(29_221, 29_222)
    package = client.post(
        "/api/v1/coach/packages",
        headers=coach_headers,
        json={"client_id": client_id, "name": "CRM", "included_sessions": 2},
    ).json()
    client.post(
        "/api/v1/coach/sessions",
        headers=coach_headers,
        json={
            "client_id": client_id,
            "package_id": package["id"],
            "starts_at": "2026-09-24T10:00:00",
            "timezone": "Europe/Moscow",
        },
    )
    with get_session_context() as db:
        user = db.get(User, coach_id)
        assert user is not None
        delete_user_cascade(db, user)
        db.flush()
        assert db.query(CoachBusinessSession).filter_by(coach_user_id=coach_id).count() == 0
        assert db.query(CoachSessionSeries).filter_by(coach_user_id=coach_id).count() == 0
        assert db.query(CoachPackage).filter_by(coach_user_id=coach_id).count() == 0
        assert db.query(CoachPayment).filter_by(coach_user_id=coach_id).count() == 0
        assert db.query(CoachTask).filter_by(coach_user_id=coach_id).count() == 0
