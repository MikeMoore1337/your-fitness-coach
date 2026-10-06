from __future__ import annotations

import importlib.util
from datetime import date, timedelta
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


def _items(day: dict) -> list[dict]:
    return [item for slot in day["slots"] for item in slot["items"]]


def test_plan_day_week_crud_replay_stale_write_and_diary_isolation(client) -> None:
    headers = _auth(client, 74_601)
    other_headers = _auth(client, 74_602)
    food_id = _store_food("Плановый рис")
    selected_date = _today()
    recipe = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Плановый рецепт",
            "ingredients": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert recipe.status_code == 201
    recipe_id = recipe.json()["id"]
    template = client.post(
        "/api/v1/nutrition/templates",
        headers=headers,
        json={
            "name": "Плановый шаблон",
            "items": [
                {"food_id": food_id, "amount": "50", "amount_unit": "g"},
                {"recipe_id": recipe_id, "amount": "80", "amount_unit": "g"},
            ],
        },
    )
    assert template.status_code == 201
    template_id = template.json()["id"]

    empty = client.get(
        "/api/v1/nutrition/plans/day",
        headers=headers,
        params={"plan_date": selected_date.isoformat()},
    )
    assert empty.status_code == 200
    assert empty.json()["revision"] == 0
    assert _items(empty.json()) == []

    add_payload = {"food_id": food_id, "amount": "100", "amount_unit": "g"}
    first = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "plan-add-746-1"},
        params={
            "plan_date": selected_date.isoformat(),
            "meal_type": "breakfast",
            "expected_revision": 0,
        },
        json=add_payload,
    )
    assert first.status_code == 201, first.text
    assert first.json()["revision"] == 1
    assert first.json()["planned"]["energy_kcal"] == "120.00"
    assert first.json()["replayed"] is False

    replay = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "plan-add-746-1"},
        params={
            "plan_date": selected_date.isoformat(),
            "meal_type": "breakfast",
            "expected_revision": 0,
        },
        json=add_payload,
    )
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True
    assert replay.json()["revision"] == 1
    assert len(_items(replay.json())) == 1

    key_conflict = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "plan-add-746-1"},
        params={
            "plan_date": selected_date.isoformat(),
            "meal_type": "breakfast",
            "expected_revision": 0,
        },
        json={**add_payload, "amount": "101"},
    )
    assert key_conflict.status_code == 409

    stale = client.patch(
        f"/api/v1/nutrition/plans/items/{_items(first.json())[0]['id']}",
        headers=headers,
        json={"meal_type": "lunch", "expected_revision": 0},
    )
    assert stale.status_code == 409

    recipe_add = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "plan-add-746-2"},
        params={
            "plan_date": selected_date.isoformat(),
            "meal_type": "lunch",
            "expected_revision": 1,
        },
        json={"recipe_id": recipe_id, "amount": "80", "amount_unit": "g"},
    )
    assert recipe_add.status_code == 201, recipe_add.text
    assert recipe_add.json()["revision"] == 2

    template_add = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "plan-add-746-3"},
        params={
            "plan_date": selected_date.isoformat(),
            "meal_type": "dinner",
            "expected_revision": 2,
        },
        json={"template_id": template_id, "amount": "1", "amount_unit": "serving"},
    )
    assert template_add.status_code == 201, template_add.text
    assert template_add.json()["revision"] == 3
    assert len(_items(template_add.json())) == 4

    moved = client.patch(
        f"/api/v1/nutrition/plans/items/{_items(first.json())[0]['id']}",
        headers=headers,
        json={"meal_type": "snacks", "expected_revision": 3},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["revision"] == 4
    moved_item = next(
        item for item in _items(moved.json()) if item["id"] == _items(first.json())[0]["id"]
    )
    assert moved_item["meal_type"] == "snacks"

    edited = client.patch(
        f"/api/v1/nutrition/plans/items/{moved_item['id']}",
        headers=headers,
        json={"amount": "125", "amount_unit": "g", "expected_revision": 4},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["revision"] == 5

    copied = client.post(
        "/api/v1/nutrition/plans/copy",
        headers={**headers, "Idempotency-Key": "plan-copy-746"},
        json={
            "source_date": selected_date.isoformat(),
            "target_date": (selected_date + timedelta(days=1)).isoformat(),
            "expected_revision": 0,
        },
    )
    assert copied.status_code == 200, copied.text
    assert copied.json()["revision"] == 1
    assert len(_items(copied.json())) == 4
    copied_replay = client.post(
        "/api/v1/nutrition/plans/copy",
        headers={**headers, "Idempotency-Key": "plan-copy-746"},
        json={
            "source_date": selected_date.isoformat(),
            "target_date": (selected_date + timedelta(days=1)).isoformat(),
            "expected_revision": 0,
        },
    )
    assert copied_replay.status_code == 200
    assert copied_replay.json()["replayed"] is True
    assert len(_items(copied_replay.json())) == 4

    deleted = client.delete(
        f"/api/v1/nutrition/plans/items/{moved_item['id']}",
        headers=headers,
        params={"expected_revision": 5},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["revision"] == 6

    monday = selected_date - timedelta(days=selected_date.weekday())
    week = client.get(
        "/api/v1/nutrition/plans/week",
        headers=headers,
        params={"week_start": monday.isoformat()},
    )
    assert week.status_code == 200
    assert len(week.json()["days"]) == 7
    assert week.json()["days"][0]["plan_date"] == monday.isoformat()

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 74_601).one()
        assert db.query(FoodDiaryEntry).filter(FoodDiaryEntry.user_id == user.id).count() == 0
        other_user = db.query(User).filter(User.telegram_user_id == 74_602).one()
        private_food_id = _store_food("Чужой продукт", owner_id=other_user.id)

    foreign = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "plan-foreign-746"},
        params={
            "plan_date": selected_date.isoformat(),
            "meal_type": "breakfast",
            "expected_revision": 6,
        },
        json={"food_id": private_food_id, "amount": "50", "amount_unit": "g"},
    )
    assert foreign.status_code == 404
    assert other_headers["Authorization"]


def test_nutrition_plan_migration_is_additive_and_reversible(tmp_path: Path) -> None:
    migrations_dir = Path(main_module.__file__).resolve().parents[1] / "alembic" / "versions"
    migration_path = migrations_dir / "0120_nutrition_plans.py"
    spec = importlib.util.spec_from_file_location("nutrition_plan_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine(f"sqlite:///{(tmp_path / 'nutrition-plan.db').as_posix()}")
    metadata = MetaData()
    for table_name in ("users", "foods", "recipes", "nutrition_meal_templates"):
        Table(table_name, metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        schema = inspect(connection)
        assert {
            "nutrition_plans",
            "nutrition_plan_items",
            "nutrition_plan_operations",
        } <= set(schema.get_table_names())
        migration.downgrade()
        schema = inspect(connection)
        assert not {
            "nutrition_plans",
            "nutrition_plan_items",
            "nutrition_plan_operations",
        } & set(schema.get_table_names())
    engine.dispose()
