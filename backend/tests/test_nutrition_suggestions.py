from __future__ import annotations

from datetime import date
from decimal import Decimal

from fitminiapp_api.core import timezone as timezone_module
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryBatchOperation
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


def _store_food(
    name: str,
    *,
    protein: Decimal | None = Decimal("12"),
    fat: Decimal | None = Decimal("4"),
    carbs: Decimal | None = Decimal("8"),
) -> int:
    with get_session_context() as db:
        food = Food(
            name=name,
            brand="YFC test",
            energy_kcal_per_100g=Decimal("120"),
            protein_g_per_100g=protein,
            fat_g_per_100g=fat,
            carbs_g_per_100g=carbs,
            fiber_g_per_100g=Decimal("2"),
            standard_serving_amount=None,
            standard_serving_unit=None,
            standard_serving_weight_g=None,
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


def _today() -> date:
    return timezone_module.today_in_timezone("Europe/Moscow")


def test_suggestions_reconcile_authoritative_diary_and_have_stable_bounded_ranking(client) -> None:
    headers = _auth(client, 52_301)
    food_id = _store_food("Йогурт для подсказки")
    _add_target(52_301)
    selected_date = _today()

    created = client.post(
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
    assert created.status_code == 201

    first = client.get(
        "/api/v1/nutrition/diary/suggestions",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    )
    second = client.get(
        "/api/v1/nutrition/diary/suggestions",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    payload = first.json()
    assert payload["mode"] == "deterministic"
    assert payload["targets"] == {
        "energy_kcal": "2000",
        "protein_g": "150",
        "fat_g": "70",
        "carbs_g": "190",
    }
    assert payload["remaining"] == {
        "energy_kcal": "1880.00",
        "protein_g": "138.000",
        "fat_g": "66.000",
        "carbs_g": "182.000",
    }
    assert payload["remaining_confidence"] == "exact"
    assert payload["candidates"] == second.json()["candidates"]
    assert len(payload["candidates"]) <= payload["max_candidates"] == 6
    food_candidate = next(
        item for item in payload["candidates"] if item["candidate_id"] == f"food:{food_id}"
    )
    assert food_candidate["items"][0]["food_id"] == food_id
    assert "used" in food_candidate["sources"]
    assert set(food_candidate["reasons"]) <= {
        "protein_fit",
        "lower_known_fat",
        "recent",
        "frequent",
        "favorite",
        "used",
        "partial_nutrition",
    }


def test_partial_nutrients_remain_unknown_and_are_visible(client) -> None:
    headers = _auth(client, 52_302)
    food_id = _store_food("Неполный продукт", protein=None, fat=None)
    _add_target(52_302)
    selected_date = _today()
    created = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": food_id,
            "diary_date": selected_date.isoformat(),
            "meal_type": "lunch",
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert created.status_code == 201

    response = client.get(
        "/api/v1/nutrition/diary/suggestions",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["remaining"]["protein_g"] is None
    assert payload["remaining"]["fat_g"] is None
    assert payload["remaining"]["carbs_g"] == "182.000"
    assert payload["remaining_confidence"] == "partial"
    assert any("неизвестна" in limitation for limitation in payload["limitations"])
    candidate = next(
        item for item in payload["candidates"] if item["candidate_id"] == f"food:{food_id}"
    )
    assert candidate["nutrition_confidence"] == "partial"
    assert candidate["nutrition"]["protein_g"] is None
    assert candidate["nutrition"]["fat_g"] is None
    assert "partial_nutrition" in candidate["reasons"]


def test_candidates_use_only_existing_food_recipe_and_template_identities(client) -> None:
    headers = _auth(client, 52_303)
    food_id = _store_food("Рис для вариантов")
    _add_target(52_303)
    selected_date = _today()
    created = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": food_id,
            "diary_date": selected_date.isoformat(),
            "meal_type": "dinner",
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert created.status_code == 201
    recipe_response = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Сохранённый рис",
            "ingredients": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert recipe_response.status_code == 201
    recipe_id = recipe_response.json()["id"]
    template_response = client.post(
        "/api/v1/nutrition/templates",
        headers=headers,
        json={
            "name": "Мой сохранённый ужин",
            "items": [
                {"food_id": food_id, "amount": "100", "amount_unit": "g"},
                {"recipe_id": recipe_id, "amount": "100", "amount_unit": "g"},
            ],
        },
    )
    assert template_response.status_code == 201
    template_id = template_response.json()["id"]

    response = client.get(
        "/api/v1/nutrition/diary/suggestions",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    )
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    assert {candidate["candidate_kind"] for candidate in candidates} >= {
        "food",
        "recipe",
        "template",
    }
    for candidate in candidates:
        if candidate["candidate_kind"] == "food":
            assert candidate["identity_id"] == food_id
            assert candidate["items"][0]["food_id"] == food_id
        elif candidate["candidate_kind"] == "recipe":
            assert candidate["identity_id"] == recipe_id
            assert candidate["items"][0]["recipe_id"] == recipe_id
        else:
            assert candidate["identity_id"] == template_id
            assert all(item["food_id"] in {food_id, None} for item in candidate["items"])
            assert any(item["recipe_id"] == recipe_id for item in candidate["items"])


def test_suggestion_preview_does_not_persist_and_confirm_uses_existing_batch_contract(
    client,
) -> None:
    headers = _auth(client, 52_304)
    food_id = _store_food("Продукт для подтверждения")
    _add_target(52_304)
    selected_date = _today()
    created = client.post(
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
    assert created.status_code == 201
    before = client.get(
        "/api/v1/nutrition/diary",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    ).json()
    assert sum(len(meal["entries"]) for meal in before["meals"]) == 1

    preview = client.get(
        "/api/v1/nutrition/diary/suggestions",
        headers=headers,
        params={"diary_date": selected_date.isoformat()},
    )
    assert preview.status_code == 200
    assert (
        sum(
            len(meal["entries"])
            for meal in client.get(
                "/api/v1/nutrition/diary",
                headers=headers,
                params={"diary_date": selected_date.isoformat()},
            ).json()["meals"]
        )
        == 1
    )

    payload = {
        "diary_date": selected_date.isoformat(),
        "meal_type": "snacks",
        "items": [{"food_id": food_id, "amount": "50", "amount_unit": "g"}],
    }
    first = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "suggestion-contract-001"},
        json=payload,
    )
    assert first.status_code == 201
    assert first.json()["operation_kind"] == "suggestion"
    assert first.json()["replayed"] is False
    assert first.json()["entries"][0]["nutrition_source"] == "catalog"
    assert first.json()["entries"][0]["nutrition_confidence"] == "exact"
    repeated = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "suggestion-contract-001"},
        json=payload,
    )
    assert repeated.status_code == 201
    assert repeated.json()["replayed"] is True
    assert repeated.json()["entries"][0]["id"] == first.json()["entries"][0]["id"]
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 52_304).one()
        operation = (
            db.query(FoodDiaryBatchOperation)
            .filter(
                FoodDiaryBatchOperation.user_id == user.id,
                FoodDiaryBatchOperation.idempotency_key == "suggestion-contract-001",
            )
            .one()
        )
        assert operation.operation_kind == "suggestion"
