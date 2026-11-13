from types import SimpleNamespace
from unittest.mock import MagicMock

from test_food_diary import _active_food
from test_nutrition_import_fatsecret_csv import DETAIL_HEADER, NUTRIENTS, SUMMARY_HEADER, _validated
from test_training_analytics import _auth

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.nutrition_power import NutritionMealTemplate
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import_engine import RecurringImportMeals
from fitminiapp_api.services import nutrition_import_meals
from fitminiapp_api.services.nutrition_import_drafts import create_nutrition_import_draft


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
