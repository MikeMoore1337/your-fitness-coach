from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from test_food_diary import _active_food
from test_nutrition_import_fatsecret_csv import DETAIL_HEADER, NUTRIENTS, SUMMARY_HEADER, _validated
from test_training_analytics import _auth

from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.nutrition_power import NutritionMealTemplate
from fitminiapp_api.models.user import User
from fitminiapp_api.nutrition_label.parser import build_draft_from_ocr
from fitminiapp_api.schemas.nutrition_import import ImportFoodRow, OriginalTotal
from fitminiapp_api.schemas.nutrition_import_engine import (
    RecurringImportMeals,
    RecurringMealConfirmRequest,
    RecurringMealReviewRequest,
)
from fitminiapp_api.schemas.nutrition_power import NutritionMealTemplateCreate
from fitminiapp_api.services import nutrition_import_meals
from fitminiapp_api.services.nutrition_import_drafts import create_nutrition_import_draft
from fitminiapp_api.services.nutrition_power import (
    NutritionPowerConflictError,
    create_meal_template,
)


def _row(day, number, name, quantity="100", unit="g"):
    return {
        "coordinates": {"section": "report_details", "section_kind": "detail", "row": number},
        "diary_date": day,
        "meal_type": "breakfast",
        "food": {"name": name, "kind": "unknown"},
        "quantity": quantity,
        "amount_unit": unit,
        "nutrition": {"basis": None, "facts": {}},
    }


def _preview(monkeypatch, rows, ids, totals=(), visible_ids=None):
    draft = SimpleNamespace(
        provider="fatsecret",
        document={"rows": rows, "original_totals": list(totals)},
        catalog_receipt={
            "rows": [
                {"index": index, "food_id": food_id, "outcome": "reuse"}
                for index, food_id in enumerate(ids)
                if food_id is not None
            ]
        },
    )
    monkeypatch.setattr(nutrition_import_meals, "get_nutrition_import_draft", lambda *a, **k: draft)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        (food_id,) for food_id in (visible_ids if visible_ids is not None else set(ids)) if food_id
    ]
    return RecurringImportMeals.model_validate(
        nutrition_import_meals.recurring_import_meals(db, SimpleNamespace(id=1), "draft")
    )


def test_repeated_composition_counts_days_and_preserves_portions_and_unknowns(monkeypatch):
    rows = [
        _row("2026-10-01", 1, "A", "100"),
        _row("2026-10-01", 2, "B", None, None),
        _row("2026-10-02", 3, "A", "125"),
        _row("2026-10-02", 4, "B", None, None),
    ]
    totals = [
        {
            "scope": "unknown",
            "coordinates": rows[0]["coordinates"],
            "facts": {"protein_g": {"value": None, "unit": None, "evidence": "absent"}},
        }
    ]
    result = _preview(monkeypatch, rows, [1, 2, 1, 2], totals)
    assert result.observed_days == 2
    assert len(result.items) == 1
    assert result.items[0].repeat_days == 2
    first, second = result.items[0].occurrences
    assert str(first.items[0].source.quantity) == "100"
    assert str(second.items[0].source.quantity) == "125"
    assert first.items[1].source.quantity is None
    assert first.items[0].original_total.facts.protein_g.value is None


def test_one_day_duplicates_and_different_compositions_do_not_repeat(monkeypatch):
    rows = [
        _row("2026-10-01", 1, "A"),
        _row("2026-10-01", 2, "A"),
        _row("2026-10-02", 3, "A"),
        _row("2026-10-03", 4, "A"),
    ]
    result = _preview(monkeypatch, rows, [1, 1, 2, 3])
    assert result.observed_days == 3
    assert result.items == []


def test_unresolved_row_excludes_whole_meal_and_partial_period_counts_observed_days(monkeypatch):
    rows = [_row(f"2026-10-{day:02d}", day, "A") for day in range(1, 9)]
    rows.append(_row("2026-10-01", 9, "unknown"))
    result = _preview(monkeypatch, rows, [1] * 8 + [None])
    assert result.observed_days == 8
    assert result.items[0].repeat_days == 7
    assert all(occ.date.isoformat() != "2026-10-01" for occ in result.items[0].occurrences)


def test_unknown_meal_context_does_not_produce_incomplete_proposal(monkeypatch):
    rows = [_row("2026-10-01", 1, "A"), _row("2026-10-02", 2, "A"), _row(None, 3, "unknown")]
    assert _preview(monkeypatch, rows, [1, 1, None]).items == []


def test_unavailable_food_excludes_the_entire_meal(monkeypatch):
    rows = [_row("2026-10-01", 1, "A"), _row("2026-10-02", 2, "A")]
    assert _preview(monkeypatch, rows, [1, 1], visible_ids=set()).items == []


def test_preview_api_is_owner_only_and_does_not_write_diary_or_templates(client):
    owner = _auth(client, 984_886)
    other = _auth(client, 984_887)
    source, document = _validated(
        [
            ["# Period Summary"],
            ["Период: 01.02.2024–29.02.2024"],
            SUMMARY_HEADER,
            ["# Report Details"],
            DETAIL_HEADER,
            ["Дата: 01.02.2024"],
            ["Завтрак"],
            ["Продукт", *NUTRIENTS],
            ["100 г"],
            ["Дата: 02.02.2024"],
            ["Завтрак"],
            ["Продукт", *NUTRIENTS],
            ["120 г"],
        ]
    )
    with get_session_context() as db:
        user = db.query(User).filter_by(telegram_user_id=984_886).one()
        draft = create_nutrition_import_draft(
            db,
            user,
            document=document,
            source=source,
            filename="synthetic.csv",
            content_type="text/csv",
            delimiter=",",
            parser_version="fatsecret-csv-v1",
            upload_key="issue-886-upload",
            adapter_id="fatsecret-csv-v1",
        )
        draft_id = draft.id
        user_id = user.id
        food = _active_food()
        db.add(food)
        db.flush()
        draft.catalog_receipt = {
            "rows": [
                {"index": 0, "outcome": "reuse", "food_id": food.id},
                {"index": 1, "outcome": "reuse", "food_id": food.id},
            ]
        }
        db.commit()
    url = f"/api/v1/nutrition/imports/{draft_id}/recurring-meals"
    assert client.get(url, headers=other).status_code == 404
    response = client.get(url, headers=owner)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["items"][0]["repeat_days"] == 2
    assert response.json()["items"][0]["occurrences"][0]["items"][0]["original_detail_cells"]
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0
        assert db.query(NutritionMealTemplate).filter_by(owner_user_id=user_id).count() == 0


def test_comparison_distinguishes_equal_different_unknown_and_changed_portions(monkeypatch):
    source = ImportFoodRow.model_validate(_row("2026-10-01", 1, "A"))
    total = OriginalTotal.model_validate(
        {
            "scope": "entry",
            "coordinates": source.coordinates.model_dump(),
            "facts": {
                "energy_kcal": {"value": "100", "unit": "kcal", "evidence": "read"},
                "protein_g": {"value": "4", "unit": "g", "evidence": "read"},
                "fat_g": {"value": None, "unit": None, "evidence": "absent"},
            },
        }
    )
    item = {
        "source_index": 0,
        "food_id": 1,
        "source": source,
        "original_total": total,
        "original_detail_cells": [],
    }
    monkeypatch.setattr(
        nutrition_import_meals,
        "recurring_import_meals",
        lambda *a: {
            "items": [
                {
                    "meal_type": "breakfast",
                    "occurrences": [{"date": source.diary_date, "items": [item]}],
                }
            ]
        },
    )
    monkeypatch.setattr(nutrition_import_meals, "get_visible_food", lambda *a: object())
    monkeypatch.setattr(
        nutrition_import_meals,
        "calculate_food_amount",
        lambda *a: SimpleNamespace(
            energy_kcal=Decimal("100"), protein_g=Decimal("5"), fat_g=Decimal("2"), carbs_g=None
        ),
    )
    request = RecurringMealReviewRequest.model_validate(
        {
            "meal_type": "breakfast",
            "date": "2026-10-01",
            "name": "Пример",
            "items": [{"source_index": 0, "food_id": 1, "amount": "100", "amount_unit": "g"}],
        }
    )
    result = nutrition_import_meals.review_recurring_meal(None, None, "draft", request)
    assert result.items[0].comparison == {
        "energy_kcal": "equal",
        "protein_g": "different",
        "fat_g": "unknown",
        "carbohydrate_g": "unknown",
    }
    total.facts.protein_g.unit = "mg"
    wrong_unit = nutrition_import_meals.review_recurring_meal(None, None, "draft", request)
    assert wrong_unit.items[0].comparison["protein_g"] == "unknown"
    total.facts.protein_g.unit = "g"
    request.items[0].amount = Decimal("120")
    changed = nutrition_import_meals.review_recurring_meal(None, None, "draft", request)
    assert set(changed.items[0].comparison.values()) == {"unknown"}
    assert changed.preview_signature != result.preview_signature


def test_confirmation_reuses_manual_template_and_does_not_change_diary(client):
    owner = _auth(client, 984_888)
    other = _auth(client, 984_889)
    source, document = _validated(
        [
            ["# Period Summary"],
            ["Период: 01.02.2024–29.02.2024"],
            SUMMARY_HEADER,
            ["# Report Details"],
            DETAIL_HEADER,
            ["Дата: 01.02.2024"],
            ["Завтрак"],
            ["Продукт", *NUTRIENTS],
            ["100 г"],
            ["Дата: 02.02.2024"],
            ["Завтрак"],
            ["Продукт", *NUTRIENTS],
            ["120 г"],
        ]
    )
    with get_session_context() as db:
        user = db.query(User).filter_by(telegram_user_id=984_888).one()
        draft = create_nutrition_import_draft(
            db,
            user,
            document=document,
            source=source,
            filename="synthetic.csv",
            content_type="text/csv",
            delimiter=",",
            parser_version="fatsecret-csv-v1",
            upload_key="confirm-issue-886",
            adapter_id="fatsecret-csv-v1",
        )
        food = _active_food()
        db.add(food)
        db.flush()
        food_id, draft_id, user_id = food.id, draft.id, user.id
        draft.catalog_receipt = {
            "rows": [{"index": i, "outcome": "reuse", "food_id": food_id} for i in range(2)]
        }
        db.commit()
    base = f"/api/v1/nutrition/imports/{draft_id}/recurring-meals"
    selection = {
        "meal_type": "breakfast",
        "date": "2024-02-01",
        "name": "Из импорта",
        "items": [{"source_index": 0, "food_id": food_id, "amount": "100", "amount_unit": "g"}],
    }
    assert client.post(f"{base}/review", json=selection, headers=other).status_code == 404
    review = client.post(f"{base}/review", json=selection, headers=owner)
    assert review.status_code == 200, review.text
    assert set(review.json()["items"][0]["comparison"].values()) == {"unknown"}
    confirmation = {
        **selection,
        "preview_signature": review.json()["preview_signature"],
        "confirmed": True,
        "acknowledge_nutrition": True,
    }
    assert (
        client.post(
            f"{base}/confirm", json={**confirmation, "acknowledge_nutrition": False}, headers=owner
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{base}/confirm", json={**confirmation, "preview_signature": "0" * 64}, headers=owner
        ).status_code
        == 409
    )
    altered = {**confirmation, "items": [{**confirmation["items"][0], "amount": "101"}]}
    assert client.post(f"{base}/confirm", json=altered, headers=owner).status_code == 409
    assert client.post(f"{base}/confirm", json=confirmation, headers=other).status_code == 404
    with get_session_context() as db:
        db.get(Food, food_id).energy_kcal_per_100g = Decimal("210")
    assert client.post(f"{base}/confirm", json=confirmation, headers=owner).status_code == 409
    review = client.post(f"{base}/review", json=selection, headers=owner)
    confirmation["preview_signature"] = review.json()["preview_signature"]
    manual = client.post(
        "/api/v1/nutrition/templates",
        headers=owner,
        json={
            "name": "Ручной",
            "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert manual.status_code == 201, manual.text
    response = client.post(f"{base}/confirm", json=confirmation, headers=owner)
    assert response.status_code == 200, response.text
    assert response.json()["existing"] is True
    assert response.json()["template"]["id"] == manual.json()["id"]
    selection["items"][0]["amount"] = "120"
    review = client.post(f"{base}/review", json=selection, headers=owner)
    assert review.status_code == 200, review.text
    confirmation = {
        **selection,
        "preview_signature": review.json()["preview_signature"],
        "confirmed": True,
        "acknowledge_nutrition": True,
    }
    created = client.post(f"{base}/confirm", json=confirmation, headers=owner)
    assert created.status_code == 200, created.text
    assert created.json()["existing"] is False
    repeat = client.post(f"{base}/confirm", json=confirmation, headers=owner)
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["existing"] is True
    assert repeat.json()["template"]["id"] == created.json()["template"]["id"]
    duplicate = client.post(
        "/api/v1/nutrition/templates",
        headers=owner,
        json={
            "name": "Другое название",
            "items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}],
        },
    )
    assert duplicate.status_code == 409
    update = client.patch(
        f"/api/v1/nutrition/templates/{created.json()['template']['id']}",
        headers=owner,
        json={"items": [{"food_id": food_id, "amount": "100", "amount_unit": "g"}]},
    )
    assert update.status_code == 409
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0
        assert db.query(NutritionMealTemplate).filter_by(owner_user_id=user_id).count() == 2
    insert_url = f"/api/v1/nutrition/templates/{created.json()['template']['id']}/entries"
    insert_headers = {**owner, "Idempotency-Key": "issue-886-insert-001"}
    insert_body = {"diary_date": "2024-02-02", "meal_type": "breakfast"}
    first = client.post(insert_url, headers=insert_headers, json=insert_body)
    second = client.post(insert_url, headers=insert_headers, json=insert_body)
    assert first.status_code == second.status_code == 201
    assert second.json()["replayed"] is True
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 1


def test_concurrent_confirmations_from_separate_imports_create_one_template():
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locks")
    source, document = _validated(
        [
            ["# Period Summary"],
            ["Период: 01.02.2024–29.02.2024"],
            SUMMARY_HEADER,
            ["# Report Details"],
            DETAIL_HEADER,
            ["Дата: 01.02.2024"],
            ["Завтрак"],
            ["Продукт", *NUTRIENTS],
            ["100 г"],
            ["Дата: 02.02.2024"],
            ["Завтрак"],
            ["Продукт", *NUTRIENTS],
            ["120 г"],
        ]
    )
    requests = []
    with get_session_context() as db:
        user = User(telegram_user_id=984_890, measurement_eligibility="test")
        food = _active_food()
        db.add_all([user, food])
        db.flush()
        user_id = user.id
        for number in range(2):
            draft = create_nutrition_import_draft(
                db,
                user,
                document=document,
                source=source,
                filename="synthetic.csv",
                content_type="text/csv",
                delimiter=",",
                parser_version="fatsecret-csv-v1",
                upload_key=f"race-886-{number}",
                adapter_id="fatsecret-csv-v1",
            )
            draft.catalog_receipt = {
                "rows": [{"index": i, "outcome": "reuse", "food_id": food.id} for i in range(2)]
            }
            db.flush()
            selection = RecurringMealReviewRequest.model_validate(
                {
                    "meal_type": "breakfast",
                    "date": "2024-02-01",
                    "name": "Пример",
                    "items": [
                        {"source_index": 0, "food_id": food.id, "amount": "100", "amount_unit": "g"}
                    ],
                }
            )
            review = nutrition_import_meals.review_recurring_meal(db, user, draft.id, selection)
            request = RecurringMealConfirmRequest.model_validate(
                {
                    **selection.model_dump(),
                    "preview_signature": review.preview_signature,
                    "confirmed": True,
                    "acknowledge_nutrition": True,
                }
            )
            requests.append((draft.id, request))
        db.commit()
    barrier = Barrier(2)

    def submit(pair):
        draft_id, request = pair
        with get_session_context() as db:
            user = db.get(User, user_id)
            barrier.wait(timeout=10)
            result = nutrition_import_meals.confirm_recurring_meal(db, user, draft_id, request)
            return result["existing"], result["template"].id

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, requests))
    assert sorted(existing for existing, _ in results) == [False, True]
    assert len({template_id for _, template_id in results}) == 1
    with get_session_context() as db:
        assert db.query(NutritionMealTemplate).filter_by(owner_user_id=user_id).count() == 1
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0

    draft_id, previous = requests[0]
    selection = RecurringMealReviewRequest.model_validate(
        previous.model_dump(exclude={"preview_signature", "confirmed", "acknowledge_nutrition"})
    )
    selection.items[0].amount = Decimal("130")
    with get_session_context() as db:
        user = db.get(User, user_id)
        review = nutrition_import_meals.review_recurring_meal(db, user, draft_id, selection)
        confirm = RecurringMealConfirmRequest.model_validate(
            {
                **selection.model_dump(),
                "preview_signature": review.preview_signature,
                "confirmed": True,
                "acknowledge_nutrition": True,
            }
        )
    barrier = Barrier(2)

    def submit_manual(is_import):
        with get_session_context() as db:
            user = db.get(User, user_id)
            barrier.wait(timeout=10)
            if is_import:
                result = nutrition_import_meals.confirm_recurring_meal(db, user, draft_id, confirm)
                return result["template"].id
            payload = NutritionMealTemplateCreate.model_validate(
                {
                    "name": "Ручной",
                    "items": [
                        {"food_id": selection.items[0].food_id, "amount": "130", "amount_unit": "g"}
                    ],
                }
            )
            try:
                return create_meal_template(db, user, payload).id
            except NutritionPowerConflictError:
                db.rollback()
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        manual_results = list(pool.map(submit_manual, [True, False]))
    assert manual_results[0] is not None
    assert manual_results[1] in {None, manual_results[0]}
    with get_session_context() as db:
        assert db.query(NutritionMealTemplate).filter_by(owner_user_id=user_id).count() == 2


def test_template_with_unknown_serving_mass_keeps_weight_null(client):
    headers = _auth(client, 984_891)
    canonical = build_draft_from_ocr(
        "Per serving\nEnergy 250 kcal\nProtein 10 g\nFat 5 g\nCarbohydrate 30 g"
    )
    with get_session_context() as db:
        food = _active_food(
            energy_kcal_per_100g=None,
            protein_g_per_100g=None,
            fat_g_per_100g=None,
            carbs_g_per_100g=None,
            fiber_g_per_100g=None,
            standard_serving_weight_g=None,
            nutrition_basis_kind="per_serving",
            nutrition_basis_amount=Decimal("1"),
            nutrition_basis_unit="serving",
            canonical_facts=canonical.model_dump(mode="json"),
        )
        db.add(food)
        db.flush()
        food_id = food.id
    result = client.post(
        "/api/v1/nutrition/templates",
        headers=headers,
        json={
            "name": "Порция",
            "items": [{"food_id": food_id, "amount": "2", "amount_unit": "serving"}],
        },
    )
    assert result.status_code == 201, result.text
    assert result.json()["total_weight_g"] is None
    assert result.json()["items"][0]["weight_g"] is None
    assert Decimal(result.json()["totals"]["energy_kcal"]) == Decimal("500")
