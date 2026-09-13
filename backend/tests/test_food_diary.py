from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, Column, Integer, MetaData, Table, create_engine, inspect
from sqlalchemy.orm import joinedload

from fitminiapp_api import main as main_module
from fitminiapp_api.core import timezone as timezone_module
from fitminiapp_api.db.performance import (
    begin_sql_metrics,
    current_sql_metrics,
    reset_sql_metrics,
)
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.schemas.food_diary import FoodDiaryEntryCreate
from fitminiapp_api.services.food_diary import create_food_diary_entry, get_food_diary_day


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "is_coach": False,
            "is_admin": False,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _active_food(**overrides: object) -> Food:
    values: dict[str, object] = {
        "name": "Овсяная каша",
        "brand": "YFC Test",
        "energy_kcal_per_100g": Decimal("200"),
        "protein_g_per_100g": Decimal("10"),
        "fat_g_per_100g": Decimal("5"),
        "carbs_g_per_100g": Decimal("30"),
        "fiber_g_per_100g": Decimal("4"),
        "standard_serving_amount": Decimal("1"),
        "standard_serving_unit": "serving",
        "standard_serving_weight_g": Decimal("50"),
        "food_type": "system",
        "owner_user_id": None,
        "provenance": "internal",
        "source_name": "yfc-test",
        "trust_level": "verified",
        "status": "active",
    }
    values.update(overrides)
    return Food(**values)


def _store_food(**overrides: object) -> int:
    with get_session_context() as db:
        food = _active_food(**overrides)
        db.add(food)
        db.flush()
        return food.id


def _set_timezone(telegram_user_id: int, timezone_name: str) -> None:
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == telegram_user_id).one()
        if user.profile is None:
            db.add(UserProfile(user_id=user.id, timezone=timezone_name))
        else:
            user.profile.timezone = timezone_name


def _add_target(telegram_user_id: int) -> None:
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == telegram_user_id).one()
        db.add(
            NutritionTarget(
                user_id=user.id,
                sex="male",
                weight_kg=80,
                height_cm=180,
                age=30,
                daily_activity_level="moderate",
                daily_routine="mixed",
                steps_range="from_7000_to_10000",
                strength_trainings_per_week=3,
                strength_training_duration_minutes=60,
                strength_training_type="regular",
                strength_rest="one_to_two",
                cardio_trainings_per_week=1,
                cardio_training_duration_minutes=30,
                cardio_intensity="moderate",
                cardio_trainings=[],
                goal="maintenance",
                bmr=1800,
                tdee=2400,
                calories=2000,
                protein_g=150,
                fat_g=70,
                carbs_g=190,
            )
        )


def test_diary_api_crud_aggregates_and_uses_existing_target_service(client, monkeypatch) -> None:
    telegram_user_id = 16_001
    headers = _auth(client, telegram_user_id)
    food_id = _store_food()
    _add_target(telegram_user_id)
    selected_date = timezone_module.today_in_timezone("Europe/Moscow")

    first = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": food_id,
            "diary_date": selected_date.isoformat(),
            "meal_type": "breakfast",
            "amount": "150",
            "amount_unit": "g",
        },
    )
    assert first.status_code == 201
    assert first.json()["weight_g"] == "150.000"
    assert first.json()["nutrition"] == {
        "energy_kcal": "300.00",
        "protein_g": "15.000",
        "fat_g": "7.500",
        "carbs_g": "45.000",
        "fiber_g": "6.000",
    }

    second = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": food_id,
            "diary_date": selected_date.isoformat(),
            "meal_type": "lunch",
            "amount": "2",
            "amount_unit": "serving",
        },
    )
    assert second.status_code == 201
    assert second.json()["weight_g"] == "100.000"

    from fitminiapp_api.services import food_diary as diary_service

    target_calls = 0
    real_target_service = diary_service.get_nutrition_target_for_user

    def tracked_target_service(db, user):
        nonlocal target_calls
        target_calls += 1
        return real_target_service(db, user)

    monkeypatch.setattr(diary_service, "get_nutrition_target_for_user", tracked_target_service)
    day = client.get(
        "/api/v1/nutrition/diary",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    )
    assert day.status_code == 200
    payload = day.json()
    assert target_calls == 1
    assert [meal["meal_type"] for meal in payload["meals"]] == [
        "breakfast",
        "lunch",
        "dinner",
        "snacks",
    ]
    assert payload["totals"]["energy_kcal"] == "500.00"
    assert payload["meals"][0]["totals"]["protein_g"] == "15.000"
    assert payload["meals"][1]["totals"]["protein_g"] == "10.000"
    assert payload["targets"] == {
        "energy_kcal": "2000",
        "protein_g": "150",
        "fat_g": "70",
        "carbs_g": "190",
    }
    assert payload["remaining"]["energy_kcal"] == "1500.00"

    with get_session_context() as db:
        food = db.query(Food).filter(Food.id == food_id).one()
        food.name = "Новое название каталога"
        food.energy_kcal_per_100g = Decimal("900")

    updated = client.patch(
        f"/api/v1/nutrition/diary/entries/{first.json()['id']}",
        headers=headers,
        json={"meal_type": "dinner", "amount": "1", "amount_unit": "serving"},
    )
    assert updated.status_code == 200
    assert updated.json()["food_name"] == "Овсяная каша"
    assert updated.json()["weight_g"] == "50.000"
    assert updated.json()["nutrition"]["energy_kcal"] == "100.00"

    deleted = client.delete(
        f"/api/v1/nutrition/diary/entries/{second.json()['id']}", headers=headers
    )
    assert deleted.status_code == 204
    final_day = client.get(
        "/api/v1/nutrition/diary",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    ).json()
    assert final_day["totals"]["energy_kcal"] == "100.00"
    assert [len(meal["entries"]) for meal in final_day["meals"]] == [0, 0, 1, 0]


def test_diary_is_private_and_foreign_resources_are_not_disclosed(client) -> None:
    owner_headers = _auth(client, 16_010)
    other_headers = _auth(client, 16_011)
    selected_date = timezone_module.today_in_timezone("Europe/Moscow")
    with get_session_context() as db:
        owner = db.query(User).filter(User.telegram_user_id == 16_010).one()
        food = _active_food(
            name="Личный продукт",
            food_type="user",
            owner_user_id=owner.id,
            provenance="user",
            source_name=None,
            trust_level="unverified",
        )
        db.add(food)
        db.flush()
        food_id = food.id

    created = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=owner_headers,
        json={
            "food_id": food_id,
            "diary_date": selected_date.isoformat(),
            "meal_type": "snacks",
            "amount": "25",
        },
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]

    foreign_food = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=other_headers,
        json={
            "food_id": food_id,
            "diary_date": selected_date.isoformat(),
            "meal_type": "snacks",
            "amount": "25",
        },
    )
    assert foreign_food.status_code == 404
    assert (
        client.patch(
            f"/api/v1/nutrition/diary/entries/{entry_id}",
            headers=other_headers,
            json={"amount": "30"},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/nutrition/diary/entries/{entry_id}", headers=other_headers
        ).status_code
        == 404
    )
    other_day = client.get(
        "/api/v1/nutrition/diary",
        headers=other_headers,
        params={"diary_date": selected_date.isoformat()},
    ).json()
    assert other_day["totals"]["energy_kcal"] == "0"
    assert all(not meal["entries"] for meal in other_day["meals"])


def test_user_timezone_controls_today_and_future_date_rule(client, monkeypatch) -> None:
    fixed_utc = datetime(2026, 8, 18, 21, 30, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_utc.replace(tzinfo=None)
            return fixed_utc.astimezone(tz)

    monkeypatch.setattr(timezone_module, "datetime", FixedDateTime)
    tokyo_headers = _auth(client, 16_020)
    los_angeles_headers = _auth(client, 16_021)
    _set_timezone(16_020, "Asia/Tokyo")
    _set_timezone(16_021, "America/Los_Angeles")
    food_id = _store_food()

    assert (
        client.get("/api/v1/nutrition/diary", headers=tokyo_headers).json()["diary_date"]
        == "2026-08-19"
    )
    assert (
        client.get("/api/v1/nutrition/diary", headers=los_angeles_headers).json()["diary_date"]
        == "2026-08-18"
    )

    tokyo_today = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=tokyo_headers,
        json={
            "food_id": food_id,
            "diary_date": "2026-08-19",
            "meal_type": "breakfast",
            "amount": "100",
        },
    )
    assert tokyo_today.status_code == 201
    los_angeles_future = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=los_angeles_headers,
        json={
            "food_id": food_id,
            "diary_date": "2026-08-19",
            "meal_type": "breakfast",
            "amount": "100",
        },
    )
    assert los_angeles_future.status_code == 422
    assert los_angeles_future.json()["detail"] == "future diary dates are not allowed"
    assert (
        client.post(
            "/api/v1/nutrition/diary/entries",
            headers=los_angeles_headers,
            json={
                "food_id": food_id,
                "diary_date": "2026-08-17",
                "meal_type": "breakfast",
                "amount": "100",
            },
        ).status_code
        == 201
    )
    assert (
        client.get(
            "/api/v1/nutrition/diary",
            headers=los_angeles_headers,
            params={"diary_date": "2026-08-19"},
        ).status_code
        == 422
    )


def test_empty_day_invalid_values_and_missing_serving_contract(client) -> None:
    headers = _auth(client, 16_030)
    selected_date = timezone_module.today_in_timezone("Europe/Moscow")
    no_serving_food_id = _store_food(
        fiber_g_per_100g=None,
        standard_serving_amount=None,
        standard_serving_unit=None,
        standard_serving_weight_g=None,
    )

    empty = client.get(
        "/api/v1/nutrition/diary",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    )
    assert empty.status_code == 200
    assert empty.json()["totals"] == {
        "energy_kcal": "0",
        "protein_g": "0",
        "fat_g": "0",
        "carbs_g": "0",
        "fiber_g": "0",
    }
    assert empty.json()["targets"] is None
    assert empty.json()["remaining"] is None

    base_payload = {
        "food_id": no_serving_food_id,
        "diary_date": selected_date.isoformat(),
        "meal_type": "breakfast",
        "amount": "10",
    }
    assert (
        client.post(
            "/api/v1/nutrition/diary/entries",
            headers=headers,
            json={**base_payload, "amount": "0"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/nutrition/diary/entries",
            headers=headers,
            json={**base_payload, "meal_type": "brunch"},
        ).status_code
        == 422
    )
    missing_serving = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={**base_payload, "amount_unit": "serving"},
    )
    assert missing_serving.status_code == 422
    assert missing_serving.json()["detail"] == "food has no standard serving weight"
    created = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json=base_payload,
    )
    assert created.status_code == 201
    assert (
        client.patch(
            f"/api/v1/nutrition/diary/entries/{created.json()['id']}",
            headers=headers,
            json={"amount": None},
        ).status_code
        == 422
    )
    populated = client.get(
        "/api/v1/nutrition/diary",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    ).json()
    assert populated["totals"]["fiber_g"] is None
    assert client.get("/api/v1/nutrition/diary").status_code == 401


def test_quick_add_is_idempotent_and_day_completeness_is_explicit(client) -> None:
    headers = _auth(client, 16_040)
    selected_date = timezone_module.today_in_timezone("Europe/Moscow")
    request_headers = {**headers, "Idempotency-Key": "quick-entry-0001"}
    payload = {
        "quick_add": {"name": "  Обед   вне дома ", "energy_kcal": "640"},
        "diary_date": selected_date.isoformat(),
        "meal_type": "lunch",
        "logged_at": "13:25",
        "amount": "1",
        "amount_unit": "serving",
    }

    created = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=request_headers,
        json=payload,
    )
    assert created.status_code == 201, created.text
    assert created.json()["entry_kind"] == "quick_add"
    assert created.json()["food_id"] is None
    assert created.json()["recipe_id"] is None
    assert created.json()["food_name"] == "Обед вне дома"
    assert created.json()["logged_at"] == "13:25:00"
    assert created.json()["nutrition"] == {
        "energy_kcal": "640.00",
        "protein_g": None,
        "fat_g": None,
        "carbs_g": None,
        "fiber_g": None,
    }

    replay = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=request_headers,
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == created.json()["id"]
    conflict = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=request_headers,
        json={**payload, "quick_add": {"energy_kcal": "700"}},
    )
    assert conflict.status_code == 409

    day = client.get(
        "/api/v1/nutrition/diary",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    ).json()
    assert day["status"] == "incomplete"
    assert day["status_is_explicit"] is False
    assert day["totals"]["energy_kcal"] == "640.00"
    assert day["totals"]["protein_g"] is None

    complete = client.put(
        "/api/v1/nutrition/diary/status",
        headers=headers,
        json={"diary_date": selected_date.isoformat(), "status": "complete"},
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == "complete"
    assert complete.json()["status_is_explicit"] is True

    empty_date = selected_date - timedelta(days=1)
    fasted = client.put(
        "/api/v1/nutrition/diary/status",
        headers=headers,
        json={"diary_date": empty_date.isoformat(), "status": "fasted"},
    )
    assert fasted.status_code == 200
    assert fasted.json()["status"] == "fasted"
    blocked = client.post(
        "/api/v1/nutrition/diary/entries",
        headers={**headers, "Idempotency-Key": "quick-entry-0002"},
        json={**payload, "diary_date": empty_date.isoformat()},
    )
    assert blocked.status_code == 409
    reset = client.put(
        "/api/v1/nutrition/diary/status",
        headers=headers,
        json={"diary_date": empty_date.isoformat(), "status": "unlogged"},
    )
    assert reset.status_code == 200
    assert reset.json()["status"] == "unlogged"
    assert reset.json()["status_is_explicit"] is False


def test_quick_add_full_macros_remain_available_to_day_totals(client) -> None:
    headers = _auth(client, 16_041)
    selected_date = timezone_module.today_in_timezone("Europe/Moscow") - timedelta(days=2)
    response = client.post(
        "/api/v1/nutrition/diary/entries",
        headers={**headers, "Idempotency-Key": "quick-entry-full-1"},
        json={
            "quick_add": {
                "energy_kcal": "520",
                "protein_g": "35",
                "fat_g": "18",
                "carbs_g": "52",
            },
            "diary_date": selected_date.isoformat(),
            "meal_type": "dinner",
            "amount": "1",
            "amount_unit": "serving",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["nutrition"] == {
        "energy_kcal": "520.00",
        "protein_g": "35.000",
        "fat_g": "18.000",
        "carbs_g": "52.000",
        "fiber_g": None,
    }
    copied = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**headers, "Idempotency-Key": "copy-quick-entry-full-1"},
        json={
            "source_entry_id": response.json()["id"],
            "source_date": selected_date.isoformat(),
            "source_meal_type": "dinner",
            "target_date": (selected_date + timedelta(days=1)).isoformat(),
            "target_meal_type": "lunch",
        },
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()["entries"][0]["entry_kind"] == "quick_add"
    assert copied.json()["entries"][0]["nutrition"] == response.json()["nutrition"]


def test_diary_day_query_count_is_constant() -> None:
    selected_date = timezone_module.today_in_timezone("Europe/Moscow")
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 2001).one()
        food = _active_food()
        db.add(food)
        db.flush()
        for index in range(25):
            create_food_diary_entry(
                db,
                user,
                FoodDiaryEntryCreate(
                    food_id=food.id,
                    diary_date=selected_date,
                    meal_type="snacks",
                    amount=Decimal(index + 1),
                ),
            )

    with get_session_context() as db:
        user = (
            db.query(User)
            .options(joinedload(User.profile))
            .filter(User.telegram_user_id == 2001)
            .one()
        )
        token = begin_sql_metrics()
        try:
            result = get_food_diary_day(db, user, selected_date)
            metrics = current_sql_metrics()
        finally:
            reset_sql_metrics(token)

    assert len(result.meals[-1].entries) == 25
    assert metrics.query_count == 3


def test_food_diary_migration_upgrades_from_food_domain_head(tmp_path: Path) -> None:
    migration_path = (
        Path(main_module.__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0035_food_diary.py"
    )
    spec = importlib.util.spec_from_file_location("food_diary_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "0034_food_domain_foundation"

    engine = create_engine(f"sqlite:///{(tmp_path / 'food-diary-migration.db').as_posix()}")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table("foods", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        schema = inspect(connection)
        assert "food_diary_entries" in schema.get_table_names()
        later_columns = {
            "recipe_id",
            "copy_operation_id",
            "copied_from_entry_id",
            "logged_at",
            "entry_kind",
            "quick_energy_kcal",
            "quick_protein_g",
            "quick_fat_g",
            "quick_carbs_g",
            "idempotency_key",
            "request_fingerprint",
            "nutrition_basis_kind",
            "nutrition_basis_amount",
            "nutrition_basis_unit",
            "nutrition_snapshot",
            "nutrition_amount",
            "nutrition_weight_g",
            "nutrition_energy_kcal_per_100g",
            "nutrition_protein_g_per_100g",
            "nutrition_fat_g_per_100g",
            "nutrition_carbs_g_per_100g",
        }
        assert {column["name"] for column in schema.get_columns("food_diary_entries")} == {
            column.name
            for column in FoodDiaryEntry.__table__.columns
            if column.name not in later_columns
        }
        assert {
            constraint["name"] for constraint in schema.get_check_constraints("food_diary_entries")
        } == {
            constraint.name
            for constraint in FoodDiaryEntry.__table__.constraints
            if isinstance(constraint, CheckConstraint)
            and constraint.name
            not in {
                "ck_food_diary_entries_single_source",
                "ck_food_diary_entries_kind",
                "ck_food_diary_entries_quick_source",
                "ck_food_diary_entries_quick_nutrition",
                "ck_food_diary_entries_quick_macros_complete",
                "ck_food_diary_entries_quick_energy_range",
                "ck_food_diary_entries_quick_protein_range",
                "ck_food_diary_entries_quick_fat_range",
                "ck_food_diary_entries_quick_carbs_range",
                "ck_food_diary_entries_idempotency_pair",
            }
        }
        assert {index["name"] for index in schema.get_indexes("food_diary_entries")} == {
            "ix_food_diary_entries_user_date_meal"
        }
        migration.downgrade()
        assert "food_diary_entries" not in inspect(connection).get_table_names()

    engine.dispose()
