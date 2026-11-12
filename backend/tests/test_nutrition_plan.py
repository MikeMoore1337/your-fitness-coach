from __future__ import annotations

import importlib.util
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest
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
from fitminiapp_api.db.session import SessionLocal, engine, get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryBatchOperation, FoodDiaryEntry
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.nutrition_power import NutritionMealTemplate
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition import NutritionDateOverrideSave
from fitminiapp_api.schemas.nutrition_plan import NutritionPlanItemUpdate
from fitminiapp_api.services.nutrition import save_nutrition_date_override
from fitminiapp_api.services.nutrition_plan import update_plan_item


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


def test_target_and_plan_changes_can_roll_back_together(client) -> None:
    headers = _auth(client, 74954)
    food_id = _store_food("Продукт для плана")
    plan_date = _today() + timedelta(days=1)
    added = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "atomic-plan-74954"},
        params={"plan_date": plan_date.isoformat(), "meal_type": "lunch", "expected_revision": 0},
        json={"food_id": food_id, "amount": "100", "amount_unit": "g"},
    )
    assert added.status_code == 201, added.text
    item_id = _items(added.json())[0]["id"]

    with SessionLocal() as db:
        user = db.query(User).filter_by(telegram_user_id=74954).one()
        save_nutrition_date_override(
            db,
            user,
            NutritionDateOverrideSave(
                effective_from=plan_date,
                calories=2000,
                protein_g=150,
                fat_g=70,
                carbs_g=180,
            ),
            "atomic-target-74954",
            commit=False,
        )
        updated = update_plan_item(
            db,
            user,
            item_id,
            NutritionPlanItemUpdate(amount=Decimal("150"), expected_revision=1),
            commit=False,
        )
        assert updated.revision == 2
        db.rollback()

    day = client.get(
        "/api/v1/nutrition/plans/day", headers=headers, params={"plan_date": plan_date.isoformat()}
    )
    assert day.status_code == 200
    assert day.json()["revision"] == 1
    assert Decimal(str(_items(day.json())[0]["amount"])) == Decimal("100")
    target = client.get(
        "/api/v1/nutrition/targets/for-date",
        headers=headers,
        params={"target_date": plan_date.isoformat()},
    )
    assert target.status_code == 200
    assert target.json()["target"] is None


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


def test_plan_suggestions_do_not_use_diary_remaining_when_plan_is_incomplete(client) -> None:
    headers = _auth(client, 74_605)
    _add_target(74_605)
    diary_food = _store_food("Продукт из дневника")
    planned_food = _store_food("Недоступный продукт плана")
    selected_date = _today().isoformat()

    diary = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": diary_food,
            "diary_date": selected_date,
            "meal_type": "breakfast",
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert diary.status_code == 201
    plan = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**headers, "Idempotency-Key": "plan-incomplete-74605"},
        params={"plan_date": selected_date, "meal_type": "lunch", "expected_revision": 0},
        json={"food_id": planned_food, "amount": "100", "amount_unit": "g"},
    )
    assert plan.status_code == 201, plan.text
    with get_session_context() as db:
        db.get(Food, planned_food).status = "disabled"

    day = client.get(
        "/api/v1/nutrition/plans/day", headers=headers, params={"plan_date": selected_date}
    )
    assert day.status_code == 200
    assert day.json()["nutrition_complete"] is False
    assert day.json()["remaining"] is None
    suggestions = client.get(
        "/api/v1/nutrition/plans/suggestions", headers=headers, params={"plan_date": selected_date}
    )
    assert suggestions.status_code == 200
    assert suggestions.json()["targets"] == day.json()["targets"]
    assert suggestions.json()["remaining"] is None
    assert suggestions.json()["candidates"] == []
    assert any("доступность продуктов" in text for text in suggestions.json()["limitations"])
    assert not any("Настройте цель" in text for text in suggestions.json()["limitations"])


def test_plan_suggestions_support_a_future_date_without_allowing_future_diary(client) -> None:
    headers = _auth(client, 74_607)
    _add_target(74_607)
    food_id = _store_food("Продукт для будущего плана")
    today = _today()
    entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": food_id,
            "diary_date": today.isoformat(),
            "meal_type": "breakfast",
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert entry.status_code == 201
    future = (today + timedelta(days=1)).isoformat()
    day = client.get("/api/v1/nutrition/plans/day", headers=headers, params={"plan_date": future})
    assert day.status_code == 200
    suggestions = client.get(
        "/api/v1/nutrition/plans/suggestions", headers=headers, params={"plan_date": future}
    )
    assert suggestions.status_code == 200, suggestions.text
    assert suggestions.json()["diary_date"] == future
    assert suggestions.json()["remaining"] == day.json()["remaining"]
    assert any(
        item["candidate_id"] == f"food:{food_id}" for item in suggestions.json()["candidates"]
    )
    future_diary = client.get(
        "/api/v1/nutrition/diary", headers=headers, params={"diary_date": future}
    )
    assert future_diary.status_code == 422


def test_plan_suggestion_confidence_includes_partial_diary_entries(client) -> None:
    headers = _auth(client, 74_608)
    _add_target(74_608)
    food_id = _store_food("Продукт для полного плана")
    selected_date = _today().isoformat()
    for payload in (
        {"food_id": food_id, "amount": "100", "amount_unit": "g"},
        {"quick_add": {"energy_kcal": "100"}, "amount": "1", "amount_unit": "serving"},
    ):
        entry = client.post(
            "/api/v1/nutrition/diary/entries",
            headers=headers,
            json={**payload, "diary_date": selected_date, "meal_type": "breakfast"},
        )
        assert entry.status_code == 201, entry.text
    diary = client.get(
        "/api/v1/nutrition/diary/suggestions",
        headers=headers,
        params={"diary_date": selected_date},
    )
    plan = client.get(
        "/api/v1/nutrition/plans/suggestions",
        headers=headers,
        params={"plan_date": selected_date},
    )
    assert diary.status_code == plan.status_code == 200
    assert diary.json()["remaining_confidence"] == "partial"
    assert plan.json()["remaining_confidence"] == "partial"
    assert plan.json()["remaining"]["protein_g"] is None
    assert Decimal(plan.json()["remaining"]["energy_kcal"]) == 1780


def test_plan_suggestion_retry_does_not_change_completed_past_day(client, monkeypatch) -> None:
    headers = _auth(client, 74_606)
    _add_target(74_606)
    food_id = _store_food("План для завершённого дня")
    selected_date = _today()
    diary = client.post(
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
    assert diary.status_code == 201
    suggestions = client.get(
        "/api/v1/nutrition/plans/suggestions",
        headers=headers,
        params={"plan_date": selected_date.isoformat()},
    )
    assert suggestions.status_code == 200
    candidate = next(
        item
        for item in suggestions.json()["candidates"]
        if item["candidate_id"] == f"food:{food_id}"
    )
    payload = {
        "plan_date": selected_date.isoformat(),
        "meal_type": "lunch",
        "candidate_id": candidate["candidate_id"],
        "items": [{"position": 0, "food_id": food_id, "amount": "100", "amount_unit": "g"}],
        "expected_revision": 0,
    }
    exact_preview = client.post(
        "/api/v1/nutrition/plans/suggestions/preview", headers=headers, json=payload
    )
    assert exact_preview.status_code == 200, exact_preview.text
    payload["preview_token"] = exact_preview.json()["preview_token"]
    first = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "plan-past-74606"},
        json=payload,
    )
    assert first.status_code == 201, first.text
    completed = client.put(
        "/api/v1/nutrition/diary/status",
        headers=headers,
        json={"diary_date": selected_date.isoformat(), "status": "complete"},
    )
    assert completed.status_code == 200
    monkeypatch.setattr(
        timezone_module, "today_in_timezone", lambda _timezone: selected_date + timedelta(days=1)
    )

    retry = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "plan-past-74606"},
        json=payload,
    )
    assert retry.status_code == 201
    assert retry.json()["replayed"] is True
    changed = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "plan-past-74606-new"},
        json={**payload, "expected_revision": 1},
    )
    assert changed.status_code == 409
    day = client.get(
        "/api/v1/nutrition/plans/day",
        headers=headers,
        params={"plan_date": selected_date.isoformat()},
    )
    assert day.status_code == 200
    assert day.json()["revision"] == 1
    assert len(_items(day.json())) == 1


def test_plan_preview_limits_staleness_and_retry_on_future_date(client) -> None:
    headers = _auth(client, 74_609)
    other_headers = _auth(client, 74_610)
    _add_target(74_609)
    _add_target(74_610)
    food_id = _store_food("Продукт для предварительного расчёта плана")
    today = _today()
    entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "diary_date": today.isoformat(),
            "meal_type": "breakfast",
            "food_id": food_id,
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert entry.status_code == 201
    future = (today + timedelta(days=1)).isoformat()
    payload = {
        "plan_date": future,
        "meal_type": "lunch",
        "candidate_id": f"food:{food_id}",
        "items": [{"position": 0, "food_id": food_id, "amount": "150", "amount_unit": "g"}],
        "expected_revision": 0,
        "constraints": {"max_fat_g": "5"},
    }
    no_preview = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "plan-preview-required-74609"},
        json=payload,
    )
    assert no_preview.status_code == 409
    preview = client.post(
        "/api/v1/nutrition/plans/suggestions/preview", headers=headers, json=payload
    )
    assert preview.status_code == 200, preview.text
    result = preview.json()
    assert Decimal(result["before"]["energy_kcal"]) == 0
    assert Decimal(result["addition"]["energy_kcal"]) == 180
    assert Decimal(result["after"]["energy_kcal"]) == 180
    assert Decimal(result["diary"]["energy_kcal"]) == 0
    assert result["constraint_status"] == "violated"
    blocked = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "plan-preview-limit-74609"},
        json={**payload, "preview_token": result["preview_token"]},
    )
    assert blocked.status_code == 409
    assert (
        _items(
            client.get(
                "/api/v1/nutrition/plans/day", headers=headers, params={"plan_date": future}
            ).json()
        )
        == []
    )
    payload["constraints"] = {"max_fat_g": "6"}
    preview = client.post(
        "/api/v1/nutrition/plans/suggestions/preview", headers=headers, json=payload
    )
    assert preview.status_code == 200, preview.text
    result = preview.json()
    assert result["constraint_status"] == "satisfied"
    confirmed_payload = {**payload, "preview_token": result["preview_token"]}
    favorite = client.put(f"/api/v1/nutrition/foods/{food_id}/favorite", headers=other_headers)
    assert favorite.status_code == 200
    foreign_candidates = client.get(
        "/api/v1/nutrition/plans/suggestions",
        headers=other_headers,
        params={"plan_date": future},
    )
    assert any(
        item["candidate_id"] == payload["candidate_id"]
        for item in foreign_candidates.json()["candidates"]
    )
    foreign = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**other_headers, "Idempotency-Key": "plan-preview-foreign-74610"},
        json=confirmed_payload,
    )
    assert foreign.status_code == 409
    confirmed = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "plan-preview-confirm-74609"},
        json=confirmed_payload,
    )
    assert confirmed.status_code == 201, confirmed.text
    assert confirmed.json()["planned"] == result["after"]
    replay = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "plan-preview-confirm-74609"},
        json=confirmed_payload,
    )
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True
    stale = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "plan-preview-stale-74609"},
        json=confirmed_payload,
    )
    assert stale.status_code == 409
    day = client.get("/api/v1/nutrition/plans/day", headers=headers, params={"plan_date": future})
    assert len(_items(day.json())) == 1


def test_plan_preview_rejects_changed_template_even_if_nutrients_match(client) -> None:
    headers = _auth(client, 74_612)
    _add_target(74_612)
    food_id = _store_food("Продукт шаблона")
    template = client.post(
        "/api/v1/nutrition/templates",
        headers=headers,
        json={
            "name": "Исходный шаблон",
            "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert template.status_code == 201
    template_id = template.json()["id"]
    selected_date = _today().isoformat()
    payload = {
        "plan_date": selected_date,
        "meal_type": "lunch",
        "candidate_id": f"template:{template_id}",
        "items": [{"position": 0, "food_id": food_id, "amount": "100", "amount_unit": "g"}],
        "expected_revision": 0,
    }
    preview = client.post(
        "/api/v1/nutrition/plans/suggestions/preview", headers=headers, json=payload
    )
    assert preview.status_code == 200, preview.text
    changed = client.patch(
        f"/api/v1/nutrition/templates/{template_id}",
        headers=headers,
        json={"name": "Переименованный шаблон"},
    )
    assert changed.status_code == 200
    stale = client.post(
        "/api/v1/nutrition/plans/fill",
        headers={**headers, "Idempotency-Key": "stale-template-preview-74612"},
        json={**payload, "preview_token": preview.json()["preview_token"]},
    )
    assert stale.status_code == 409
    day = client.get(
        "/api/v1/nutrition/plans/day", headers=headers, params={"plan_date": selected_date}
    )
    assert _items(day.json()) == []


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_plan_confirmation_fails_closed_while_template_is_being_edited(client) -> None:
    headers = _auth(client, 74_613)
    _add_target(74_613)
    food_id = _store_food("Продукт для конкурентного шаблона")
    template = client.post(
        "/api/v1/nutrition/templates",
        headers=headers,
        json={
            "name": "Исходный шаблон для плана",
            "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert template.status_code == 201
    template_id = template.json()["id"]
    selected_date = _today().isoformat()
    payload = {
        "plan_date": selected_date,
        "meal_type": "lunch",
        "candidate_id": f"template:{template_id}",
        "items": [{"position": 0, "food_id": food_id, "amount": "100", "amount_unit": "g"}],
        "expected_revision": 0,
    }
    preview = client.post(
        "/api/v1/nutrition/plans/suggestions/preview", headers=headers, json=payload
    )
    assert preview.status_code == 200, preview.text
    with ThreadPoolExecutor(max_workers=1) as executor, get_session_context() as db:
        locked = db.query(NutritionMealTemplate).filter_by(id=template_id).with_for_update().one()
        locked.name = "Изменяемый шаблон"
        db.flush()
        future = executor.submit(
            client.post,
            "/api/v1/nutrition/plans/fill",
            headers={**headers, "Idempotency-Key": "template-race-74613"},
            json={**payload, "preview_token": preview.json()["preview_token"]},
        )
        response = future.result(timeout=10)
        assert response.status_code == 409, response.text
    day = client.get(
        "/api/v1/nutrition/plans/day", headers=headers, params={"plan_date": selected_date}
    )
    assert _items(day.json()) == []


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
@pytest.mark.parametrize("same_key", [True, False])
def test_plan_preview_concurrent_confirmations(client, same_key: bool) -> None:
    headers = _auth(client, 74_611)
    _add_target(74_611)
    food_id = _store_food("Продукт для конкурентного плана")
    selected_date = _today().isoformat()
    source = client.post(
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
    assert source.status_code == 201
    payload = {
        "plan_date": selected_date,
        "meal_type": "lunch",
        "candidate_id": f"food:{food_id}",
        "items": [{"position": 0, "food_id": food_id, "amount": "100", "amount_unit": "g"}],
        "expected_revision": 0,
    }
    preview = client.post(
        "/api/v1/nutrition/plans/suggestions/preview", headers=headers, json=payload
    )
    assert preview.status_code == 200, preview.text
    payload["preview_token"] = preview.json()["preview_token"]
    barrier = Barrier(2)

    def confirm(key: str):
        barrier.wait(timeout=5)
        return client.post(
            "/api/v1/nutrition/plans/fill",
            headers={**headers, "Idempotency-Key": key},
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(confirm, "plan-race-first-74611")
        second = executor.submit(
            confirm, "plan-race-first-74611" if same_key else "plan-race-second-74611"
        )
        responses = [first.result(), second.result()]
    assert sorted(response.status_code for response in responses) == (
        [201, 201] if same_key else [201, 409]
    )
    if same_key:
        assert sorted(response.json()["replayed"] for response in responses) == [False, True]
    day = client.get(
        "/api/v1/nutrition/plans/day", headers=headers, params={"plan_date": selected_date}
    )
    assert len(_items(day.json())) == 1


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
    exact_preview = client.post(
        "/api/v1/nutrition/plans/suggestions/preview", headers=headers, json=fill_payload
    )
    assert exact_preview.status_code == 200, exact_preview.text
    fill_payload["preview_token"] = exact_preview.json()["preview_token"]
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

    second_fill_payload = {
        **{key: value for key, value in fill_payload.items() if key != "preview_token"},
        "expected_revision": 1,
    }
    second_preview = client.post(
        "/api/v1/nutrition/plans/suggestions/preview", headers=headers, json=second_fill_payload
    )
    assert second_preview.status_code == 200, second_preview.text
    second_fill_payload["preview_token"] = second_preview.json()["preview_token"]
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
        migrations_dir / "0122_plan_fill_kind.py",
        migrations_dir / "0123_diary_planned_item_kind.py",
        migrations_dir / "0124_plan_item_lifecycle.py",
        migrations_dir / "0125_grocery_lists.py",
        migrations_dir / "0126_nutrition_plan_source_constraint.py",
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
            "grocery_lists",
            "grocery_list_items",
            "grocery_list_item_sources",
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
            "grocery_lists",
            "grocery_list_items",
            "grocery_list_item_sources",
        } & set(schema.get_table_names())
    engine.dispose()
