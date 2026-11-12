from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from fitminiapp_api.core.timezone import today_for_user, today_msk
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services import nutrition as nutrition_service
from fitminiapp_api.services.nutrition import get_nutrition_target_for_date


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


def _manual_payload(**overrides) -> dict:
    payload = {
        "calories": 2200,
        "protein_g": 150,
        "fat_g": 70,
        "carbs_g": 242,
        "note": "Стартовый ручной ориентир",
    }
    payload.update(overrides)
    return payload


def _calculated_payload(**overrides) -> dict:
    payload = {
        "sex": "female",
        "weight_kg": 68,
        "height_cm": 170,
        "age": 31,
        "daily_routine": "mixed",
        "steps_range": "from_7000_to_10000",
        "strength_trainings_per_week": 3,
        "strength_training_duration_minutes": 60,
        "strength_training_type": "regular",
        "strength_rest": "one_to_two",
        "cardio_trainings": [],
        "goal": "maintenance",
    }
    payload.update(overrides)
    return payload


def test_manual_target_requires_energy_confirmation_and_preserves_exact_values(client) -> None:
    headers = _auth(client, 55_001)

    mismatch = client.post(
        "/api/v1/nutrition/targets/manual",
        json=_manual_payload(calories=1200, protein_g=200, fat_g=100, carbs_g=200),
        headers=headers,
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"] == {
        "code": "nutrition_energy_mismatch",
        "message": (
            "Калорийность заметно отличается от энергии по БЖУ. "
            "Подтвердите сохранение или исправьте значения."
        ),
        "implied_energy_kcal": 2500,
        "difference_kcal": 1300,
    }

    saved = client.post(
        "/api/v1/nutrition/targets/manual",
        json=_manual_payload(
            calories=1200,
            protein_g=200,
            fat_g=100,
            carbs_g=200,
            confirm_energy_mismatch=True,
        ),
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert {
        key: saved.json()[key] for key in ("source", "calories", "protein_g", "fat_g", "carbs_g")
    } == {
        "source": "manual",
        "calories": 1200,
        "protein_g": 200,
        "fat_g": 100,
        "carbs_g": 200,
    }


def test_same_day_retry_is_idempotent_and_change_versions_without_overlap(client) -> None:
    headers = _auth(client, 55_002)
    effective_from = today_msk().isoformat()
    payload = _manual_payload(effective_from=effective_from)

    first = client.post("/api/v1/nutrition/targets/manual", json=payload, headers=headers)
    retry = client.post("/api/v1/nutrition/targets/manual", json=payload, headers=headers)
    changed = client.post(
        "/api/v1/nutrition/targets/manual",
        json=_manual_payload(
            effective_from=effective_from,
            calories=2300,
            protein_g=155,
            fat_g=75,
            carbs_g=251,
            note="Уточнённый ориентир",
        ),
        headers=headers,
    )

    assert first.status_code == retry.status_code == changed.status_code == 200
    assert retry.json()["id"] == first.json()["id"]
    assert changed.json()["id"] != first.json()["id"]
    history = client.get("/api/v1/nutrition/targets/history", headers=headers).json()["items"]
    assert [row["id"] for row in history] == [changed.json()["id"], first.json()["id"]]
    assert history[1]["effective_to"] == effective_from
    assert history[1]["superseded_by_id"] == changed.json()["id"]
    assert history[0]["effective_to"] is None

    user_id = _user_id(55_002)
    with get_session_context() as db:
        rows = db.query(NutritionTarget).filter(NutritionTarget.user_id == user_id).all()
        assert sum(row.effective_to is None for row in rows) == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_same_day_retry_creates_one_active_version(client) -> None:
    headers = _auth(client, 55_009)
    payload = _manual_payload()
    barrier = Barrier(2)

    def save_target():
        barrier.wait(timeout=5)
        return client.post(
            "/api/v1/nutrition/targets/manual",
            json=payload,
            headers=headers,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: save_target(), range(2)))

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    history = client.get("/api/v1/nutrition/targets/history", headers=headers).json()["items"]
    assert len(history) == 1
    assert history[0]["effective_to"] is None


def test_effective_history_resolves_each_calendar_day_and_export_contains_all_versions(
    client,
    monkeypatch,
) -> None:
    headers = _auth(client, 55_003)
    user_id = _user_id(55_003)
    previous_start = today_msk() - timedelta(days=4)
    current_start = today_msk() - timedelta(days=1)
    monkeypatch.setattr(nutrition_service, "today_for_user", lambda _user: previous_start)
    previous = client.post(
        "/api/v1/nutrition/targets/manual",
        json=_manual_payload(effective_from=previous_start.isoformat()),
        headers=headers,
    )
    monkeypatch.setattr(nutrition_service, "today_for_user", lambda _user: current_start)
    current = client.post(
        "/api/v1/nutrition/targets",
        json=_calculated_payload(
            effective_from=current_start.isoformat(), note="Возврат к расчёту"
        ),
        headers=headers,
    )
    assert previous.status_code == current.status_code == 200

    with get_session_context() as db:
        assert (
            get_nutrition_target_for_date(db, user_id, previous_start).id == previous.json()["id"]
        )
        assert get_nutrition_target_for_date(db, user_id, current_start).id == current.json()["id"]
        assert (
            get_nutrition_target_for_date(db, user_id, previous_start - timedelta(days=1)) is None
        )

    exported = client.get("/api/v1/me/export", headers=headers).json()
    assert exported["nutrition"]["id"] == current.json()["id"]
    assert [row["id"] for row in exported["nutrition_target_history"]] == [
        previous.json()["id"],
        current.json()["id"],
    ]


def test_trainer_cannot_assign_without_consent_and_loses_history_after_revocation(client) -> None:
    coach_headers = _auth(client, 55_004, is_coach=True)
    client_headers = _auth(client, 55_005)
    coach_id = _user_id(55_004)
    client_id = _user_id(55_005)
    with get_session_context() as db:
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=client_id, status="active"))

    assigned = client.post(
        "/api/v1/nutrition/targets/manual",
        json=_manual_payload(target_telegram_user_id=55_005, note="Ориентир от тренера"),
        headers=coach_headers,
    )
    assert assigned.status_code == 409, assigned.text
    own_target = client.post(
        "/api/v1/nutrition/targets/manual", json=_manual_payload(), headers=client_headers
    )
    assert own_target.status_code == 200
    own_history = client.get("/api/v1/nutrition/targets/history", headers=client_headers)
    assert own_history.json()["items"][0]["source"] == "manual"
    coach_history = client.get(
        "/api/v1/nutrition/targets/history?target_telegram_user_id=55005",
        headers=coach_headers,
    )
    assert coach_history.status_code == 200
    assert coach_history.json()["items"][0]["id"] == own_target.json()["id"]

    with get_session_context() as db:
        relation = db.query(CoachClient).filter(CoachClient.coach_user_id == coach_id).one()
        relation.status = "ended"

    denied_write = client.post(
        "/api/v1/nutrition/targets/manual",
        json=_manual_payload(target_telegram_user_id=55_005, calories=2250),
        headers=coach_headers,
    )
    denied_history = client.get(
        "/api/v1/nutrition/targets/history?target_telegram_user_id=55005",
        headers=coach_headers,
    )
    assert denied_write.status_code == 403
    assert denied_history.status_code == 403


def test_default_effective_date_uses_target_account_timezone_and_future_is_rejected(client) -> None:
    headers = _auth(client, 55_006)
    user_id = _user_id(55_006)
    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None and user.profile is not None
        user.profile.timezone = "Pacific/Kiritimati"
        expected_date = today_for_user(user)

    saved = client.post(
        "/api/v1/nutrition/targets/manual",
        json=_manual_payload(),
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["effective_from"] == expected_date.isoformat()
    future = client.post(
        "/api/v1/nutrition/targets/manual",
        json=_manual_payload(effective_from=(expected_date + timedelta(days=1)).isoformat()),
        headers=headers,
    )
    assert future.status_code == 409


def test_manual_target_validation_rejects_negative_and_unrealistic_values(client) -> None:
    headers = _auth(client, 55_007)
    for changes in (
        {"calories": 799},
        {"protein_g": -1},
        {"fat_g": 251},
        {"carbs_g": 801},
    ):
        response = client.post(
            "/api/v1/nutrition/targets/manual",
            json=_manual_payload(**changes),
            headers=headers,
        )
        assert response.status_code == 422


def test_progress_compares_each_logged_day_with_its_effective_target(client, monkeypatch) -> None:
    headers = _auth(client, 55_008)
    user_id = _user_id(55_008)
    previous_start = today_msk() - timedelta(days=5)
    diary_date = today_msk() - timedelta(days=3)
    current_start = today_msk() - timedelta(days=1)
    monkeypatch.setattr(nutrition_service, "today_for_user", lambda _user: previous_start)
    previous = client.post(
        "/api/v1/nutrition/targets/manual",
        json=_manual_payload(
            effective_from=previous_start.isoformat(),
            calories=2000,
            protein_g=150,
            fat_g=60,
            carbs_g=215,
        ),
        headers=headers,
    )
    monkeypatch.setattr(nutrition_service, "today_for_user", lambda _user: current_start)
    current = client.post(
        "/api/v1/nutrition/targets/manual",
        json=_manual_payload(
            effective_from=current_start.isoformat(),
            calories=2400,
            protein_g=170,
            fat_g=75,
            carbs_g=261,
        ),
        headers=headers,
    )
    assert previous.status_code == current.status_code == 200
    with get_session_context() as db:
        db.add(
            FoodDiaryEntry(
                user_id=user_id,
                diary_date=diary_date,
                meal_type="dinner",
                amount=Decimal("200"),
                amount_unit="g",
                weight_g=Decimal("200"),
                food_name="Исторический рацион",
                energy_kcal_per_100g=Decimal("1000"),
                protein_g_per_100g=Decimal("75"),
                fat_g_per_100g=Decimal("0"),
                carbs_g_per_100g=Decimal("0"),
            )
        )
        db.add(FoodDiaryDayStatus(user_id=user_id, diary_date=diary_date, status="complete"))

    summary = client.get(
        "/api/v1/workouts/progress/summary?period_days=7",
        headers=headers,
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["nutrition"]["target_calories"] == 2400
    assert summary.json()["adherence"]["calories"]["evaluated"] == 1
    assert summary.json()["adherence"]["calories"]["achieved"] == 1
    assert summary.json()["adherence"]["calories"]["percent"] == 100.0


def test_migration_backfills_honest_effective_date_and_preserves_legacy_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from fitminiapp_api.core import config as app_config

    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite:///{(tmp_path / 'nutrition-history.db').as_posix()}"
    alembic_config = Config(str(root / "backend" / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(root / "backend" / "alembic"))
    monkeypatch.setattr(app_config.settings, "database_url", database_url)
    command.upgrade(alembic_config, "0054_training_preferences")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (telegram_user_id, is_coach, is_admin, is_active) "
                "VALUES (55100, 0, 0, 1)"
            )
        )
        user_id = connection.execute(
            text("SELECT id FROM users WHERE telegram_user_id = 55100")
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO nutrition_targets (
                    user_id, assigned_by_user_id, sex, weight_kg, height_cm, age,
                    daily_activity_level, daily_routine, steps_range,
                    strength_trainings_per_week, strength_training_duration_minutes,
                    strength_training_type, strength_rest, cardio_trainings_per_week,
                    cardio_training_duration_minutes, cardio_intensity, cardio_trainings,
                    goal, bmr, tdee, calories, protein_g, fat_g, carbs_g, saved_at
                ) VALUES (
                    :user_id, :user_id, 'female', 68, 170, 31,
                    'moderate', 'mixed', 'from_7000_to_10000',
                    3, 60, 'regular', 'one_to_two', 0,
                    30, 'moderate', '[]', 'maintenance', 1450, 2100,
                    2100, 140, 70, 230, :saved_at
                )
                """
            ),
            {"user_id": user_id, "saved_at": "2026-08-01 23:45:00"},
        )
    engine.dispose()

    command.upgrade(alembic_config, "head")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        migrated = (
            connection.execute(
                text("SELECT effective_from, effective_to, source, calories FROM nutrition_targets")
            )
            .mappings()
            .one()
        )
        indexes = {row["name"] for row in inspect(connection).get_indexes("nutrition_targets")}
    engine.dispose()
    assert str(migrated["effective_from"]) == "2026-08-01"
    assert migrated["effective_to"] is None
    assert migrated["source"] == "calculated"
    assert migrated["calories"] == 2100
    assert "uq_nutrition_targets_active_user" in indexes

    command.downgrade(alembic_config, "0054_training_preferences")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        restored = (
            connection.execute(text("SELECT calories, saved_at FROM nutrition_targets"))
            .mappings()
            .one()
        )
    engine.dispose()
    assert restored["calories"] == 2100
