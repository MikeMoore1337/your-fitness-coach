from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier

import pytest

from fitminiapp_api.core import timezone as timezone_module
from fitminiapp_api.db.session import engine, get_session_context
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
    owner_id: int | None = None,
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
    payload = {
        "diary_date": selected_date,
        "meal_type": "snacks",
        "items": [{"food_id": food_id, "amount": "50", "amount_unit": "g"}],
    }
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
    confirmed = client.post(
        "/api/v1/nutrition/diary/suggestions/commit",
        headers={**headers, "Idempotency-Key": "suggestion-report-52309"},
        json={
            "diary_date": selected_date,
            "meal_type": "snacks",
            "items": [{"food_id": food_id, "amount": "150", "amount_unit": "g"}],
        },
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


def test_suggestion_commit_rejects_another_users_private_food_and_rolls_back(client) -> None:
    _auth(client, 52_310)
    other_headers = _auth(client, 52_311)
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
    food_id = _store_food("Продукт для конкурентной проверки")
    selected_date = _today().isoformat()
    payload = {
        "diary_date": selected_date,
        "meal_type": "snacks",
        "items": [{"food_id": food_id, "amount": "50", "amount_unit": "g"}],
    }
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
            json={
                "diary_date": selected_date,
                "meal_type": "snacks",
                "items": [{"food_id": food_id, "amount": "50", "amount_unit": "g"}],
            },
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
