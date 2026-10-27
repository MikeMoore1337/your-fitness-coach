from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from fitminiapp_api import main as main_module
from fitminiapp_api.core import timezone as timezone_module
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.user import User


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


def _food(**overrides: object) -> Food:
    values: dict[str, object] = {
        "name": "Тестовый продукт",
        "energy_kcal_per_100g": Decimal("100"),
        "protein_g_per_100g": Decimal("10"),
        "fat_g_per_100g": Decimal("4"),
        "carbs_g_per_100g": Decimal("12"),
        "fiber_g_per_100g": Decimal("2"),
        "standard_serving_amount": None,
        "standard_serving_unit": None,
        "standard_serving_weight_g": None,
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
        food = _food(**overrides)
        db.add(food)
        db.flush()
        return food.id


def _create_entry(
    client,
    headers: dict[str, str],
    food_id: int,
    diary_date: date,
    meal_type: str,
    amount: str = "100",
) -> dict:
    response = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": food_id,
            "diary_date": diary_date.isoformat(),
            "meal_type": meal_type,
            "amount": amount,
            "amount_unit": "g",
        },
    )
    assert response.status_code == 201
    return response.json()


def _preview_copy(client, headers: dict[str, str], scope: str, payload: dict) -> dict:
    response = client.post(
        f"/api/v1/nutrition/diary/copy/{scope}/preview",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 200, response.text
    return {**payload, "preview_token": response.json()["preview_token"]}


def test_recipe_math_final_weight_and_diary_serving_are_deterministic(client) -> None:
    headers = _auth(client, 18_001)
    first_food_id = _store_food(name="Яйцо")
    second_food_id = _store_food(
        name="Сыр",
        energy_kcal_per_100g=Decimal("200"),
        standard_serving_amount=Decimal("1"),
        standard_serving_unit="serving",
        standard_serving_weight_g=Decimal("50"),
    )

    created = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "  Омлет  ",
            "ingredients": [
                {"food_id": first_food_id, "amount": "100", "amount_unit": "g"},
                {"food_id": second_food_id, "amount": "1", "amount_unit": "serving"},
            ],
        },
    )
    assert created.status_code == 201
    recipe = created.json()
    assert recipe["name"] == "Омлет"
    assert recipe["ingredients_weight_g"] == "150.000"
    assert recipe["final_weight_g"] is None
    assert recipe["effective_weight_g"] == "150.000"
    assert recipe["totals"]["energy_kcal"] == "200.00"
    assert recipe["nutrients_per_100g"]["energy_kcal_per_100g"] == "133.33"

    cooked = client.patch(
        f"/api/v1/nutrition/recipes/{recipe['id']}",
        headers=headers,
        json={"final_weight_g": "100"},
    )
    assert cooked.status_code == 200
    assert cooked.json()["ingredients_weight_g"] == "150.000"
    assert cooked.json()["effective_weight_g"] == "100.000"
    assert cooked.json()["nutrients_per_100g"]["energy_kcal_per_100g"] == "200.00"

    selected_date = timezone_module.today_in_timezone("Europe/Moscow")
    diary_entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "recipe_id": recipe["id"],
            "diary_date": selected_date.isoformat(),
            "meal_type": "breakfast",
            "amount": "25",
            "amount_unit": "g",
        },
    )
    assert diary_entry.status_code == 201
    assert diary_entry.json()["food_id"] is None
    assert diary_entry.json()["recipe_id"] == recipe["id"]
    assert diary_entry.json()["nutrition"]["energy_kcal"] == "50.00"
    assert diary_entry.json()["nutrition"]["protein_g"] == "3.750"
    assert (
        client.post(
            "/api/v1/nutrition/diary/entries",
            headers=headers,
            json={
                "recipe_id": recipe["id"],
                "diary_date": selected_date.isoformat(),
                "meal_type": "breakfast",
                "amount": "1",
                "amount_unit": "serving",
            },
        ).status_code
        == 422
    )


def test_recipes_and_their_ingredient_foods_are_private(client) -> None:
    owner_headers = _auth(client, 18_010)
    other_headers = _auth(client, 18_011)
    with get_session_context() as db:
        owner = db.query(User).filter(User.telegram_user_id == 18_010).one()
        private_food = _food(
            name="Секретный продукт",
            food_type="user",
            owner_user_id=owner.id,
            provenance="user",
            source_name=None,
            trust_level="unverified",
        )
        db.add(private_food)
        db.flush()
        private_food_id = private_food.id

    foreign_ingredient = client.post(
        "/api/v1/nutrition/recipes",
        headers=other_headers,
        json={
            "name": "Чужой состав",
            "ingredients": [{"food_id": private_food_id, "amount": "100"}],
        },
    )
    assert foreign_ingredient.status_code == 404

    recipe = client.post(
        "/api/v1/nutrition/recipes",
        headers=owner_headers,
        json={
            "name": "Личный рецепт",
            "ingredients": [{"food_id": private_food_id, "amount": "100"}],
        },
    ).json()
    recipe_id = recipe["id"]
    assert client.get("/api/v1/nutrition/recipes", headers=other_headers).json()["items"] == []
    assert (
        client.get(f"/api/v1/nutrition/recipes/{recipe_id}", headers=other_headers).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/nutrition/recipes/{recipe_id}",
            headers=other_headers,
            json={"name": "Украдено"},
        ).status_code
        == 404
    )
    selected_date = timezone_module.today_in_timezone("Europe/Moscow")
    assert (
        client.post(
            "/api/v1/nutrition/diary/entries",
            headers=other_headers,
            json={
                "recipe_id": recipe_id,
                "diary_date": selected_date.isoformat(),
                "meal_type": "dinner",
                "amount": "100",
            },
        ).status_code
        == 404
    )


def test_copy_product_meal_day_and_idempotent_replay(client) -> None:
    headers = _auth(client, 18_020)
    other_headers = _auth(client, 18_021)
    food_id = _store_food()
    today = timezone_module.today_in_timezone("Europe/Moscow")
    source_date = today - timedelta(days=2)
    middle_date = today - timedelta(days=1)
    breakfast = _create_entry(client, headers, food_id, source_date, "breakfast", "80")
    _create_entry(client, headers, food_id, source_date, "lunch", "120")

    product_request = {
        "source_entry_id": breakfast["id"],
        "source_date": source_date.isoformat(),
        "source_meal_type": "breakfast",
        "target_date": middle_date.isoformat(),
        "target_meal_type": "dinner",
    }
    product_payload = _preview_copy(client, headers, "product", product_request)
    first = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**headers, "Idempotency-Key": "repeat-product-1"},
        json=product_payload,
    )
    assert first.status_code == 201
    assert first.json()["replayed"] is False
    assert first.json()["entries"][0]["meal_type"] == "dinner"
    repeated = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**headers, "Idempotency-Key": "repeat-product-1"},
        json=product_payload,
    )
    assert repeated.status_code == 201
    assert repeated.json()["replayed"] is True
    assert repeated.json()["entries"][0]["id"] == first.json()["entries"][0]["id"]

    conflicting = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**headers, "Idempotency-Key": "repeat-product-1"},
        json={**product_payload, "target_meal_type": "snacks"},
    )
    assert conflicting.status_code == 409
    middle_day = client.get(
        "/api/v1/nutrition/diary",
        headers=headers,
        params={"diary_date": middle_date.isoformat()},
    ).json()
    assert sum(len(meal["entries"]) for meal in middle_day["meals"]) == 1

    meal_request = {
        "source_date": source_date.isoformat(),
        "source_meal_type": "breakfast",
        "target_date": middle_date.isoformat(),
        "target_meal_type": "breakfast",
    }
    meal = client.post(
        "/api/v1/nutrition/diary/copy/meal",
        headers={**headers, "Idempotency-Key": "copy-meal-0001"},
        json=_preview_copy(client, headers, "meal", meal_request),
    )
    assert meal.status_code == 201
    assert len(meal.json()["entries"]) == 1

    yesterday_request = {
        "source_date": middle_date.isoformat(),
        "source_meal_type": "breakfast",
        "target_date": today.isoformat(),
        "target_meal_type": "breakfast",
    }
    repeated_yesterday = client.post(
        "/api/v1/nutrition/diary/copy/meal",
        headers={**headers, "Idempotency-Key": "yesterday-breakfast"},
        json=_preview_copy(client, headers, "meal", yesterday_request),
    )
    assert repeated_yesterday.status_code == 201
    assert len(repeated_yesterday.json()["entries"]) == 1

    day_request = {"source_date": source_date.isoformat(), "target_date": today.isoformat()}
    copied_day = client.post(
        "/api/v1/nutrition/diary/copy/day",
        headers={**headers, "Idempotency-Key": "copy-day-000001"},
        json=_preview_copy(client, headers, "day", day_request),
    )
    assert copied_day.status_code == 201
    assert [entry["meal_type"] for entry in copied_day.json()["entries"]] == [
        "breakfast",
        "lunch",
    ]
    foreign_repeat = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**other_headers, "Idempotency-Key": "foreign-product"},
        json=product_payload,
    )
    assert foreign_repeat.status_code == 409


def test_repeat_preview_is_read_only_and_stale_confirmation_fails_safe(client) -> None:
    headers = _auth(client, 18_022)
    food_id = _store_food(name="Предварительный продукт")
    today = timezone_module.today_in_timezone("Europe/Moscow")
    source_date = today - timedelta(days=2)
    target_date = today - timedelta(days=1)
    source = _create_entry(client, headers, food_id, source_date, "breakfast", "80")
    request = {
        "source_entry_id": source["id"],
        "source_date": source_date.isoformat(),
        "source_meal_type": "breakfast",
        "target_date": target_date.isoformat(),
        "target_meal_type": "lunch",
    }

    preview = client.post(
        "/api/v1/nutrition/diary/copy/product/preview",
        headers=headers,
        json=request,
    )
    assert preview.status_code == 200, preview.text
    preview_json = preview.json()
    assert preview_json["entries"][0]["food_name"] == "Предварительный продукт"
    assert preview_json["entries"][0]["amount"] == "80.000"
    preview_day = client.get(
        "/api/v1/nutrition/diary",
        headers=headers,
        params={"diary_date": target_date.isoformat()},
    )
    assert preview_day.status_code == 200
    assert all(not meal["entries"] for meal in preview_day.json()["meals"])

    updated = client.patch(
        f"/api/v1/nutrition/diary/entries/{source['id']}",
        headers=headers,
        json={"amount": "90"},
    )
    assert updated.status_code == 200, updated.text
    stale = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**headers, "Idempotency-Key": "stale-preview-0001"},
        json={**request, "preview_token": preview_json["preview_token"]},
    )
    assert stale.status_code == 409
    assert "stale" in stale.json()["detail"]

    fresh_request = {**request}
    fresh_preview = client.post(
        "/api/v1/nutrition/diary/copy/product/preview",
        headers=headers,
        json=fresh_request,
    )
    assert fresh_preview.status_code == 200, fresh_preview.text
    confirmed = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**headers, "Idempotency-Key": "repeat-double-click-0001"},
        json={**fresh_request, "preview_token": fresh_preview.json()["preview_token"]},
    )
    assert confirmed.status_code == 201, confirmed.text
    assert confirmed.json()["entries"][0]["amount"] == "90.000"
    assert confirmed.json()["entries"][0]["diary_date"] == target_date.isoformat()
    replay = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**headers, "Idempotency-Key": "repeat-double-click-0001"},
        json={**fresh_request, "preview_token": fresh_preview.json()["preview_token"]},
    )
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True
    alternate_confirmation = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**headers, "Idempotency-Key": "repeat-double-click-0002"},
        json={**fresh_request, "preview_token": fresh_preview.json()["preview_token"]},
    )
    assert alternate_confirmation.status_code == 409
    target = client.get(
        "/api/v1/nutrition/diary",
        headers=headers,
        params={"diary_date": target_date.isoformat()},
    )
    assert target.status_code == 200
    assert sum(len(meal["entries"]) for meal in target.json()["meals"]) == 1


def test_copy_target_date_uses_the_authenticated_users_timezone(client, monkeypatch) -> None:
    fixed_utc = datetime(2026, 8, 18, 21, 30, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_utc.replace(tzinfo=None)
            return fixed_utc.astimezone(tz)

    monkeypatch.setattr(timezone_module, "datetime", FixedDateTime)
    tokyo_headers = _auth(client, 18_030)
    los_angeles_headers = _auth(client, 18_031)
    with get_session_context() as db:
        tokyo = db.query(User).filter(User.telegram_user_id == 18_030).one()
        los_angeles = db.query(User).filter(User.telegram_user_id == 18_031).one()
        tokyo.profile.timezone = "Asia/Tokyo"
        los_angeles.profile.timezone = "America/Los_Angeles"
    food_id = _store_food()
    tokyo_source = _create_entry(client, tokyo_headers, food_id, date(2026, 8, 18), "breakfast")
    la_source = _create_entry(client, los_angeles_headers, food_id, date(2026, 8, 17), "breakfast")

    def payload(entry_id: int, source_date: str) -> dict[str, object]:
        return {
            "source_entry_id": entry_id,
            "source_date": source_date,
            "source_meal_type": "breakfast",
            "target_date": "2026-08-19",
            "target_meal_type": "breakfast",
        }

    tokyo_request = payload(tokyo_source["id"], "2026-08-18")
    tokyo_copy = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**tokyo_headers, "Idempotency-Key": "tokyo-target-001"},
        json=_preview_copy(client, tokyo_headers, "product", tokyo_request),
    )
    assert tokyo_copy.status_code == 201
    la_preview = client.post(
        "/api/v1/nutrition/diary/copy/product/preview",
        headers=los_angeles_headers,
        json=payload(la_source["id"], "2026-08-17"),
    )
    assert la_preview.status_code == 422
    assert la_preview.json()["detail"] == "future diary dates are not allowed"


def test_recipes_copying_migration_upgrades_and_downgrades(tmp_path: Path) -> None:
    migrations_dir = Path(main_module.__file__).resolve().parents[1] / "alembic" / "versions"

    def load_migration(filename: str, module_name: str):
        spec = importlib.util.spec_from_file_location(module_name, migrations_dir / filename)
        assert spec is not None and spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        return migration

    diary_migration = load_migration("0035_food_diary.py", "food_diary_before_recipes")
    migration = load_migration("0037_recipes_copying.py", "recipes_copying_migration")
    assert migration.down_revision == "0036_food_library_search"

    engine = create_engine(f"sqlite:///{(tmp_path / 'recipes-copying.db').as_posix()}")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table("foods", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        diary_migration.op = operations
        diary_migration.upgrade()
        migration.op = operations
        migration.upgrade()
        schema = inspect(connection)
        assert {"recipes", "recipe_ingredients", "food_diary_copy_operations"} <= set(
            schema.get_table_names()
        )
        diary_columns = {column["name"] for column in schema.get_columns("food_diary_entries")}
        assert {"recipe_id", "copy_operation_id", "copied_from_entry_id"} <= diary_columns
        migration.downgrade()
        schema = inspect(connection)
        assert "recipes" not in schema.get_table_names()
        assert "recipe_id" not in {
            column["name"] for column in schema.get_columns("food_diary_entries")
        }

    engine.dispose()
