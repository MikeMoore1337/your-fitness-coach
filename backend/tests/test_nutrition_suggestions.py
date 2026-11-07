from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier, Event

import pytest
from sqlalchemy import event

from fitminiapp_api.core import timezone as timezone_module
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryBatchOperation
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.program import UserProgram
from fitminiapp_api.models.recipe import RecipeIngredient
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_power import FoodDiaryBatchItem
from fitminiapp_api.services import nutrition_suggestions as suggestions_service
from fitminiapp_api.services.food_diary import create_food_diary_batch


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
    owner_id: int | None = None,
    protein: Decimal | None = Decimal("12"),
    fat: Decimal | None = Decimal("4"),
    carbs: Decimal | None = Decimal("8"),
    fiber: Decimal | None = Decimal("2"),
) -> int:
    with get_session_context() as db:
        food = Food(
            name=name,
            brand="YFC test",
            energy_kcal_per_100g=Decimal("120"),
            protein_g_per_100g=protein,
            fat_g_per_100g=fat,
            carbs_g_per_100g=carbs,
            fiber_g_per_100g=fiber,
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


def _add_target(telegram_user_id: int, effective_from: date | None = None) -> None:
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
                effective_from=effective_from or _today(),
            )
        )


def _today() -> date:
    return timezone_module.today_in_timezone("Europe/Moscow")


def _with_preview(client, headers: dict[str, str], payload: dict) -> dict:
    response = client.post(
        "/api/v1/nutrition/diary/suggestions/preview", headers=headers, json=payload
    )
    assert response.status_code == 200, response.text
    return {**payload, "preview_token": response.json()["preview_token"]}


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


def test_suggestions_rank_candidates_using_all_known_remaining_macros(client) -> None:
    headers = _auth(client, 52_320)
    _add_target(52_320)
    with get_session_context() as db:
        user = db.query(User).filter_by(telegram_user_id=52_320).one()
        target = db.query(NutritionTarget).filter_by(user_id=user.id).one()
        target.fat_g = 10
        target.carbs_g = 325
    consumed = _store_food("Уже съедено", protein=Decimal("5"), fat=Decimal("6"))
    fits = _store_food("Укладывается", protein=Decimal("12"), fat=Decimal("1"))
    over = _store_food(
        "Больше остатка жиров", protein=Decimal("17"), fat=Decimal("5"), carbs=Decimal("1")
    )
    selected_date = _today().isoformat()
    entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "diary_date": selected_date,
            "meal_type": "breakfast",
            "food_id": consumed,
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert entry.status_code == 201
    for food_id in (fits, over):
        assert (
            client.put(f"/api/v1/nutrition/foods/{food_id}/favorite", headers=headers).status_code
            == 200
        )
    response = client.get(
        "/api/v1/nutrition/diary/suggestions",
        headers=headers,
        params={"diary_date": selected_date},
    )
    assert response.status_code == 200
    assert Decimal(response.json()["remaining"]["fat_g"]) == 4
    candidates = [candidate["identity_id"] for candidate in response.json()["candidates"]]
    assert candidates.index(fits) < candidates.index(over)


def test_no_target_or_saved_products_produces_no_candidates(client) -> None:
    headers = _auth(client, 52_323)
    food_id = _store_food("Неиспользованный продукт")
    selected_date = _today().isoformat()
    params = {"diary_date": selected_date}
    no_target = client.get("/api/v1/nutrition/diary/suggestions", headers=headers, params=params)
    assert no_target.status_code == 200
    assert no_target.json()["targets"] is None
    assert no_target.json()["candidates"] == []
    preview = client.post(
        "/api/v1/nutrition/diary/suggestions/preview",
        headers=headers,
        json={
            "diary_date": selected_date,
            "meal_type": "snacks",
            "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert preview.status_code == 422
    _add_target(52_323)
    no_products = client.get("/api/v1/nutrition/diary/suggestions", headers=headers, params=params)
    assert no_products.status_code == 200
    assert no_products.json()["targets"] is not None
    assert no_products.json()["candidates"] == []


def test_openapi_preserves_commit_names_and_describes_preview_conflicts(client) -> None:
    schema = client.get("/openapi.json").json()
    cases = (
        ("/api/v1/nutrition/diary/suggestions/preview", "NutritionSuggestionPreviewRequest", "200"),
        ("/api/v1/nutrition/diary/suggestions/commit", "NutritionSuggestionCommitRequest", "201"),
        ("/api/v1/nutrition/plans/suggestions/preview", "NutritionPlanFillPreviewRequest", "200"),
        ("/api/v1/nutrition/plans/fill", "NutritionPlanFillRequest", "201"),
    )
    for path, model, success in cases:
        operation = schema["paths"][path]["post"]
        assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"] == (
            f"#/components/schemas/{model}"
        )
        assert {success, "404", "409", "422"} <= set(operation["responses"])
    for model in ("NutritionSuggestionCommitRequest", "NutritionPlanFillRequest"):
        commit = schema["components"]["schemas"][model]
        assert "preview_token" not in commit["required"]
        assert "повтор прежней операции" in commit["properties"]["preview_token"]["description"]
    preview = schema["components"]["schemas"]["NutritionSuggestionPreviewResponse"]
    for field in ("planned", "projected_after", "target_id", "target_weight_kg", "target_goal"):
        assert any(option.get("type") == "null" for option in preview["properties"][field]["anyOf"])


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


def test_suggestions_account_for_pending_plan_without_double_counting_consumed_items(
    client,
) -> None:
    headers = _auth(client, 52_317)
    _add_target(52_317)
    food_id = _store_food("Продукт в плане")
    selected_date = _today().isoformat()
    entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": food_id,
            "diary_date": selected_date,
            "meal_type": "breakfast",
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert entry.status_code == 201
    plan = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "suggestion-plan-52317"},
        params={"plan_date": selected_date, "meal_type": "dinner", "expected_revision": 0},
        json={"food_id": food_id, "amount": "100", "amount_unit": "g"},
    )
    assert plan.status_code == 201
    item_id = next(item["id"] for slot in plan.json()["slots"] for item in slot["items"])
    suggestions = client.get(
        "/api/v1/nutrition/diary/suggestions",
        headers=headers,
        params={"diary_date": selected_date},
    )
    assert suggestions.status_code == 200
    assert Decimal(suggestions.json()["remaining"]["protein_g"]) == 126
    assert suggestions.json()["remaining_includes_plan"] is True
    consumed = client.post(
        f"/api/v1/nutrition/plans/items/{item_id}/action",
        headers={**headers, "Idempotency-Key": "suggestion-consume-52317"},
        json={"action": "consume", "expected_revision": 1},
    )
    assert consumed.status_code == 200, consumed.text
    suggestions = client.get(
        "/api/v1/nutrition/diary/suggestions",
        headers=headers,
        params={"diary_date": selected_date},
    )
    assert suggestions.status_code == 200
    assert Decimal(suggestions.json()["remaining"]["protein_g"]) == 126
    assert suggestions.json()["remaining_includes_plan"] is False


def test_suggestion_reasons_do_not_claim_a_fit_when_protein_is_already_over_target(client) -> None:
    headers = _auth(client, 52_308)
    _add_target(52_308)
    food_id = _store_food("Продукт без белка", protein=Decimal("0"))
    selected_date = _today().isoformat()
    for payload in (
        {"food_id": food_id, "amount": "100", "amount_unit": "g"},
        {
            "quick_add": {"energy_kcal": "640", "protein_g": "160", "fat_g": "0", "carbs_g": "0"},
            "amount": "1",
            "amount_unit": "serving",
        },
    ):
        entry = client.post(
            "/api/v1/nutrition/diary/entries",
            headers=headers,
            json={**payload, "diary_date": selected_date, "meal_type": "breakfast"},
        )
        assert entry.status_code == 201, entry.text
    response = client.get(
        "/api/v1/nutrition/diary/suggestions",
        headers=headers,
        params={"diary_date": selected_date},
    )
    assert response.status_code == 200
    assert Decimal(response.json()["remaining"]["protein_g"]) < 0
    candidate = next(
        item for item in response.json()["candidates"] if item["candidate_id"] == f"food:{food_id}"
    )
    assert "protein_fit" not in candidate["reasons"]
    assert "lower_known_fat" not in candidate["reasons"]


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
    payload = _with_preview(client, headers, payload)
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


def test_suggestion_retry_preserves_a_completed_past_day(client) -> None:
    headers = _auth(client, 52_305)
    food_id = _store_food("Продукт для завершённого дня")
    selected_date = (_today() - timedelta(days=1)).isoformat()
    _add_target(52_305, date.fromisoformat(selected_date))
    payload = {
        "diary_date": selected_date,
        "meal_type": "snacks",
        "items": [{"food_id": food_id, "amount": "50", "amount_unit": "g"}],
    }
    payload = _with_preview(client, headers, payload)
    first = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "suggestion-past-52305"},
        json=payload,
    )
    assert first.status_code == 201
    completed = client.put(
        "/api/v1/nutrition/diary/status",
        headers=headers,
        json={"diary_date": selected_date, "status": "complete"},
    )
    assert completed.status_code == 200
    before = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
    ).json()

    retry = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "suggestion-past-52305"},
        json=payload,
    )
    assert retry.status_code == 201
    assert retry.json()["replayed"] is True
    assert retry.json()["entries"][0]["id"] == first.json()["entries"][0]["id"]
    changed = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "suggestion-past-52305-new"},
        json=payload,
    )
    assert changed.status_code == 409
    after = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
    ).json()
    assert after == before
    reopened = client.put(
        "/api/v1/nutrition/diary/status",
        headers=headers,
        json={"diary_date": selected_date, "status": "incomplete"},
    )
    assert reopened.status_code == 200
    still_denied = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "suggestion-past-52305-reopened"},
        json=payload,
    )
    assert still_denied.status_code == 409
    assert sum(len(meal["entries"]) for meal in reopened.json()["meals"]) == 1


def test_confirmed_suggestion_matches_diary_and_report(client) -> None:
    headers = _auth(client, 52_309)
    _add_target(52_309)
    food_id = _store_food("Продукт для сверки отчёта")
    selected_date = _today().isoformat()
    payload = _with_preview(
        client,
        headers,
        {
            "diary_date": selected_date,
            "meal_type": "snacks",
            "items": [{"food_id": food_id, "amount": "150", "amount_unit": "g"}],
        },
    )
    confirmed = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "suggestion-report-52309"},
        json=payload,
    )
    assert confirmed.status_code == 201
    diary = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
    ).json()
    report_response = client.get(
        "/api/v1/workouts/progress/nutrition-report",
        headers=headers,
        params={"period": "days_7"},
    )
    assert report_response.status_code == 200
    report = report_response.json()
    point = next(day for day in report["daily"] if day["diary_date"] == selected_date)
    for diary_field, report_field in (
        ("energy_kcal", "calories"),
        ("protein_g", "protein_g"),
        ("fat_g", "fat_g"),
        ("carbs_g", "carbs_g"),
        ("fiber_g", "fiber_g"),
    ):
        assert Decimal(str(point[report_field])) == Decimal(diary["totals"][diary_field])
    assert point["status"] == "incomplete"
    assert report["summary"]["protein_g"]["sample_days"] == 0

    completed = client.put(
        "/api/v1/nutrition/diary/status",
        headers=headers,
        json={"diary_date": selected_date, "status": "complete"},
    )
    assert completed.status_code == 200
    report = client.get(
        "/api/v1/workouts/progress/nutrition-report",
        headers=headers,
        params={"period": "days_7"},
    ).json()
    assert report["summary"]["protein_g"]["sample_days"] == 1
    assert Decimal(str(report["summary"]["protein_g"]["average"])) == Decimal(
        diary["totals"]["protein_g"]
    )


def test_exact_preview_confirm_retry_and_unknown_nutrients(client) -> None:
    headers = _auth(client, 52_312)
    _add_target(52_312)
    known_food = _store_food("Известный продукт")
    partial_food = _store_food("Неполный состав", fat=None, fiber=None)
    selected_date = _today().isoformat()
    entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": known_food,
            "diary_date": selected_date,
            "meal_type": "breakfast",
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert entry.status_code == 201
    payload = {
        "diary_date": selected_date,
        "meal_type": "snacks",
        "items": [{"food_id": partial_food, "amount": "150", "amount_unit": "g"}],
    }
    before = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
    ).json()
    preview_response = client.post(
        "/api/v1/nutrition/diary/suggestions/preview", headers=headers, json=payload
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert Decimal(preview["before"]["energy_kcal"]) == 120
    assert Decimal(preview["addition"]["energy_kcal"]) == 180
    assert Decimal(preview["after"]["energy_kcal"]) == 300
    assert Decimal(preview["after"]["protein_g"]) == 30
    assert preview["addition"]["fat_g"] is None
    assert preview["after"]["fat_g"] is None
    assert preview["after"]["fiber_g"] is None
    assert preview["remaining_after"]["fat_g"] is None
    assert preview["target_id"] is not None
    assert len(preview["preview_token"]) == 64
    assert (
        client.get(
            "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
        ).json()
        == before
    )

    invalid = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "preview-invalid-52312"},
        json={**payload, "preview_token": "0" * 64},
    )
    assert invalid.status_code == 409
    confirmed = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "preview-confirm-52312"},
        json={**payload, "preview_token": preview["preview_token"]},
    )
    assert confirmed.status_code == 201, confirmed.text
    after = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
    ).json()
    assert after["totals"] == preview["after"]
    retry = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "preview-confirm-52312"},
        json={**payload, "preview_token": preview["preview_token"]},
    )
    assert retry.status_code == 201
    assert retry.json()["replayed"] is True
    assert retry.json()["entries"][0]["id"] == confirmed.json()["entries"][0]["id"]


def test_confirmation_requires_preview_but_replays_legacy_operation(client) -> None:
    headers = _auth(client, 52_317)
    _add_target(52_317)
    food_id = _store_food("Продукт для старого повтора")
    selected_date = _today()
    payload = {
        "diary_date": selected_date.isoformat(),
        "meal_type": "snacks",
        "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
    }
    denied = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "preview-required-52317"},
        json=payload,
    )
    assert denied.status_code == 409
    with get_session_context() as db:
        user = db.query(User).filter_by(telegram_user_id=52_317).one()
        legacy = create_food_diary_batch(
            db,
            user,
            diary_date=selected_date,
            meal_type="snacks",
            items=[FoodDiaryBatchItem.model_validate(payload["items"][0])],
            idempotency_key="legacy-suggestion-52317",
            operation_kind="suggestion",
        )
    replay = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "legacy-suggestion-52317"},
        json=payload,
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["entries"][0]["id"] == legacy.entries[0].id
    changed = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "legacy-suggestion-52317"},
        json={**payload, "items": [{**payload["items"][0], "amount": "50"}]},
    )
    assert changed.status_code == 409


def test_incompatible_saved_target_does_not_generate_a_suggestion(client) -> None:
    headers = _auth(client, 52_318)
    _add_target(52_318)
    food_id = _store_food("Продукт при несовместимой цели")
    selected_date = _today().isoformat()
    entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "diary_date": selected_date,
            "meal_type": "breakfast",
            "food_id": food_id,
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert entry.status_code == 201
    saved = client.post(
        "/api/v1/nutrition/targets/manual",
        headers=headers,
        json={
            "calories": 2000,
            "protein_g": 200,
            "fat_g": 100,
            "carbs_g": 400,
            "confirm_energy_mismatch": True,
        },
    )
    assert saved.status_code == 200, saved.text
    suggestions = client.get(
        "/api/v1/nutrition/diary/suggestions",
        headers=headers,
        params={"diary_date": selected_date},
    )
    assert suggestions.status_code == 200
    assert suggestions.json()["not_calculable"] is True
    assert suggestions.json()["candidates"] == []
    assert any("не согласуются" in text for text in suggestions.json()["limitations"])
    preview = client.post(
        "/api/v1/nutrition/diary/suggestions/preview",
        headers=headers,
        json={
            "diary_date": selected_date,
            "meal_type": "snacks",
            "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert preview.status_code == 422
    assert "не согласуются" in preview.text


def test_preview_rejects_changed_target_and_another_user(client) -> None:
    headers = _auth(client, 52_313)
    other_headers = _auth(client, 52_314)
    _add_target(52_313)
    _add_target(52_314)
    food_id = _store_food("Продукт для проверки цели")
    selected_date = _today().isoformat()
    payload = {
        "diary_date": selected_date,
        "meal_type": "snacks",
        "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
    }
    preview = client.post(
        "/api/v1/nutrition/diary/suggestions/preview", headers=headers, json=payload
    )
    assert preview.status_code == 200
    token = preview.json()["preview_token"]
    foreign = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**other_headers, "Idempotency-Key": "preview-foreign-52314"},
        json={**payload, "preview_token": token},
    )
    assert foreign.status_code == 409
    changed = client.post(
        "/api/v1/nutrition/targets/manual",
        headers=headers,
        json={"calories": 2200, "protein_g": 150, "fat_g": 80, "carbs_g": 220},
    )
    assert changed.status_code == 200, changed.text
    stale = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "preview-stale-52313"},
        json={**payload, "preview_token": token},
    )
    assert stale.status_code == 409
    day = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
    ).json()
    assert sum(len(meal["entries"]) for meal in day["meals"]) == 0


@pytest.mark.parametrize("change", ["food", "plan"])
def test_preview_rejects_changed_food_or_plan(client, change: str) -> None:
    headers = _auth(client, 52_322)
    _add_target(52_322)
    food_id = _store_food("Продукт для проверки изменений")
    selected_date = _today().isoformat()
    payload = _with_preview(
        client,
        headers,
        {
            "diary_date": selected_date,
            "meal_type": "snacks",
            "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    if change == "food":
        with get_session_context() as db:
            db.get(Food, food_id).energy_kcal_per_100g = Decimal("130")
    else:
        plan = client.post(
            "/api/v1/nutrition/plans/items",
            headers={**headers, "Idempotency-Key": "preview-plan-change-52322"},
            params={"plan_date": selected_date, "meal_type": "dinner", "expected_revision": 0},
            json={"food_id": food_id, "amount": "100", "amount_unit": "g"},
        )
        assert plan.status_code == 201
    result = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "preview-source-change-52322"},
        json=payload,
    )
    assert result.status_code == 409
    day = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
    ).json()
    assert sum(len(meal["entries"]) for meal in day["meals"]) == 0


@pytest.mark.parametrize("day_type", ["training", "rest", "recovery"])
def test_preview_uses_the_dated_override_for_each_day_type(client, day_type: str) -> None:
    headers = _auth(client, 52_321)
    _add_target(52_321)
    food_id = _store_food("Продукт для цели на день")
    selected_date = _today().isoformat()
    override = client.post(
        "/api/v1/nutrition/targets/dates",
        headers={**headers, "Idempotency-Key": f"target-day-{day_type}-52321"},
        json={
            "effective_from": selected_date,
            "day_type": day_type,
            "calories": 2300,
            "protein_g": 150,
            "fat_g": 70,
            "carbs_g": 270,
        },
    )
    assert override.status_code == 200, override.text
    payload = {
        "diary_date": selected_date,
        "meal_type": "snacks",
        "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
    }
    preview = client.post(
        "/api/v1/nutrition/diary/suggestions/preview", headers=headers, json=payload
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["target_id"] == override.json()["target"]["id"]
    assert Decimal(preview.json()["targets"]["energy_kcal"]) == 2300
    assert Decimal(preview.json()["remaining_after"]["energy_kcal"]) == 2180
    report = client.get(
        "/api/v1/workouts/progress/nutrition-report", headers=headers, params={"period": "days_7"}
    )
    assert report.status_code == 200
    day = next(row for row in report.json()["daily"] if row["diary_date"] == selected_date)
    assert day["target_calories"] == 2300


def test_plan_preview_resolves_saved_cycle_targets(client) -> None:
    from test_program_week_cycle import _payload

    headers = _auth(client, 52_329)
    program_payload = _payload(client, headers)
    program_payload["week_cycle"] = {
        "length_weeks": 3,
        "repeat": True,
        "week_types": ["light", "medium", "heavy"],
    }
    created = client.post("/api/v1/programs/templates", headers=headers, json=program_payload)
    assert created.status_code == 200, created.text
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 12},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    with get_session_context() as db:
        start = db.get(UserProgram, program_id).start_date

    base = {"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 190}
    assert (
        client.post("/api/v1/nutrition/targets/manual", headers=headers, json=base).status_code
        == 200
    )
    for index, (day_type, week_type, calories, carbs) in enumerate(
        [
            ("training", None, 2200, 242),
            ("training", "medium", 2300, 270),
            ("rest", None, 1900, 170),
        ]
    ):
        rule = {
            **base,
            "calories": calories,
            "carbs_g": carbs,
            "program_id": program_id,
            "revision_number": 1,
            "effective_from": (start + timedelta(days=1)).isoformat(),
            "scope": "template",
            "day_type": day_type,
            "week_type": week_type,
        }
        rule_preview = client.post(
            "/api/v1/nutrition/targets/schedule/preview",
            headers=headers,
            json={
                **rule,
                "date_from": (start + timedelta(days=1)).isoformat(),
                "date_to": (start + timedelta(days=21)).isoformat(),
            },
        )
        assert rule_preview.status_code == 200, rule_preview.text
        saved = client.post(
            "/api/v1/nutrition/targets/schedule",
            headers={**headers, "Idempotency-Key": f"suggestion-cycle-rule-52329-{index}"},
            json={
                **rule,
                "expected_binding_id": rule_preview.json()["expected_binding_id"],
                "expected_target_version": rule_preview.json()["expected_target_version"],
            },
        )
        assert saved.status_code == 200, saved.text

    food_id = _store_food("Продукт для цели по циклу")
    assert (
        client.put(f"/api/v1/nutrition/foods/{food_id}/favorite", headers=headers).status_code
        == 200
    )
    for selected_date, calories in (
        (start + timedelta(days=1), 1900),
        (start + timedelta(weeks=1), 2300),
        (start + timedelta(weeks=2), 2200),
    ):
        preview = client.post(
            "/api/v1/nutrition/plans/suggestions/preview",
            headers=headers,
            json={
                "plan_date": selected_date.isoformat(),
                "meal_type": "lunch",
                "candidate_id": f"food:{food_id}",
                "items": [{"position": 0, "food_id": food_id, "amount": "100", "amount_unit": "g"}],
                "expected_revision": 0,
            },
        )
        assert preview.status_code == 200, preview.text
        assert Decimal(preview.json()["targets"]["energy_kcal"]) == calories
        resolved = client.get(
            "/api/v1/nutrition/targets/for-date",
            headers=headers,
            params={"target_date": selected_date.isoformat()},
        )
        assert resolved.status_code == 200, resolved.text
        assert preview.json()["target_id"] == resolved.json()["target"]["id"]


def test_preview_checks_explicit_limits_against_pending_plan_without_saving_them(client) -> None:
    headers = _auth(client, 52_315)
    _add_target(52_315)
    food_id = _store_food("Продукт с известным жиром")
    partial_food = _store_food("Продукт с неизвестным жиром", fat=None)
    selected_date = _today().isoformat()
    entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": food_id,
            "diary_date": selected_date,
            "meal_type": "breakfast",
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert entry.status_code == 201
    planned = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "preview-plan-52315"},
        params={"plan_date": selected_date, "meal_type": "dinner", "expected_revision": 0},
        json={"food_id": food_id, "amount": "100", "amount_unit": "g"},
    )
    assert planned.status_code == 201
    payload = {
        "diary_date": selected_date,
        "meal_type": "snacks",
        "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        "constraints": {"max_fat_g": "10"},
    }
    preview = client.post(
        "/api/v1/nutrition/diary/suggestions/preview", headers=headers, json=payload
    )
    assert preview.status_code == 200, preview.text
    result = preview.json()
    assert Decimal(result["after"]["fat_g"]) == 8
    assert Decimal(result["planned"]["fat_g"]) == 4
    assert Decimal(result["projected_after"]["fat_g"]) == 12
    assert result["constraint_status"] == "violated"
    denied = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "preview-limit-52315"},
        json={**payload, "preview_token": result["preview_token"]},
    )
    assert denied.status_code == 409
    allowed_payload = {**payload, "constraints": {"max_fat_g": "12"}}
    allowed = client.post(
        "/api/v1/nutrition/diary/suggestions/preview", headers=headers, json=allowed_payload
    ).json()
    assert allowed["constraint_status"] == "satisfied"
    confirmed = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "preview-limit-52315"},
        json={**allowed_payload, "preview_token": allowed["preview_token"]},
    )
    assert confirmed.status_code == 201, confirmed.text
    conflicting_retry = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "preview-limit-52315"},
        json={**payload, "preview_token": allowed["preview_token"]},
    )
    assert conflicting_retry.status_code == 409
    without_constraints = client.post(
        "/api/v1/nutrition/diary/suggestions/preview",
        headers=headers,
        json={key: value for key, value in payload.items() if key != "constraints"},
    )
    assert without_constraints.json()["constraint_status"] == "not_set"
    unknown = client.post(
        "/api/v1/nutrition/diary/suggestions/preview",
        headers=headers,
        json={**payload, "items": [{"food_id": partial_food, "amount": "100", "amount_unit": "g"}]},
    )
    assert unknown.json()["constraint_status"] == "unknown"


def test_unavailable_planned_food_makes_limit_unknown_and_blocks_confirmation(client) -> None:
    headers = _auth(client, 52_330)
    _add_target(52_330)
    planned_food = _store_food("Недоступный продукт плана")
    selected_food = _store_food("Доступный продукт")
    selected_date = _today().isoformat()
    planned = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "unavailable-plan-52330"},
        params={"plan_date": selected_date, "meal_type": "dinner", "expected_revision": 0},
        json={"food_id": planned_food, "amount": "100", "amount_unit": "g"},
    )
    assert planned.status_code == 201
    with get_session_context() as db:
        db.get(Food, planned_food).status = "disabled"
    payload = {
        "diary_date": selected_date,
        "meal_type": "snacks",
        "items": [{"food_id": selected_food, "amount": "100", "amount_unit": "g"}],
        "constraints": {"max_energy_kcal": "2000"},
    }
    preview = client.post(
        "/api/v1/nutrition/diary/suggestions/preview", headers=headers, json=payload
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["planned"] is None
    assert preview.json()["projected_after"] is None
    assert preview.json()["constraint_status"] == "unknown"
    denied = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "unknown-plan-limit-52330"},
        json={**payload, "preview_token": preview.json()["preview_token"]},
    )
    assert denied.status_code == 409


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_unavailable_plan_source_cannot_change_during_confirmation(client) -> None:
    headers = _auth(client, 52_331)
    _add_target(52_331)
    planned_food = _store_food("Временно недоступный продукт плана")
    selected_food = _store_food("Доступный вариант")
    selected_date = _today().isoformat()
    planned = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "source-plan-52331"},
        params={"plan_date": selected_date, "meal_type": "dinner", "expected_revision": 0},
        json={"food_id": planned_food, "amount": "100", "amount_unit": "g"},
    )
    assert planned.status_code == 201
    with get_session_context() as db:
        db.get(Food, planned_food).status = "disabled"
    payload = _with_preview(
        client,
        headers,
        {
            "diary_date": selected_date,
            "meal_type": "snacks",
            "items": [{"food_id": selected_food, "amount": "100", "amount_unit": "g"}],
        },
    )
    with ThreadPoolExecutor(max_workers=1) as executor, get_session_context() as db:
        locked = db.query(Food).filter_by(id=planned_food).with_for_update().one()
        locked.status = "active"
        db.flush()
        future = executor.submit(
            client.post,
            "/api/v1/nutrition/diary/suggestions/commit",
            headers={**headers, "Idempotency-Key": "source-plan-race-52331"},
            json=payload,
        )
        response = future.result(timeout=10)
        assert response.status_code == 409, response.text


def test_preview_checks_explicit_exclusions_in_recipe_ingredients(client) -> None:
    headers = _auth(client, 52_316)
    _add_target(52_316)
    food_id = _store_food("Исключаемый продукт")
    recipe = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Рецепт с продуктом",
            "ingredients": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert recipe.status_code == 201
    payload = {
        "diary_date": _today().isoformat(),
        "meal_type": "lunch",
        "items": [{"recipe_id": recipe.json()["id"], "amount": "100", "amount_unit": "g"}],
        "constraints": {"excluded_food_ids": [food_id]},
    }
    preview = client.post(
        "/api/v1/nutrition/diary/suggestions/preview", headers=headers, json=payload
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["constraint_status"] == "violated"
    assert any(
        "состав готовых продуктов не проверяется" in message
        for message in preview.json()["constraint_messages"]
    )
    confirm = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "preview-exclusion-52316"},
        json={**payload, "preview_token": preview.json()["preview_token"]},
    )
    assert confirm.status_code == 409


def test_recipe_change_with_identical_macros_invalidates_preference_preview(client) -> None:
    headers = _auth(client, 52_326)
    _add_target(52_326)
    preferred = _store_food("Предпочитаемый продукт")
    replacement = _store_food("Другой продукт с теми же КБЖУ")
    recipe = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Рецепт для проверки состава",
            "ingredients": [{"food_id": preferred, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert recipe.status_code == 201
    recipe_id = recipe.json()["id"]
    payload = {
        "diary_date": _today().isoformat(),
        "meal_type": "lunch",
        "items": [{"recipe_id": recipe_id, "amount": "100", "amount_unit": "g"}],
        "constraints": {"preferred_food_ids": [preferred]},
    }
    preview = client.post(
        "/api/v1/nutrition/diary/suggestions/preview", headers=headers, json=payload
    )
    assert preview.status_code == 200
    assert "есть указанный" in preview.json()["preference_message"]
    changed = client.patch(
        f"/api/v1/nutrition/recipes/{recipe_id}",
        headers=headers,
        json={"ingredients": [{"food_id": replacement, "amount": "100", "amount_unit": "g"}]},
    )
    assert changed.status_code == 200, changed.text
    updated = client.post(
        "/api/v1/nutrition/diary/suggestions/preview", headers=headers, json=payload
    )
    assert updated.status_code == 200
    assert updated.json()["addition"] == preview.json()["addition"]
    assert "нет указанных" in updated.json()["preference_message"]
    stale = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "recipe-preference-stale-52326"},
        json={**payload, "preview_token": preview.json()["preview_token"]},
    )
    assert stale.status_code == 409


def test_suggestion_commit_rejects_another_users_private_food_and_rolls_back(client) -> None:
    _auth(client, 52_310)
    other_headers = _auth(client, 52_311)
    _add_target(52_311)
    with get_session_context() as db:
        owner_id = db.query(User.id).filter(User.telegram_user_id == 52_310).scalar()
    assert owner_id is not None
    private_food = _store_food("Личный продукт", owner_id=owner_id)
    public_food = _store_food("Доступный продукт")
    selected_date = _today().isoformat()
    payload = {
        "diary_date": selected_date,
        "meal_type": "snacks",
        "items": [
            {"food_id": public_food, "amount": "100", "amount_unit": "g"},
            {"food_id": private_food, "amount": "100", "amount_unit": "g"},
        ],
    }
    visible_payload = {**payload, "items": payload["items"][:1]}
    payload["preview_token"] = _with_preview(client, other_headers, visible_payload)[
        "preview_token"
    ]
    denied = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**other_headers, "Idempotency-Key": "suggestion-private-52311"},
        json=payload,
    )
    assert denied.status_code == 404
    day = client.get(
        "/api/v1/nutrition/diary", headers=other_headers, params={"diary_date": selected_date}
    ).json()
    assert sum(len(meal["entries"]) for meal in day["meals"]) == 0
    with get_session_context() as db:
        other_id = db.query(User.id).filter(User.telegram_user_id == 52_311).scalar()
        assert not db.query(FoodDiaryBatchOperation).filter_by(user_id=other_id).count()


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_suggestion_confirmations_are_idempotent(client) -> None:
    headers = _auth(client, 52_306)
    _add_target(52_306)
    food_id = _store_food("Продукт для конкурентной проверки")
    selected_date = _today().isoformat()
    payload = {
        "diary_date": selected_date,
        "meal_type": "snacks",
        "items": [{"food_id": food_id, "amount": "50", "amount_unit": "g"}],
    }
    payload = _with_preview(client, headers, payload)
    barrier = Barrier(2)

    def confirm():
        barrier.wait(timeout=5)
        return client.post(
            "/api/v1/nutrition/diary/suggestions/commit",
            headers={**headers, "Idempotency-Key": "suggestion-concurrent-52306"},
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.submit(confirm), executor.submit(confirm)
        responses = [first.result(), second.result()]
    assert [response.status_code for response in responses] == [201, 201]
    assert sorted(response.json()["replayed"] for response in responses) == [False, True]
    assert responses[0].json()["entries"][0]["id"] == responses[1].json()["entries"][0]["id"]
    day = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
    ).json()
    assert sum(len(meal["entries"]) for meal in day["meals"]) == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_suggestion_confirmation_and_past_completion_are_serialized(client) -> None:
    headers = _auth(client, 52_307)
    food_id = _store_food("Продукт для закрытия дня")
    selected_date = (_today() - timedelta(days=1)).isoformat()
    _add_target(52_307, date.fromisoformat(selected_date))
    entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": food_id,
            "diary_date": selected_date,
            "meal_type": "breakfast",
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert entry.status_code == 201
    payload = _with_preview(
        client,
        headers,
        {
            "diary_date": selected_date,
            "meal_type": "snacks",
            "items": [{"food_id": food_id, "amount": "50", "amount_unit": "g"}],
        },
    )
    barrier = Barrier(2)

    def complete():
        barrier.wait(timeout=5)
        return client.put(
            "/api/v1/nutrition/diary/status",
            headers=headers,
            json={"diary_date": selected_date, "status": "complete"},
        )

    def confirm():
        barrier.wait(timeout=5)
        return client.post(
            "/api/v1/nutrition/diary/suggestions/commit",
            headers={**headers, "Idempotency-Key": "suggestion-completion-52307"},
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        completion, confirmation = executor.submit(complete), executor.submit(confirm)
        completion, confirmation = completion.result(), confirmation.result()
    assert completion.status_code == 200
    assert confirmation.status_code in {201, 409}
    day = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
    ).json()
    assert day == completion.json()
    count = sum(len(meal["entries"]) for meal in day["meals"])
    assert count == (2 if confirmation.status_code == 201 else 1)


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_different_keys_cannot_confirm_the_same_preview_twice(client) -> None:
    headers = _auth(client, 52_319)
    _add_target(52_319)
    food_id = _store_food("Продукт для проверки устаревшего просмотра")
    selected_date = _today().isoformat()
    payload = _with_preview(
        client,
        headers,
        {
            "diary_date": selected_date,
            "meal_type": "snacks",
            "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    barrier = Barrier(2)

    def confirm(key: str):
        barrier.wait(timeout=5)
        return client.post(
            "/api/v1/nutrition/diary/suggestions/commit",
            headers={**headers, "Idempotency-Key": key},
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(confirm, "preview-race-first-52319")
        second = executor.submit(confirm, "preview-race-second-52319")
        assert sorted([first.result().status_code, second.result().status_code]) == [201, 409]
    day = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
    ).json()
    assert sum(len(meal["entries"]) for meal in day["meals"]) == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_food_change_invalidates_preview_before_confirmation(
    client, monkeypatch
) -> None:
    headers = _auth(client, 52_324)
    _add_target(52_324)
    food_id = _store_food("Продукт для конкурентного изменения")
    selected_date = _today().isoformat()
    payload = _with_preview(
        client,
        headers,
        {
            "diary_date": selected_date,
            "meal_type": "snacks",
            "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    entered = Event()
    original = suggestions_service.lock_suggestion_sources

    def signal_then_lock(*args, **kwargs):
        entered.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(suggestions_service, "lock_suggestion_sources", signal_then_lock)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with get_session_context() as db:
            food = db.query(Food).filter_by(id=food_id).with_for_update().one()
            food.energy_kcal_per_100g = Decimal("130")
            db.flush()
            future = executor.submit(
                client.post,
                "/api/v1/nutrition/diary/suggestions/commit",
                headers={**headers, "Idempotency-Key": "food-race-preview-52324"},
                json=payload,
            )
            assert entered.wait(timeout=5)
        response = future.result(timeout=10)
    assert response.status_code == 409, response.text
    day = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": selected_date}
    ).json()
    assert sum(len(meal["entries"]) for meal in day["meals"]) == 0


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_recipe_ingredient_change_invalidates_preview(client) -> None:
    headers = _auth(client, 52_327)
    _add_target(52_327)
    first = _store_food("Исходный продукт рецепта")
    second = _store_food("Другой продукт рецепта")
    recipe = client.post(
        "/api/v1/nutrition/recipes",
        headers=headers,
        json={
            "name": "Конкурентный рецепт",
            "ingredients": [{"food_id": first, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert recipe.status_code == 201
    recipe_id = recipe.json()["id"]
    payload = _with_preview(
        client,
        headers,
        {
            "diary_date": _today().isoformat(),
            "meal_type": "lunch",
            "items": [{"recipe_id": recipe_id, "amount": "100", "amount_unit": "g"}],
            "constraints": {"preferred_food_ids": [first]},
        },
    )
    locking_ingredient = Event()

    def observe_lock(_conn, _cursor, statement, _parameters, _context, _many):
        if "recipe_ingredients" in statement and "FOR SHARE" in statement.upper():
            locking_ingredient.set()

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            with get_session_context() as db:
                ingredient = (
                    db.query(RecipeIngredient)
                    .filter_by(recipe_id=recipe_id)
                    .with_for_update()
                    .one()
                )
                ingredient.food_id = second
                db.flush()
                event.listen(engine, "before_cursor_execute", observe_lock)
                future = executor.submit(
                    client.post,
                    "/api/v1/nutrition/diary/suggestions/commit",
                    headers={**headers, "Idempotency-Key": "recipe-race-preview-52327"},
                    json=payload,
                )
                assert locking_ingredient.wait(timeout=10)
            response = future.result(timeout=10)
    finally:
        if event.contains(engine, "before_cursor_execute", observe_lock):
            event.remove(engine, "before_cursor_execute", observe_lock)
    assert response.status_code == 409, response.text


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_shared_food_does_not_block_confirmations_from_different_users(client, monkeypatch) -> None:
    first_headers = _auth(client, 52_328)
    second_headers = _auth(client, 52_329)
    _add_target(52_328)
    _add_target(52_329)
    food_id = _store_food("Общий продукт для двух пользователей")
    selected_date = _today().isoformat()
    payload = {
        "diary_date": selected_date,
        "meal_type": "snacks",
        "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
    }
    first_payload = _with_preview(client, first_headers, payload)
    second_payload = _with_preview(client, second_headers, payload)
    both_locked = Barrier(2)
    original = suggestions_service.preview_nutrition_suggestion

    def synchronize_preview(*args, **kwargs):
        both_locked.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(suggestions_service, "preview_nutrition_suggestion", synchronize_preview)

    def confirm(headers: dict[str, str], request: dict):
        return client.post(
            "/api/v1/nutrition/diary/suggestions/commit",
            headers={**headers, "Idempotency-Key": "shared-food-race-52328"},
            json=request,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_result = executor.submit(confirm, first_headers, first_payload)
        second_result = executor.submit(confirm, second_headers, second_payload)
        responses = [first_result.result(timeout=15), second_result.result(timeout=15)]
    assert [response.status_code for response in responses] == [201, 201]
    assert all(response.json()["replayed"] is False for response in responses)
