from __future__ import annotations

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from fitminiapp_api import main as main_module
from fitminiapp_api.core import timezone as timezone_module
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.user import User
from fitminiapp_api.services.nutrition_power import parse_natural_food_input


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


def _store_food(name: str, *, owner_id: int | None = None) -> int:
    with get_session_context() as db:
        food = Food(
            name=name,
            energy_kcal_per_100g=Decimal("120"),
            protein_g_per_100g=Decimal("12"),
            fat_g_per_100g=Decimal("4"),
            carbs_g_per_100g=Decimal("8"),
            fiber_g_per_100g=Decimal("2"),
            standard_serving_amount=None,
            standard_serving_unit=None,
            standard_serving_weight_g=None,
            food_type="user" if owner_id is not None else "system",
            owner_user_id=owner_id,
            provenance="user" if owner_id is not None else "internal",
            source_name=None if owner_id is not None else "yfc-test",
            trust_level="unverified" if owner_id is not None else "verified",
            status="active",
        )
        db.add(food)
        db.flush()
        return food.id


def _today() -> date:
    return timezone_module.today_in_timezone("Europe/Moscow")


def test_natural_parser_supports_newlines_spaces_decimal_comma_and_excludes_water() -> None:
    rows = parse_natural_food_input("творог 180 г банан 120,5\nвода 300")

    assert [row.name for row in rows] == ["творог", "банан", "вода"]
    assert rows[0].amount == Decimal("180")
    assert rows[0].amount_unit == "g"
    assert rows[0].unit_inferred is False
    assert rows[1].amount == Decimal("120.5")
    assert rows[1].amount_unit == "g"
    assert rows[1].unit_inferred is True
    assert rows[2].status == "excluded"


def test_natural_parser_does_not_infer_grams_for_unsupported_units() -> None:
    rows = parse_natural_food_input("банан 1 кг творог 100 г")

    assert [row.name for row in rows] == ["банан", "творог"]
    assert rows[0].raw_text == "банан 1 кг"
    assert rows[0].amount is None
    assert rows[0].amount_unit is None
    assert rows[0].status == "unresolved"
    assert "не поддерживается" in (rows[0].message or "")
    assert rows[1].amount == Decimal("100")
    assert rows[1].amount_unit == "g"


def test_natural_input_alias_review_commit_is_idempotent_and_private(client) -> None:
    headers = _auth(client, 28_001)
    other_headers = _auth(client, 28_002)
    food_id = _store_food("Творог")

    alias = client.post(
        "/api/v1/nutrition/food-aliases",
        headers=headers,
        json={"alias": "теос", "food_id": food_id},
    )
    assert alias.status_code == 201
    assert alias.json()["available"] is True

    preview = client.post(
        "/api/v1/nutrition/diary/natural-input/preview",
        headers=headers,
        json={"text": "теос 140\nвода 250"},
    )
    assert preview.status_code == 200
    rows = preview.json()["rows"]
    assert rows[0]["status"] == "matched"
    assert rows[0]["selected_food_id"] == food_id
    assert rows[0]["candidates"][0]["source"] == "alias"
    assert rows[0]["nutrition"]["energy_kcal"] == "168.00"
    assert rows[1]["status"] == "excluded"

    commit_payload = {
        "diary_date": _today().isoformat(),
        "meal_type": "breakfast",
        "items": [{"row_id": "row-0", "food_id": food_id, "amount": "140", "amount_unit": "g"}],
    }
    first = client.post(
        "/api/v1/nutrition/diary/natural-input/commit",
        headers={**headers, "Idempotency-Key": "natural-input-001"},
        json=commit_payload,
    )
    assert first.status_code == 201
    assert first.json()["replayed"] is False
    repeated = client.post(
        "/api/v1/nutrition/diary/natural-input/commit",
        headers={**headers, "Idempotency-Key": "natural-input-001"},
        json=commit_payload,
    )
    assert repeated.status_code == 201
    assert repeated.json()["replayed"] is True
    assert repeated.json()["entries"][0]["id"] == first.json()["entries"][0]["id"]
    conflicting = client.post(
        "/api/v1/nutrition/diary/natural-input/commit",
        headers={**headers, "Idempotency-Key": "natural-input-001"},
        json={**commit_payload, "items": [{**commit_payload["items"][0], "amount": "141"}]},
    )
    assert conflicting.status_code == 409

    assert client.get("/api/v1/nutrition/food-aliases", headers=other_headers).json()["items"] == []
    foreign_preview = client.post(
        "/api/v1/nutrition/diary/natural-input/preview",
        headers=other_headers,
        json={"text": "теос 140"},
    )
    assert foreign_preview.status_code == 200
    assert foreign_preview.json()["rows"][0]["status"] != "matched"


def test_meal_template_supports_recipe_items_preview_insert_replay_and_ownership(client) -> None:
    headers = _auth(client, 28_010)
    other_headers = _auth(client, 28_011)
    food_id = _store_food("Рис")
    recipe = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Рис с собой",
            "ingredients": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert recipe.status_code == 201
    recipe_id = recipe.json()["id"]

    created = client.post(
        "/api/v1/nutrition/templates",
        headers=headers,
        json={
            "name": "Мой обед",
            "items": [
                {"food_id": food_id, "amount": "80", "amount_unit": "g"},
                {"recipe_id": recipe_id, "amount": "120", "amount_unit": "g"},
            ],
        },
    )
    assert created.status_code == 201
    template = created.json()
    assert template["name"] == "Мой обед"
    assert [item["item_kind"] for item in template["items"]] == ["food", "recipe"]
    assert template["total_weight_g"] == "200.000"
    assert template["totals"]["energy_kcal"] == "240.00"
    template_id = template["id"]

    assert client.get("/api/v1/nutrition/templates", headers=other_headers).json()["items"] == []
    assert (
        client.get(f"/api/v1/nutrition/templates/{template_id}", headers=other_headers).status_code
        == 404
    )

    insert_payload = {"diary_date": _today().isoformat(), "meal_type": "lunch"}
    first = client.post(
        f"/api/v1/nutrition/templates/{template_id}/entries",
        headers={**headers, "Idempotency-Key": "template-insert-001"},
        json=insert_payload,
    )
    assert first.status_code == 201
    assert len(first.json()["entries"]) == 2
    repeated = client.post(
        f"/api/v1/nutrition/templates/{template_id}/entries",
        headers={**headers, "Idempotency-Key": "template-insert-001"},
        json=insert_payload,
    )
    assert repeated.status_code == 201
    assert repeated.json()["replayed"] is True
    assert [entry["id"] for entry in repeated.json()["entries"]] == [
        entry["id"] for entry in first.json()["entries"]
    ]
    conflict = client.post(
        f"/api/v1/nutrition/templates/{template_id}/entries",
        headers={**headers, "Idempotency-Key": "template-insert-001"},
        json={"diary_date": _today().isoformat(), "meal_type": "dinner"},
    )
    assert conflict.status_code == 409


def test_batch_insert_rolls_back_all_items_and_recipe_diary_history_is_immutable(client) -> None:
    headers = _auth(client, 28_020)
    food_id = _store_food("Курица")
    selected_date = _today()
    recipe = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Курица для истории",
            "ingredients": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    recipe_id = recipe.json()["id"]
    diary_entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "recipe_id": recipe_id,
            "diary_date": selected_date.isoformat(),
            "meal_type": "dinner",
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert diary_entry.status_code == 201
    before = diary_entry.json()["nutrition"]

    invalid_batch = client.post(
        "/api/v1/nutrition/diary/natural-input/commit",
        headers={**headers, "Idempotency-Key": "natural-rollback-001"},
        json={
            "diary_date": selected_date.isoformat(),
            "meal_type": "breakfast",
            "items": [
                {"row_id": "row-0", "food_id": food_id, "amount": "50", "amount_unit": "g"},
                {"row_id": "row-1", "food_id": 999999, "amount": "50", "amount_unit": "g"},
            ],
        },
    )
    assert invalid_batch.status_code == 404
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter(FoodDiaryEntry.user_id == 0).count() == 0
        user = db.query(User).filter(User.telegram_user_id == 28_020).one()
        assert (
            db.query(FoodDiaryEntry)
            .filter(
                FoodDiaryEntry.user_id == user.id,
                FoodDiaryEntry.diary_date == selected_date,
                FoodDiaryEntry.meal_type == "breakfast",
            )
            .count()
            == 0
        )

    client.patch(
        f"/api/v1/nutrition/recipes/{recipe_id}",
        headers=headers,
        json={"final_weight_g": "50"},
    )
    client.delete(f"/api/v1/nutrition/recipes/{recipe_id}", headers=headers)
    history = client.get(
        "/api/v1/nutrition/diary",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    )
    assert history.status_code == 200
    dinner_entries = history.json()["meals"][2]["entries"]
    assert dinner_entries[0]["nutrition"] == before
    assert dinner_entries[0]["food_name"] == "Курица для истории"


def test_nutrition_power_migration_is_additive_and_downgrade_is_reversible(tmp_path: Path) -> None:
    migrations_dir = Path(main_module.__file__).resolve().parents[1] / "alembic" / "versions"
    migration_path = migrations_dir / "0090_nutrition_power_features.py"
    spec = importlib.util.spec_from_file_location("nutrition_power_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine(f"sqlite:///{(tmp_path / 'nutrition-power.db').as_posix()}")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table("foods", metadata, Column("id", Integer, primary_key=True))
    Table("recipes", metadata, Column("id", Integer, primary_key=True))
    Table(
        "food_diary_entries",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer, nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        schema = inspect(connection)
        assert {
            "nutrition_meal_templates",
            "nutrition_meal_template_items",
            "food_search_aliases",
            "food_diary_batch_operations",
        } <= set(schema.get_table_names())
        assert "batch_operation_id" in {
            column["name"] for column in schema.get_columns("food_diary_entries")
        }
        migration.downgrade()
        schema = inspect(connection)
        assert not {
            "nutrition_meal_templates",
            "nutrition_meal_template_items",
            "food_search_aliases",
            "food_diary_batch_operations",
        } & set(schema.get_table_names())
        assert "batch_operation_id" not in {
            column["name"] for column in schema.get_columns("food_diary_entries")
        }
    engine.dispose()
