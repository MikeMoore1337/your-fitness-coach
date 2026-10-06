from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    CheckConstraint,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
)

from fitminiapp_api import main as main_module
from fitminiapp_api.core import timezone as timezone_module
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryBatchOperation, FoodDiaryEntry
from fitminiapp_api.models.nutrition import NutritionTarget
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


def test_plan_fill_is_explicit_and_consumption_is_atomic_idempotent_and_owner_scoped(
    client,
) -> None:
    headers = _auth(client, 74_603)
    other_headers = _auth(client, 74_604)
    food_id = _store_food("Bridge овсянка")
    _add_target(74_603)
    selected_date = _today()
    diary_entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": food_id,
            "diary_date": selected_date.isoformat(),
            "meal_type": "breakfast",
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert diary_entry.status_code == 201

    preview = client.get(
        "/api/v1/nutrition/plans/suggestions",
        headers=headers,
        params={"plan_date": selected_date.isoformat()},
    )
    assert preview.status_code == 200, preview.text
    candidate = next(
        item for item in preview.json()["candidates"] if item["candidate_id"] == f"food:{food_id}"
    )
    fill_payload = {
        "plan_date": selected_date.isoformat(),
        "meal_type": "lunch",
        "candidate_id": candidate["candidate_id"],
        "items": [
            {
                "position": 0,
                "food_id": food_id,
                "amount": "120",
                "amount_unit": "g",
            }
        ],
        "expected_revision": 0,
    }
    first_fill = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "plan-fill-747-1"},
        json=fill_payload,
    )
    assert first_fill.status_code == 201, first_fill.text
    assert first_fill.json()["revision"] == 1
    assert _items(first_fill.json())[0]["status"] == "planned"
    assert _items(first_fill.json())[0]["diary_entry_id"] is None
    assert first_fill.json()["replayed"] is False
    before_action_diary = client.get(
        "/api/v1/nutrition/diary",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    ).json()
    assert sum(len(meal["entries"]) for meal in before_action_diary["meals"]) == 1

    fill_replay = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "plan-fill-747-1"},
        json=fill_payload,
    )
    assert fill_replay.status_code == 201
    assert fill_replay.json()["replayed"] is True
    assert len(_items(fill_replay.json())) == 1

    second_fill_payload = {**fill_payload, "expected_revision": 1}
    second_fill = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "plan-fill-747-2"},
        json=second_fill_payload,
    )
    assert second_fill.status_code == 201, second_fill.text
    assert second_fill.json()["revision"] == 2
    first_item, second_item = _items(second_fill.json())

    action_payload = {
        "action": "edit_and_consume",
        "amount": "75",
        "amount_unit": "g",
        "meal_type": "dinner",
        "expected_revision": 2,
    }
    action = client.post(
        f"/api/v1/nutrition/plans/items/{first_item['id']}/action",
        headers={**headers, "Idempotency-Key": "plan-action-747-1"},
        json=action_payload,
    )
    assert action.status_code == 200, action.text
    assert action.json()["item"]["status"] == "consumed"
    assert action.json()["item"]["diary_entry_id"] is not None
    assert action.json()["diagnostic"] == "planned_item_consumed"
    diary_entry_id = action.json()["diary_entry_id"]

    action_replay = client.post(
        f"/api/v1/nutrition/plans/items/{first_item['id']}/action",
        headers={**headers, "Idempotency-Key": "plan-action-747-1"},
        json=action_payload,
    )
    assert action_replay.status_code == 200
    assert action_replay.json()["replayed"] is True
    assert action_replay.json()["diary_entry_id"] == diary_entry_id

    already_resolved = client.post(
        f"/api/v1/nutrition/plans/items/{first_item['id']}/action",
        headers={**headers, "Idempotency-Key": "plan-action-747-new"},
        json={"action": "consume", "expected_revision": 4},
    )
    assert already_resolved.status_code == 409
    assert already_resolved.json()["detail"]["code"] == "planned_item_already_resolved"

    stale = client.post(
        f"/api/v1/nutrition/plans/items/{second_item['id']}/action",
        headers={**headers, "Idempotency-Key": "plan-action-747-stale"},
        json={"action": "skip", "expected_revision": 2},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_plan"

    skip = client.post(
        f"/api/v1/nutrition/plans/items/{second_item['id']}/action",
        headers={**headers, "Idempotency-Key": "plan-action-747-2"},
        json={"action": "skip", "expected_revision": 3},
    )
    assert skip.status_code == 200, skip.text
    assert skip.json()["item"]["status"] == "skipped"
    assert skip.json()["diary_entry_id"] is None

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 74_603).one()
        assert db.query(FoodDiaryEntry).filter(FoodDiaryEntry.user_id == user.id).count() == 2
        operation = (
            db.query(FoodDiaryBatchOperation)
            .filter(
                FoodDiaryBatchOperation.user_id == user.id,
                FoodDiaryBatchOperation.operation_kind == "planned_item",
            )
            .one()
        )
        assert operation.idempotency_key == f"planned-item-{first_item['id']}"

    deleted_diary_entry = client.delete(
        f"/api/v1/nutrition/diary/entries/{diary_entry_id}",
        headers=headers,
    )
    assert deleted_diary_entry.status_code == 204
    plan_after_diary_delete = client.get(
        "/api/v1/nutrition/plans/day",
        headers=headers,
        params={"plan_date": selected_date.isoformat()},
    )
    assert plan_after_diary_delete.status_code == 200
    consumed_after_diary_delete = next(
        item for item in _items(plan_after_diary_delete.json()) if item["id"] == first_item["id"]
    )
    assert consumed_after_diary_delete["status"] == "consumed"
    assert consumed_after_diary_delete["diary_entry_id"] is None

    foreign = client.post(
        f"/api/v1/nutrition/plans/items/{first_item['id']}/action",
        headers={**other_headers, "Idempotency-Key": "plan-action-747-foreign"},
        json={"action": "consume", "expected_revision": 0},
    )
    assert foreign.status_code == 404


def test_nutrition_plan_migration_is_additive_and_reversible(tmp_path: Path) -> None:
    migrations_dir = Path(main_module.__file__).resolve().parents[1] / "alembic" / "versions"
    migration_paths = [
        migrations_dir / "0120_nutrition_plans.py",
        migrations_dir / "0121_nutrition_plan_consumption_bridge.py",
    ]
    migrations = []
    for index, migration_path in enumerate(migration_paths):
        spec = importlib.util.spec_from_file_location(
            f"nutrition_plan_migration_{index}", migration_path
        )
        assert spec is not None and spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migrations.append(migration)

    engine = create_engine(f"sqlite:///{(tmp_path / 'nutrition-plan.db').as_posix()}")
    metadata = MetaData()
    for table_name in (
        "users",
        "foods",
        "recipes",
        "nutrition_meal_templates",
        "food_diary_entries",
    ):
        Table(table_name, metadata, Column("id", Integer, primary_key=True))
    Table(
        "food_diary_batch_operations",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("operation_kind", String(24), nullable=False),
        CheckConstraint(
            "operation_kind IN ('meal_template', 'natural_input', 'suggestion')",
            name="ck_food_diary_batch_operations_kind",
        ),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        for migration in migrations:
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
        schema = inspect(connection)
        assert {
            "nutrition_plans",
            "nutrition_plan_items",
            "nutrition_plan_operations",
        } <= set(schema.get_table_names())
        assert {
            "status",
            "diary_entry_id",
            "action_idempotency_key",
            "action_request_fingerprint",
        } <= {column["name"] for column in schema.get_columns("nutrition_plan_items")}
        for migration in reversed(migrations):
            migration.op = Operations(MigrationContext.configure(connection))
            migration.downgrade()
        schema = inspect(connection)
        assert not {
            "nutrition_plans",
            "nutrition_plan_items",
            "nutrition_plan_operations",
        } & set(schema.get_table_names())
    engine.dispose()
