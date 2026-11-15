from copy import deepcopy
from datetime import UTC, date, datetime, timedelta

from test_nutrition_import_fatsecret_csv import _validated
from test_nutrition_reports import _entry
from test_training_analytics import _auth, _user_id

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.user import User
from fitminiapp_api.services.nutrition_import_drafts import create_nutrition_import_draft
from fitminiapp_api.services.nutrition_import_history import prepare_history_rows

pytest_plugins = ["test_nutrition_import_fatsecret_csv"]


def test_history_uses_only_observed_dates_and_keeps_source_facts(rows):
    _, document = _validated(rows)
    prepared = prepare_history_rows(document)

    assert {item["source"].diary_date.isoformat() for item in prepared} == {
        "2024-02-29",
        "2024-03-02",
    }
    first = prepared[0]
    assert first["source"].meal_type == "breakfast"
    assert str(first["source"].quantity) == "100.00"
    assert first["source"].amount_unit == "g"
    assert str(first["original_total"].facts.energy_kcal.value) == "12.30000001"
    assert first["original_total"].facts.fiber_g.value is None
    assert str(first["nutrition_amount"]["energy_kcal"]) == "12.30000001"
    assert first["nutrition_amount"]["fiber_g"] is None
    assert not first["ambiguous_facts"]


def test_fingerprint_survives_row_reordering_but_identical_rows_need_review(rows):
    _, original = _validated(rows)
    reordered_rows = deepcopy(rows)
    reordered_rows[9:13] = reordered_rows[11:13] + reordered_rows[9:11]
    _, reordered = _validated(reordered_rows)
    before = prepare_history_rows(original)
    after = prepare_history_rows(reordered)

    assert before[0]["fingerprint"] == after[1]["fingerprint"]
    assert before[3]["fingerprint"] == before[5]["fingerprint"]
    assert before[3]["ambiguous_duplicate"]
    assert before[5]["ambiguous_duplicate"]
    assert not before[0]["ambiguous_duplicate"]


def test_missing_or_ambiguous_source_facts_are_not_invented(rows):
    _, document = _validated(rows)
    document.original_totals = [
        total
        for total in document.original_totals
        if total.coordinates != document.rows[0].coordinates
    ]
    prepared = prepare_history_rows(document)
    assert prepared[0]["original_total"] is None
    assert prepared[0]["ambiguous_facts"]
    assert prepared[0]["fingerprint"] is None
    assert all(value is None for value in prepared[0]["nutrition_amount"].values())


def test_partial_export_fingerprint_is_independent_of_file_and_line(rows):
    _, original = _validated(rows)
    partial_rows = deepcopy(rows[:7] + rows[18:])
    _, partial = _validated(partial_rows)
    full_result = prepare_history_rows(original)
    partial_result = prepare_history_rows(partial)
    assert partial_result[0]["source"].diary_date.isoformat() == "2024-03-02"
    assert partial_result[0]["fingerprint"] == full_result[3]["fingerprint"]
    assert partial_result[0]["ambiguous_duplicate"]


def test_source_details_change_candidate_fingerprint(rows):
    _, original = _validated(rows)
    changed_rows = deepcopy(rows)
    changed_rows[9][3] = "0,75"
    _, changed = _validated(changed_rows)
    assert (
        prepare_history_rows(original)[0]["fingerprint"]
        != prepare_history_rows(changed)[0]["fingerprint"]
    )


def test_source_amount_does_not_convert_unknown_or_mismatched_units(rows):
    _, document = _validated(rows)
    total = next(
        item
        for item in document.original_totals
        if item.coordinates == document.rows[0].coordinates
    )
    total.facts.energy_kcal.unit = "mg"
    result = prepare_history_rows(document)[0]["nutrition_amount"]
    assert result["energy_kcal"] is None
    assert result["fiber_g"] is None
    assert str(result["protein_g"]) == "3.00"


def test_history_preview_is_private_read_only_and_expires(client, rows):
    owner_headers = _auth(client, 984_701)
    other_headers = _auth(client, 984_702)
    owner_id, other_id = _user_id(984_701), _user_id(984_702)
    source, document = _validated(rows)
    with get_session_context() as db:
        draft = create_nutrition_import_draft(
            db,
            db.get(User, owner_id),
            document=document,
            source=source,
            filename="synthetic.csv",
            content_type="text/csv",
            delimiter=",",
            parser_version="fatsecret-csv-v1",
            upload_key="synthetic-history-preview",
            adapter_id="fatsecret-csv-v1",
        )
        draft_id = draft.id
        own = _entry(owner_id, date(2024, 2, 29))
        own.meal_type = "breakfast"
        own.food_name = "Существующая запись"
        foreign = _entry(other_id, date(2024, 2, 29))
        foreign.meal_type = "breakfast"
        foreign.food_name = "Чужая запись"
        db.add_all([own, foreign])
        db.commit()

    url = f"/api/v1/nutrition/imports/{draft_id}/history"
    assert client.get(url, headers=other_headers).status_code == 404
    response = client.get(url, headers=owner_headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    preview = response.json()
    assert preview["dates"] == ["2024-02-29", "2024-03-02"]
    assert preview["rows"][0]["original_total"]["facts"]["energy_kcal"]["value"] == "12.30000001"
    assert preview["rows"][0]["original_total"]["facts"]["fiber_g"]["value"] is None
    assert preview["rows"][0]["nutrition_amount"]["energy_kcal"] == "12.30000001"
    assert preview["rows"][0]["nutrition_amount"]["fiber_g"] is None
    assert len(preview["existing_meals"]) == 1
    assert preview["existing_meals"][0]["entries"][0]["food_name"] == "Существующая запись"
    assert "Чужая запись" not in response.text
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).count() == 2
        draft = db.get(type(draft), draft_id)
        assert draft.status == "pending"
        draft.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    assert client.get(url, headers=owner_headers).status_code == 410
