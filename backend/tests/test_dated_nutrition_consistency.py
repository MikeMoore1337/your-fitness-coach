from __future__ import annotations

import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from threading import Barrier

import pytest

from fitminiapp_api.core import timezone as timezone_module
from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus
from fitminiapp_api.models.nutrition import NutritionTarget, NutritionTargetDaySnapshot
from fitminiapp_api.models.user import User
from fitminiapp_api.services import nutrition as nutrition_service


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (-11, None),
        (-5, (2000, 150, 70, 200)),
        (0, (1800, 140, 60, 180)),
    ],
)
def test_diary_report_and_csv_use_the_same_dated_target(client, offset, expected) -> None:
    login = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 952001, "is_coach": False},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    today = today_msk()
    selected_date = today + timedelta(days=offset)
    change_day = today - timedelta(days=3)
    with get_session_context() as db:
        user_id = db.query(User.id).filter(User.telegram_user_id == 952001).scalar()
        db.add_all(
            [
                NutritionTarget(
                    user_id=user_id,
                    source="manual",
                    effective_from=today - timedelta(days=10),
                    effective_to=change_day,
                    calories=2000,
                    protein_g=150,
                    fat_g=70,
                    carbs_g=200,
                    saved_at=datetime.combine(today - timedelta(days=10), time()),
                ),
                NutritionTarget(
                    user_id=user_id,
                    source="manual",
                    effective_from=change_day,
                    calories=1800,
                    protein_g=140,
                    fat_g=60,
                    carbs_g=180,
                    saved_at=datetime.combine(change_day, time()),
                ),
            ]
        )

    params = {
        "period": "custom",
        "date_from": selected_date.isoformat(),
        "date_to": today.isoformat(),
    }
    report = client.get(
        "/api/v1/workouts/progress/nutrition-report", params=params, headers=headers
    )
    export = client.get(
        "/api/v1/workouts/progress/nutrition-report.csv", params=params, headers=headers
    )
    diary = client.get(
        "/api/v1/nutrition/diary", params={"diary_date": selected_date.isoformat()}, headers=headers
    )
    assert report.status_code == export.status_code == diary.status_code == 200
    report_day = next(
        day for day in report.json()["daily"] if day["diary_date"] == selected_date.isoformat()
    )
    csv_day = next(
        row
        for row in csv.DictReader(io.StringIO(export.text.lstrip("\ufeff")))
        if row["diary_date"] == selected_date.isoformat()
    )
    targets = diary.json()["targets"]
    if expected is None:
        assert targets is None
        assert report_day["target_calories"] is None
        assert csv_day["target_calories_kcal"] == ""
        return

    for value, diary_key, report_key, csv_key in zip(
        expected,
        ("energy_kcal", "protein_g", "fat_g", "carbs_g"),
        ("target_calories", "target_protein_g", "target_fat_g", "target_carbs_g"),
        ("target_calories_kcal", "target_protein_g", "target_fat_g", "target_carbs_g"),
        strict=True,
    ):
        assert Decimal(targets[diary_key]) == Decimal(value)
        assert report_day[report_key] == value
        assert Decimal(csv_day[csv_key]) == Decimal(value)


@pytest.mark.parametrize("initial_target", [True, False])
def test_completed_day_keeps_its_target_when_baseline_changes(client, initial_target) -> None:
    login = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 952002, "is_coach": False},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    today = today_msk().isoformat()
    initial = {"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 180}
    if initial_target:
        saved = client.post("/api/v1/nutrition/targets/manual", json=initial, headers=headers)
        assert saved.status_code == 200, saved.text

    completed = client.put(
        "/api/v1/nutrition/diary/status",
        json={"diary_date": today, "status": "fasted"},
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    changed = client.post(
        "/api/v1/nutrition/targets/manual",
        json={"calories": 2300, "protein_g": 160, "fat_g": 75, "carbs_g": 245},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["calories"] == 2300

    diary = client.get("/api/v1/nutrition/diary", params={"diary_date": today}, headers=headers)
    report = client.get(
        "/api/v1/workouts/progress/nutrition-report",
        params={"period": "custom", "date_from": today, "date_to": today},
        headers=headers,
    )
    csv_report = client.get(
        "/api/v1/workouts/progress/nutrition-report.csv",
        params={"period": "custom", "date_from": today, "date_to": today},
        headers=headers,
    )
    plan = client.get("/api/v1/nutrition/plans/day", params={"plan_date": today}, headers=headers)
    progress = client.get("/api/v1/workouts/progress/summary?period_days=7", headers=headers)
    assert diary.status_code == report.status_code == csv_report.status_code == 200
    assert plan.status_code == progress.status_code == 200
    expected = 2000 if initial_target else None
    assert (
        Decimal(diary.json()["targets"]["energy_kcal"])
        if diary.json()["targets"] is not None
        else None
    ) == expected
    assert report.json()["daily"][0]["target_calories"] == expected
    csv_day = next(
        row
        for row in csv.DictReader(io.StringIO(csv_report.text.lstrip("\ufeff")))
        if row["diary_date"] == today
    )
    assert csv_day["target_calories_kcal"] == (str(expected) if expected is not None else "")
    assert progress.json()["nutrition"]["target_calories"] == expected
    assert (
        Decimal(plan.json()["targets"]["energy_kcal"])
        if plan.json()["targets"] is not None
        else None
    ) == expected


def test_new_baseline_target_cannot_be_backdated(client) -> None:
    login = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 952003, "is_coach": False},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    yesterday = (today_msk() - timedelta(days=1)).isoformat()
    response = client.post(
        "/api/v1/nutrition/targets/manual",
        json={
            "calories": 2000,
            "protein_g": 150,
            "fat_g": 70,
            "carbs_g": 180,
            "effective_from": yesterday,
        },
        headers=headers,
    )
    assert response.status_code == 409
    history = client.get("/api/v1/nutrition/targets/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["items"] == []


def test_legacy_completed_day_is_frozen_and_included_in_account_lifecycle(client) -> None:
    login = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": 952004, "is_coach": False}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    today = today_msk()
    payload = {"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 180}
    target = client.post("/api/v1/nutrition/targets/manual", json=payload, headers=headers)
    assert target.status_code == 200
    with get_session_context() as db:
        user_id = db.query(User.id).filter_by(telegram_user_id=952004).scalar()
        db.add(FoodDiaryDayStatus(user_id=user_id, diary_date=today, status="fasted"))

    changed = client.post(
        "/api/v1/nutrition/targets/manual",
        json={**payload, "calories": 2300, "carbs_g": 270},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    exported = client.get("/api/v1/me/export", headers=headers)
    assert exported.status_code == 200
    assert exported.json()["nutrition_target_day_snapshots"][0]["target_id"] == target.json()["id"]
    deleted = client.request(
        "DELETE", "/api/v1/me/account", json={"confirmation": "DELETE"}, headers=headers
    )
    assert deleted.status_code == 204
    with get_session_context() as db:
        assert db.get(NutritionTargetDaySnapshot, (user_id, today)) is None
        assert db.get(NutritionTarget, target.json()["id"]) is None


def test_idempotent_retry_of_previous_day_is_allowed_but_changes_are_rejected(
    client, monkeypatch
) -> None:
    login = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": 952005, "is_coach": False}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    today = today_msk()
    payload = {
        "calories": 2000,
        "protein_g": 150,
        "fat_g": 70,
        "carbs_g": 180,
        "effective_from": (today - timedelta(days=1)).isoformat(),
    }
    monkeypatch.setattr(
        nutrition_service, "today_for_user", lambda _user: today - timedelta(days=1)
    )
    saved = client.post("/api/v1/nutrition/targets/manual", json=payload, headers=headers)
    monkeypatch.setattr(nutrition_service, "today_for_user", lambda _user: today)
    retry = client.post("/api/v1/nutrition/targets/manual", json=payload, headers=headers)
    changed = client.post(
        "/api/v1/nutrition/targets/manual",
        json={**payload, "calories": 2300, "carbs_g": 270},
        headers=headers,
    )
    assert saved.status_code == retry.status_code == 200
    assert saved.json()["id"] == retry.json()["id"]
    assert changed.status_code == 409
    assert "задним числом" in changed.json()["detail"]


def test_completed_target_survives_dst_and_timezone_change(client, monkeypatch) -> None:
    login = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": 952006, "is_coach": False}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    with get_session_context() as db:
        user = db.query(User).filter_by(telegram_user_id=952006).one()
        user.profile.timezone = "America/New_York"
    instant = [datetime(2026, 3, 8, 4, 30, tzinfo=UTC)]

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant[0].astimezone(tz) if tz else instant[0].replace(tzinfo=None)

    monkeypatch.setattr(timezone_module, "datetime", FrozenDateTime)
    payload = {"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 180}
    first = client.post("/api/v1/nutrition/targets/manual", json=payload, headers=headers)
    completed = client.put(
        "/api/v1/nutrition/diary/status",
        json={"diary_date": "2026-03-07", "status": "fasted"},
        headers=headers,
    )
    instant[0] = datetime(2026, 3, 8, 7, 30, tzinfo=UTC)
    second = client.post(
        "/api/v1/nutrition/targets/manual",
        json={**payload, "calories": 2300, "carbs_g": 270},
        headers=headers,
    )
    with get_session_context() as db:
        db.query(User).filter_by(telegram_user_id=952006).one().profile.timezone = "Asia/Tokyo"
    instant[0] = datetime(2026, 3, 8, 15, 30, tzinfo=UTC)
    third = client.post(
        "/api/v1/nutrition/targets/manual",
        json={**payload, "calories": 2500, "carbs_g": 315},
        headers=headers,
    )
    assert [response.status_code for response in (first, completed, second, third)] == [200] * 4, [
        response.text for response in (first, completed, second, third)
    ]
    for day, expected in [("2026-03-07", 2000), ("2026-03-08", 2300), ("2026-03-09", 2500)]:
        result = client.get("/api/v1/nutrition/diary", params={"diary_date": day}, headers=headers)
        assert result.status_code == 200
        assert Decimal(result.json()["targets"]["energy_kcal"]) == expected


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_completion_and_target_change_are_serialized(client) -> None:
    login = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": 952007, "is_coach": False}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    today = today_msk().isoformat()
    payload = {"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 180}
    assert (
        client.post("/api/v1/nutrition/targets/manual", json=payload, headers=headers).status_code
        == 200
    )
    barrier = Barrier(2)

    def complete():
        barrier.wait(timeout=5)
        return client.put(
            "/api/v1/nutrition/diary/status",
            json={"diary_date": today, "status": "fasted"},
            headers=headers,
        )

    def change():
        barrier.wait(timeout=5)
        return client.post(
            "/api/v1/nutrition/targets/manual",
            json={**payload, "calories": 2300, "carbs_g": 270},
            headers=headers,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        completion, changed = executor.submit(complete), executor.submit(change)
        completion, changed = completion.result(), changed.result()
    assert completion.status_code == changed.status_code == 200
    day = client.get("/api/v1/nutrition/diary", params={"diary_date": today}, headers=headers)
    assert day.status_code == 200
    assert day.json()["targets"] == completion.json()["targets"]
    assert Decimal(day.json()["targets"]["energy_kcal"]) in {2000, 2300}
    with get_session_context() as db:
        user_id = db.query(User.id).filter_by(telegram_user_id=952007).scalar()
        assert db.query(NutritionTargetDaySnapshot).filter_by(user_id=user_id).count() == 1
