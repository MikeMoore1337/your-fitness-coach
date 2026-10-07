from __future__ import annotations

from datetime import date
from decimal import Decimal

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.grocery_list import GroceryList, GroceryListItem, GroceryListItemSource
from fitminiapp_api.models.user import User

WEEK_START = date(2026, 8, 17)


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


def _store_food(
    name: str,
    *,
    serving_amount: Decimal | None = None,
    serving_unit: str | None = None,
    serving_weight_g: Decimal | None = None,
) -> int:
    with get_session_context() as db:
        food = Food(
            name=name,
            energy_kcal_per_100g=Decimal("120"),
            protein_g_per_100g=Decimal("12"),
            fat_g_per_100g=Decimal("4"),
            carbs_g_per_100g=Decimal("8"),
            fiber_g_per_100g=Decimal("2"),
            standard_serving_amount=serving_amount,
            standard_serving_unit=serving_unit,
            standard_serving_weight_g=serving_weight_g,
            food_type="system",
            owner_user_id=None,
            provenance="internal",
            source_name="yfc-test",
            trust_level="verified",
            status="active",
        )
        db.add(food)
        db.flush()
        return food.id


def _items(body: dict) -> list[dict]:
    return body["items"]


def test_grocery_generation_aggregates_explicit_units_and_preserves_manual_state(client) -> None:
    headers = _auth(client, 748_001)
    oats_id = _store_food("Овсянка")
    egg_id = _store_food(
        "Яйцо",
        serving_amount=Decimal("1"),
        serving_unit="piece",
        serving_weight_g=Decimal("50"),
    )
    first_recipe = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Каша с яйцами",
            "ingredients": [
                {"food_id": oats_id, "amount": "100", "amount_unit": "g"},
                {"food_id": egg_id, "amount": "2", "amount_unit": "serving"},
            ],
        },
    )
    assert first_recipe.status_code == 201, first_recipe.text
    second_recipe = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Овсянка с яйцом",
            "ingredients": [
                {"food_id": oats_id, "amount": "50", "amount_unit": "g"},
                {"food_id": egg_id, "amount": "50", "amount_unit": "g"},
            ],
        },
    )
    assert second_recipe.status_code == 201, second_recipe.text

    first_plan = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "grocery-plan-add-001"},
        params={
            "plan_date": WEEK_START.isoformat(),
            "meal_type": "breakfast",
            "expected_revision": 0,
        },
        json={"recipe_id": first_recipe.json()["id"], "amount": "200", "amount_unit": "g"},
    )
    assert first_plan.status_code == 201, first_plan.text
    second_plan = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "grocery-plan-add-002"},
        params={
            "plan_date": WEEK_START.isoformat(),
            "meal_type": "lunch",
            "expected_revision": 1,
        },
        json={"recipe_id": second_recipe.json()["id"], "amount": "100", "amount_unit": "g"},
    )
    assert second_plan.status_code == 201, second_plan.text

    generated = client.put(
        "/api/v1/nutrition/grocery-list",
        headers=headers,
        json={"week_start": WEEK_START.isoformat()},
    )
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["generated"] is True
    assert body["stale_sources"] == []
    assert len(_items(body)) == 3
    by_unit = {(item["name"], item["amount_unit"]): item for item in _items(body)}
    assert by_unit[("Овсянка", "g")]["amount"] == "150.000"
    assert by_unit[("Яйцо", "piece")]["amount"] == "2.000"
    assert by_unit[("Яйцо", "g")]["amount"] == "50.000"
    assert len(by_unit[("Овсянка", "g")]["sources"]) == 2

    generated_item_id = by_unit[("Овсянка", "g")]["id"]
    checked = client.patch(
        f"/api/v1/nutrition/grocery-list/items/{generated_item_id}",
        headers=headers,
        json={"checked": True},
    )
    assert checked.status_code == 200, checked.text
    assert (
        next(item for item in _items(checked.json()) if item["id"] == generated_item_id)["checked"]
        is True
    )

    manual = client.post(
        "/api/v1/nutrition/grocery-list/items",
        headers=headers,
        json={
            "week_start": WEEK_START.isoformat(),
            "name": "  Соль  ",
            "amount": "1",
            "amount_unit": "piece",
        },
    )
    assert manual.status_code == 201, manual.text
    manual_item = next(item for item in _items(manual.json()) if item["source_kind"] == "manual")
    edited = client.patch(
        f"/api/v1/nutrition/grocery-list/items/{manual_item['id']}",
        headers=headers,
        json={"name": "Морская соль", "owned": True},
    )
    assert edited.status_code == 200, edited.text
    assert (
        next(item for item in _items(edited.json()) if item["id"] == manual_item["id"])["owned"]
        is True
    )

    replayed = client.put(
        "/api/v1/nutrition/grocery-list",
        headers=headers,
        json={"week_start": WEEK_START.isoformat()},
    )
    assert replayed.status_code == 200, replayed.text
    replayed_items = _items(replayed.json())
    assert len(replayed_items) == 4
    assert (
        next(item for item in replayed_items if item["id"] == generated_item_id)["checked"] is True
    )
    assert next(item for item in replayed_items if item["source_kind"] == "manual")["name"] == (
        "Морская соль"
    )

    deleted = client.delete(
        f"/api/v1/nutrition/grocery-list/items/{manual_item['id']}",
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert all(item["source_kind"] == "generated" for item in _items(deleted.json()))

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 748_001).one()
        grocery_list = db.query(GroceryList).filter(GroceryList.user_id == user.id).one()
        assert db.query(GroceryListItem).filter_by(grocery_list_id=grocery_list.id).count() == 3
        assert (
            db.query(GroceryListItemSource)
            .join(GroceryListItem)
            .filter(GroceryListItem.grocery_list_id == grocery_list.id)
            .count()
            == 4
        )
        assert db.query(FoodDiaryEntry).filter(FoodDiaryEntry.user_id == user.id).count() == 0


def test_grocery_list_is_empty_stale_and_owner_scoped(client) -> None:
    headers = _auth(client, 748_002)
    other_headers = _auth(client, 748_003)

    empty = client.put(
        "/api/v1/nutrition/grocery-list",
        headers=headers,
        json={"week_start": WEEK_START.isoformat()},
    )
    assert empty.status_code == 200
    assert empty.json()["generated"] is True
    assert empty.json()["items"] == []

    food_id = _store_food("Старый продукт")
    recipe = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Старый рецепт",
            "ingredients": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert recipe.status_code == 201
    plan = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "grocery-stale-plan-001"},
        params={
            "plan_date": WEEK_START.isoformat(),
            "meal_type": "dinner",
            "expected_revision": 0,
        },
        json={"recipe_id": recipe.json()["id"], "amount": "100", "amount_unit": "g"},
    )
    assert plan.status_code == 201, plan.text
    initial = client.put(
        "/api/v1/nutrition/grocery-list",
        headers=headers,
        json={"week_start": WEEK_START.isoformat()},
    )
    assert initial.status_code == 200
    initial_item_id = initial.json()["items"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/nutrition/grocery-list/items/{initial_item_id}",
            headers=other_headers,
            json={"checked": True},
        ).status_code
        == 404
    )

    recipe_id = recipe.json()["id"]
    assert (
        client.delete(f"/api/v1/nutrition/recipes/{recipe_id}", headers=headers).status_code == 204
    )

    stale = client.put(
        "/api/v1/nutrition/grocery-list",
        headers=headers,
        json={"week_start": WEEK_START.isoformat()},
    )
    assert stale.status_code == 200, stale.text
    assert stale.json()["items"] == []
    assert len(stale.json()["stale_sources"]) == 1
    assert stale.json()["refresh_required"] is True

    foreign = client.get(
        "/api/v1/nutrition/grocery-list",
        headers=other_headers,
        params={"week_start": WEEK_START.isoformat()},
    )
    assert foreign.status_code == 200
    assert foreign.json()["id"] is None
    assert foreign.json()["items"] == []
    assert (
        client.patch(
            f"/api/v1/nutrition/grocery-list/items/{initial_item_id}",
            headers=other_headers,
            json={"checked": True},
        ).status_code
        == 404
    )


def test_grocery_list_handles_one_stale_source_in_an_aggregated_item(client) -> None:
    headers = _auth(client, 748_004)
    food_id = _store_food("Общий ингредиент")
    recipe_a = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Рецепт A",
            "ingredients": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    recipe_b = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Рецепт B",
            "ingredients": [{"food_id": food_id, "amount": "50", "amount_unit": "g"}],
        },
    )
    assert recipe_a.status_code == 201
    assert recipe_b.status_code == 201
    for index, recipe in enumerate((recipe_a, recipe_b)):
        planned = client.post(
            "/api/v1/nutrition/plans/items",
            headers={**headers, "Idempotency-Key": f"grocery-stale-source-{index}"},
            params={
                "plan_date": (WEEK_START.replace(day=WEEK_START.day + index)).isoformat(),
                "meal_type": "breakfast",
                "expected_revision": 0,
            },
            json={"recipe_id": recipe.json()["id"], "amount": "100", "amount_unit": "g"},
        )
        assert planned.status_code == 201, planned.text

    generated = client.put(
        "/api/v1/nutrition/grocery-list",
        headers=headers,
        json={"week_start": WEEK_START.isoformat()},
    )
    assert generated.status_code == 200, generated.text
    item_id = generated.json()["items"][0]["id"]
    assert len(generated.json()["items"][0]["sources"]) == 2

    assert (
        client.delete(
            f"/api/v1/nutrition/recipes/{recipe_a.json()['id']}",
            headers=headers,
        ).status_code
        == 204
    )
    stale = client.get(
        "/api/v1/nutrition/grocery-list",
        headers=headers,
        params={"week_start": WEEK_START.isoformat()},
    )
    assert stale.status_code == 200, stale.text
    assert stale.json()["refresh_required"] is True
    assert len(stale.json()["items"][0]["sources"]) == 2
    assert len(stale.json()["stale_sources"]) == 1

    refreshed = client.put(
        "/api/v1/nutrition/grocery-list",
        headers=headers,
        json={"week_start": WEEK_START.isoformat()},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["items"][0]["id"] == item_id
    assert refreshed.json()["items"][0]["amount"] == "100.000"
    assert len(refreshed.json()["items"][0]["sources"]) == 1
