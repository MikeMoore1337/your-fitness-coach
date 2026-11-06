import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier, Event

import pytest

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.nutrition import NutritionTarget, NutritionTargetDateOverride
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services import nutrition as nutrition_service


def _auth(client, user_id: int, *, coach: bool = False) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": user_id, "is_coach": coach}
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_date_override_is_idempotent_and_used_consistently(client) -> None:
    headers = _auth(client, 952300)
    today = today_msk()
    base = {"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 180}
    assert (
        client.post("/api/v1/nutrition/targets/manual", json=base, headers=headers).status_code
        == 200
    )
    override = {**base, "calories": 2300, "carbs_g": 270, "effective_from": today.isoformat()}
    key_headers = {**headers, "Idempotency-Key": "date-override-952"}
    first = client.post("/api/v1/nutrition/targets/dates", json=override, headers=key_headers)
    retry = client.post("/api/v1/nutrition/targets/dates", json=override, headers=key_headers)
    assert first.status_code == retry.status_code == 200
    assert first.json()["target"]["id"] == retry.json()["target"]["id"]
    assert first.json()["target"]["effective_to"] == (today + timedelta(days=1)).isoformat()
    conflict = client.post(
        "/api/v1/nutrition/targets/dates", json={**override, "calories": 2400}, headers=key_headers
    )
    assert conflict.status_code == 409

    day = client.get(
        "/api/v1/nutrition/diary", params={"diary_date": today.isoformat()}, headers=headers
    )
    tomorrow = client.get(
        "/api/v1/nutrition/plans/day",
        params={"plan_date": (today + timedelta(days=1)).isoformat()},
        headers=headers,
    )
    report = client.get(
        "/api/v1/workouts/progress/nutrition-report",
        params={"period": "custom", "date_from": today.isoformat(), "date_to": today.isoformat()},
        headers=headers,
    )
    exported = client.get(
        "/api/v1/workouts/progress/nutrition-report.csv",
        params={"period": "custom", "date_from": today.isoformat(), "date_to": today.isoformat()},
        headers=headers,
    )
    progress = client.get("/api/v1/workouts/progress/summary?period_days=7", headers=headers)
    assert [response.status_code for response in (day, tomorrow, report, exported, progress)] == [
        200
    ] * 5
    assert Decimal(day.json()["targets"]["energy_kcal"]) == 2300
    assert Decimal(tomorrow.json()["targets"]["energy_kcal"]) == 2000
    assert report.json()["daily"][0]["target_calories"] == 2300
    csv_day = next(
        row
        for row in csv.DictReader(io.StringIO(exported.text.lstrip("\ufeff")))
        if row["diary_date"] == today.isoformat()
    )
    assert Decimal(csv_day["target_calories_kcal"]) == 2300
    assert progress.json()["nutrition"]["target_calories"] == 2300

    completed = client.put(
        "/api/v1/nutrition/diary/status",
        json={"diary_date": today.isoformat(), "status": "fasted"},
        headers=headers,
    )
    assert completed.status_code == 200
    denied = client.post(
        "/api/v1/nutrition/targets/dates",
        json={**base, "effective_from": today.isoformat()},
        headers={**headers, "Idempotency-Key": "another-override-952"},
    )
    assert denied.status_code == 409
    assert (
        client.post("/api/v1/nutrition/targets/dates", json=override, headers=key_headers).json()
        == first.json()
    )
    changed_base = client.post(
        "/api/v1/nutrition/targets/manual",
        json={**base, "calories": 2500, "carbs_g": 315},
        headers=headers,
    )
    assert changed_base.status_code == 200
    after = client.get(
        "/api/v1/nutrition/diary", params={"diary_date": today.isoformat()}, headers=headers
    )
    assert Decimal(after.json()["targets"]["energy_kcal"]) == 2300


def test_date_override_rejects_past_and_revoked_trainer(client) -> None:
    athlete = _auth(client, 952301)
    coach = _auth(client, 952302, coach=True)
    with get_session_context() as db:
        athlete_id = db.query(User.id).filter_by(telegram_user_id=952301).scalar()
        coach_id = db.query(User.id).filter_by(telegram_user_id=952302).scalar()
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=athlete_id, status="active"))
    payload = {
        "target_telegram_user_id": 952301,
        "calories": 2000,
        "protein_g": 150,
        "fat_g": 70,
        "carbs_g": 180,
        "effective_from": (today_msk() + timedelta(days=1)).isoformat(),
    }
    saved = client.post(
        "/api/v1/nutrition/targets/dates",
        json=payload,
        headers={**coach, "Idempotency-Key": "trainer-override-952"},
    )
    assert saved.status_code == 200
    past = client.post(
        "/api/v1/nutrition/targets/dates",
        json={
            **payload,
            "target_telegram_user_id": None,
            "effective_from": (today_msk() - timedelta(days=1)).isoformat(),
        },
        headers={**athlete, "Idempotency-Key": "past-override-952"},
    )
    assert past.status_code == 409
    with get_session_context() as db:
        db.query(CoachClient).filter_by(
            coach_user_id=coach_id, client_user_id=athlete_id
        ).one().status = "ended"
    denied = client.post(
        "/api/v1/nutrition/targets/dates",
        json=payload,
        headers={**coach, "Idempotency-Key": "trainer-override-952"},
    )
    assert denied.status_code == 403
    denied_history = client.get(
        "/api/v1/nutrition/targets/dates?target_telegram_user_id=952301", headers=coach
    )
    assert denied_history.status_code == 403


def test_override_history_export_and_account_deletion(client) -> None:
    headers = _auth(client, 952303)
    tomorrow = today_msk() + timedelta(days=1)
    payload = {
        "calories": 2000,
        "protein_g": 150,
        "fat_g": 70,
        "carbs_g": 180,
        "effective_from": tomorrow.isoformat(),
    }
    first = client.post(
        "/api/v1/nutrition/targets/dates",
        json=payload,
        headers={**headers, "Idempotency-Key": "first-date-override"},
    )
    second = client.post(
        "/api/v1/nutrition/targets/dates",
        json={**payload, "calories": 2300, "carbs_g": 270},
        headers={**headers, "Idempotency-Key": "second-date-override"},
    )
    assert first.status_code == second.status_code == 200
    plan = client.get(
        "/api/v1/nutrition/plans/day", params={"plan_date": tomorrow.isoformat()}, headers=headers
    )
    assert Decimal(plan.json()["targets"]["energy_kcal"]) == 2300
    assert client.get("/api/v1/nutrition/targets/history", headers=headers).json()["items"] == []
    history = client.get("/api/v1/nutrition/targets/dates", headers=headers)
    assert history.status_code == 200
    assert [row["target"]["id"] for row in history.json()] == [
        second.json()["target"]["id"],
        first.json()["target"]["id"],
    ]
    exported = client.get("/api/v1/me/export", headers=headers).json()
    assert [row["target_id"] for row in exported["nutrition_target_date_overrides"]] == [
        first.json()["target"]["id"],
        second.json()["target"]["id"],
    ]
    deleted = client.request(
        "DELETE", "/api/v1/me/account", json={"confirmation": "DELETE"}, headers=headers
    )
    assert deleted.status_code == 204
    with get_session_context() as db:
        assert db.get(NutritionTarget, first.json()["target"]["id"]) is None
        assert db.get(NutritionTarget, second.json()["target"]["id"]) is None


def test_deleting_trainer_anonymizes_override_author_without_deleting_client_goal(client) -> None:
    athlete = _auth(client, 952306)
    coach = _auth(client, 952307, coach=True)
    with get_session_context() as db:
        athlete_id = db.query(User.id).filter_by(telegram_user_id=952306).scalar()
        coach_id = db.query(User.id).filter_by(telegram_user_id=952307).scalar()
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=athlete_id, status="active"))
    saved = client.post(
        "/api/v1/nutrition/targets/dates",
        json={
            "target_telegram_user_id": 952306,
            "calories": 2000,
            "protein_g": 150,
            "fat_g": 70,
            "carbs_g": 180,
            "effective_from": today_msk().isoformat(),
        },
        headers={**coach, "Idempotency-Key": "trainer-date-goal"},
    )
    assert saved.status_code == 200
    deleted = client.request(
        "DELETE", "/api/v1/me/account", json={"confirmation": "DELETE"}, headers=coach
    )
    assert deleted.status_code == 204
    history = client.get("/api/v1/nutrition/targets/dates", headers=athlete)
    assert history.status_code == 200
    assert history.json()[0]["target"]["id"] == saved.json()["target"]["id"]
    assert history.json()[0]["target"]["created_by"] is None


def test_date_override_report_marks_start_and_return_to_baseline(client, monkeypatch) -> None:
    headers = _auth(client, 952304)
    today = today_msk()
    yesterday = today - timedelta(days=1)
    monkeypatch.setattr(nutrition_service, "today_for_user", lambda _user: yesterday)
    base = {
        "calories": 2000,
        "protein_g": 150,
        "fat_g": 70,
        "carbs_g": 180,
        "effective_from": yesterday.isoformat(),
    }
    assert (
        client.post("/api/v1/nutrition/targets/manual", json=base, headers=headers).status_code
        == 200
    )
    override = client.post(
        "/api/v1/nutrition/targets/dates",
        json={**base, "calories": 2300, "carbs_g": 270},
        headers={**headers, "Idempotency-Key": "historical-date-952"},
    )
    assert override.status_code == 200
    monkeypatch.setattr(nutrition_service, "today_for_user", lambda _user: today)
    report = client.get(
        "/api/v1/workouts/progress/nutrition-report",
        params={
            "period": "custom",
            "date_from": yesterday.isoformat(),
            "date_to": today.isoformat(),
        },
        headers=headers,
    )
    assert report.status_code == 200
    assert [row["target_calories"] for row in report.json()["daily"]] == [2300, 2000]
    assert [
        (row["effective_from"], row["calories"]) for row in report.json()["target_changes"]
    ] == [
        (yesterday.isoformat(), 2300),
        (today.isoformat(), 2000),
    ]


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_date_override_retry_creates_one_version(client) -> None:
    headers = {**_auth(client, 952305), "Idempotency-Key": "concurrent-date-override"}
    payload = {
        "calories": 2000,
        "protein_g": 150,
        "fat_g": 70,
        "carbs_g": 180,
        "effective_from": today_msk().isoformat(),
    }
    barrier = Barrier(2)

    def save():
        barrier.wait(timeout=5)
        return client.post("/api/v1/nutrition/targets/dates", json=payload, headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(save), pool.submit(save)
        first, second = first.result(), second.result()
    assert first.status_code == second.status_code == 200
    assert first.json()["target"]["id"] == second.json()["target"]["id"]
    with get_session_context() as db:
        user_id = db.query(User.id).filter_by(telegram_user_id=952305).scalar()
        assert db.query(NutritionTargetDateOverride).filter_by(user_id=user_id).count() == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_revoked_trainer_cannot_finish_a_write_started_before_revocation(
    client, monkeypatch
) -> None:
    _auth(client, 952308)
    coach = _auth(client, 952309, coach=True)
    with get_session_context() as db:
        athlete_id = db.query(User.id).filter_by(telegram_user_id=952308).scalar()
        coach_id = db.query(User.id).filter_by(telegram_user_id=952309).scalar()
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=athlete_id, status="active"))
    authorized_read = Event()
    original = nutrition_service._resolve_target_user

    def signal_after_initial_check(*args, **kwargs):
        result = original(*args, **kwargs)
        authorized_read.set()
        return result

    monkeypatch.setattr(nutrition_service, "_resolve_target_user", signal_after_initial_check)
    payload = {
        "target_telegram_user_id": 952308,
        "calories": 2000,
        "protein_g": 150,
        "fat_g": 70,
        "carbs_g": 180,
        "effective_from": today_msk().isoformat(),
    }
    with ThreadPoolExecutor(max_workers=1) as pool:
        with get_session_context() as db:
            relation = (
                db.query(CoachClient)
                .filter_by(coach_user_id=coach_id, client_user_id=athlete_id)
                .with_for_update()
                .one()
            )
            relation.status = "ended"
            db.flush()
            request = pool.submit(
                client.post,
                "/api/v1/nutrition/targets/dates",
                json=payload,
                headers={**coach, "Idempotency-Key": "revoked-date-write"},
            )
            assert authorized_read.wait(timeout=5)
            assert not request.done()
        response = request.result(timeout=10)
    assert response.status_code == 403
    with get_session_context() as db:
        assert db.query(NutritionTargetDateOverride).filter_by(user_id=athlete_id).count() == 0
