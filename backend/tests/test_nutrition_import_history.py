from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import event
from test_food_diary import _active_food, _set_timezone
from test_nutrition_import_fatsecret_csv import _validated
from test_nutrition_reports import _entry
from test_training_analytics import _auth, _user_id

from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import_engine import HistoryConfirmRequest
from fitminiapp_api.services.nutrition_import_drafts import (
    create_nutrition_import_draft,
    nutrition_import_preview,
    set_resolutions,
)
from fitminiapp_api.services.nutrition_import_history import confirm_history, prepare_history_rows

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
    assert len(preview["preview_signature"]) == 64
    assert len(preview["existing_meals"]) == 1
    assert preview["existing_meals"][0]["entries"][0]["food_name"] == "Существующая запись"
    assert "Чужая запись" not in response.text
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).count() == 2
        own = db.query(FoodDiaryEntry).filter_by(user_id=owner_id).one()
        own.food_name = "Изменённая запись"
        db.commit()
    changed = client.get(url, headers=owner_headers)
    assert changed.status_code == 200
    assert changed.json()["preview_signature"] != preview["preview_signature"]
    with get_session_context() as db:
        draft = db.get(type(draft), draft_id)
        assert draft.status == "pending"
        draft.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    assert client.get(url, headers=owner_headers).status_code == 410


def test_history_review_modes_and_stale_preview_never_write(client, rows):
    owner_headers = _auth(client, 984_703)
    other_headers = _auth(client, 984_704)
    owner_id = _user_id(984_703)
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
            upload_key="synthetic-history-review",
            adapter_id="fatsecret-csv-v1",
        )
        draft_id = draft.id
        own = _entry(owner_id, date(2024, 2, 29))
        own.meal_type = "breakfast"
        own.food_name = "Тестовый продукт, альфа"
        db.add(own)
        db.commit()
    root = f"/api/v1/nutrition/imports/{draft_id}/history"
    preview = client.get(root, headers=owner_headers).json()
    request = {
        "revision": preview["revision"],
        "preview_signature": preview["preview_signature"],
        "date_from": "2024-02-29",
        "date_to": "2024-02-29",
        "mode": "keep",
    }
    assert client.post(f"{root}/review", headers=other_headers, json=request).status_code == 404
    keep = client.post(f"{root}/review", headers=owner_headers, json=request)
    assert keep.status_code == 200, keep.text
    assert [row["action"] for row in keep.json()["rows"][:3]] == ["skip", "skip", "add"]
    add = client.post(
        f"{root}/review", headers=owner_headers, json={**request, "mode": "add_missing"}
    )
    assert add.status_code == 200, add.text
    assert [row["action"] for row in add.json()["rows"][:3]] == ["conflict", "add", "add"]
    manual = {
        **request,
        "mode": "manual",
        "selected_rows": [0],
        "decisions": [{"index": 0, "action": "add"}],
    }
    result = client.post(f"{root}/review", headers=owner_headers, json=manual)
    assert result.status_code == 200, result.text
    assert [row["action"] for row in result.json()["rows"][:3]] == ["add", "skip", "skip"]
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 1
        db.query(FoodDiaryEntry).filter_by(user_id=owner_id).one().food_name = "Изменено"
        db.commit()
    stale = client.post(f"{root}/review", headers=owner_headers, json=manual)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "preview_changed"


def _history_draft(db, user, rows, key):
    source, document = _validated(rows)
    return create_nutrition_import_draft(
        db,
        user,
        document=document,
        source=source,
        filename="synthetic.csv",
        content_type="text/csv",
        delimiter=",",
        parser_version="fatsecret-csv-v1",
        upload_key=key,
        adapter_id="fatsecret-csv-v1",
    )


def _history_confirmation(client, headers, draft_id, *, decisions=None, selected=None):
    root = f"/api/v1/nutrition/imports/{draft_id}/history"
    preview = client.get(root, headers=headers).json()
    request = {
        "revision": preview["revision"],
        "preview_signature": preview["preview_signature"],
        "date_from": "2024-02-29",
        "date_to": "2024-02-29",
        "mode": "manual",
        "selected_rows": selected if selected is not None else [0],
        "decisions": decisions or [],
    }
    review = client.post(f"{root}/review", headers=headers, json=request)
    assert review.status_code == 200, review.text
    return (
        root,
        {
            **request,
            "review_signature": review.json()["review_signature"],
            "confirm_key": "synthetic-history-confirm",
            "confirmed": True,
        },
        review.json(),
    )


def test_confirm_history_keeps_source_snapshot_and_replays(client, rows):
    owner = _auth(client, 984_705)
    other = _auth(client, 984_706)
    owner_id = _user_id(984_705)
    with get_session_context() as db:
        draft_id = _history_draft(db, db.get(User, owner_id), rows, "history-confirm-upload").id
        db.commit()
    root, payload, review = _history_confirmation(client, owner, draft_id)
    assert review["rows"][0]["action"] == "add"
    assert client.post(f"{root}/confirm", headers=other, json=payload).status_code == 404
    assert (
        client.post(
            f"{root}/confirm", headers=owner, json={**payload, "confirmed": False}
        ).status_code
        == 422
    )
    result = client.post(f"{root}/confirm", headers=owner, json=payload)
    assert result.status_code == 200, result.text
    assert (result.json()["added"], result.json()["skipped"]) == (1, 0)
    assert client.post(f"{root}/confirm", headers=owner, json=payload).json() == result.json()
    diary = client.get(
        "/api/v1/nutrition/diary", headers=owner, params={"diary_date": "2024-02-29"}
    )
    assert diary.status_code == 200, diary.text
    entry = diary.json()["meals"][0]["entries"][0]
    assert entry["food_name"] == "Тестовый продукт, альфа"
    assert entry["nutrition_source"] == "fatsecret"
    assert entry["logged_at"] is None
    assert Decimal(entry["nutrition"]["energy_kcal"]) == Decimal("12.30000001")
    assert entry["nutrition"]["fiber_g"] is None
    assert diary.json()["status"] == "incomplete"
    changed = client.patch(
        f"/api/v1/nutrition/diary/entries/{entry['id']}",
        headers=owner,
        json={"amount": "200", "amount_unit": "g"},
    )
    assert changed.status_code == 200, changed.text
    assert Decimal(changed.json()["nutrition"]["energy_kcal"]) == Decimal("24.60000002")
    assert changed.json()["nutrition"]["fiber_g"] is None
    rounded = client.patch(
        f"/api/v1/nutrition/diary/entries/{entry['id']}",
        headers=owner,
        json={"amount": "33.333", "amount_unit": "g"},
    )
    assert rounded.status_code == 200, rounded.text
    assert Decimal(rounded.json()["nutrition"]["energy_kcal"]) == Decimal("4.09995900")
    restored = client.patch(
        f"/api/v1/nutrition/diary/entries/{entry['id']}",
        headers=owner,
        json={"amount": "100", "amount_unit": "g"},
    )
    assert restored.status_code == 200, restored.text
    assert Decimal(restored.json()["nutrition"]["energy_kcal"]) == Decimal("12.30000001")
    copy_request = {
        "source_entry_id": entry["id"],
        "source_date": "2024-02-29",
        "source_meal_type": "breakfast",
        "target_date": "2024-03-01",
        "target_meal_type": "lunch",
    }
    copy_preview = client.post(
        "/api/v1/nutrition/diary/copy/product/preview", headers=owner, json=copy_request
    )
    assert copy_preview.status_code == 200, copy_preview.text
    copied = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**owner, "Idempotency-Key": "copy-imported-history"},
        json={**copy_request, "preview_token": copy_preview.json()["preview_token"]},
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()["entries"][0]["nutrition"] == restored.json()["nutrition"]
    assert copied.json()["entries"][0]["nutrition_source"] == "fatsecret"
    report = client.get(
        "/api/v1/workouts/progress/nutrition-report",
        headers=owner,
        params={"period": "custom", "date_from": "2024-02-29", "date_to": "2024-03-02"},
    )
    assert report.status_code == 200, report.text
    days = {day["diary_date"]: day for day in report.json()["daily"]}
    assert days["2024-02-29"]["status"] == "incomplete"
    assert days["2024-02-29"]["calories"] == 12.3
    assert days["2024-03-01"]["status"] == "incomplete"
    assert days["2024-03-02"]["status"] == "missing"
    assert report.json()["summary"]["logged_days"] == 0
    with get_session_context() as db:
        stored = db.get(FoodDiaryEntry, result.json()["entry_ids"][0])
        assert stored.food_id is None
        assert stored.nutrition_snapshot["source"] == "fatsecret"
        assert stored.nutrition_snapshot["source_record_fingerprint"] == stored.request_fingerprint
        assert stored.nutrition_amount["energy_kcal"] == "12.30000001"


def test_confirm_rechecks_conflicts_after_preview(client, rows):
    owner = _auth(client, 984_707)
    owner_id = _user_id(984_707)
    with get_session_context() as db:
        draft_id = _history_draft(db, db.get(User, owner_id), rows, "history-stale-upload").id
        db.commit()
    root, payload, _ = _history_confirmation(client, owner, draft_id)
    with get_session_context() as db:
        entry = _entry(owner_id, date(2024, 2, 29))
        entry.meal_type = "breakfast"
        db.add(entry)
        db.commit()
    response = client.post(f"{root}/confirm", headers=owner, json=payload)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "preview_changed"
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 1


def test_confirmation_rolls_back_every_entry_on_failure(client, rows):
    owner = _auth(client, 984_708)
    owner_id = _user_id(984_708)
    with get_session_context() as db:
        draft_id = _history_draft(db, db.get(User, owner_id), rows, "history-rollback-upload").id
        db.commit()
    _, payload, _ = _history_confirmation(client, owner, draft_id, selected=[0, 1])
    with get_session_context() as db:
        user = db.get(User, owner_id)

        def fail_flush(session, context, instances):
            if any(isinstance(item, FoodDiaryEntry) for item in session.new):
                raise RuntimeError("synthetic write failure")

        event.listen(db, "before_flush", fail_flush)
        with pytest.raises(RuntimeError, match="synthetic write failure"):
            confirm_history(db, user, draft_id, HistoryConfirmRequest.model_validate(payload))
        db.rollback()
        event.remove(db, "before_flush", fail_flush)
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 0


def test_reupload_requires_explicit_decision_and_does_not_duplicate(client, rows):
    owner = _auth(client, 984_709)
    owner_id = _user_id(984_709)
    with get_session_context() as db:
        first = _history_draft(db, db.get(User, owner_id), rows, "history-overlap-first").id
        db.commit()
    root, payload, _ = _history_confirmation(client, owner, first)
    assert client.post(f"{root}/confirm", headers=owner, json=payload).status_code == 200
    with get_session_context() as db:
        stored = db.query(FoodDiaryEntry).filter_by(user_id=owner_id).one()
        stored.food_name = "Переименованная запись"
        second = _history_draft(db, db.get(User, owner_id), rows, "history-overlap-second").id
        db.commit()
    root, payload, review = _history_confirmation(client, owner, second)
    assert review["rows"][0]["action"] == "conflict"
    payload["confirm_key"] = "history-overlap-confirm"
    assert client.post(f"{root}/confirm", headers=owner, json=payload).status_code == 409
    root, payload, review = _history_confirmation(
        client, owner, second, decisions=[{"index": 0, "action": "skip"}]
    )
    assert review["rows"][0]["action"] == "skip"
    payload["confirm_key"] = "history-overlap-confirm"
    result = client.post(f"{root}/confirm", headers=owner, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["added"] == 0
    assert result.json()["skipped"] == 1
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 1


def test_piece_serving_preserves_amount_without_invented_weight(client, rows):
    owner = _auth(client, 984_710)
    owner_id = _user_id(984_710)
    with get_session_context() as db:
        draft_id = _history_draft(db, db.get(User, owner_id), rows, "history-piece-upload").id
        db.commit()
    root, payload, review = _history_confirmation(client, owner, draft_id, selected=[2])
    assert review["rows"][2]["action"] == "add"
    result = client.post(f"{root}/confirm", headers=owner, json=payload)
    assert result.status_code == 200, result.text
    diary = client.get(
        "/api/v1/nutrition/diary", headers=owner, params={"diary_date": "2024-02-29"}
    ).json()
    entry = next(item for meal in diary["meals"] for item in meal["entries"])
    assert Decimal(entry["amount"]) == Decimal("2")
    assert entry["amount_unit"] == "serving"
    assert entry["serving_unit"] == "piece"
    assert entry["weight_g"] is None


def test_fasted_day_cannot_be_changed_by_history_import(client, rows):
    owner = _auth(client, 984_711)
    owner_id = _user_id(984_711)
    with get_session_context() as db:
        draft_id = _history_draft(db, db.get(User, owner_id), rows, "history-fasted-upload").id
        db.add(FoodDiaryDayStatus(user_id=owner_id, diary_date=date(2024, 2, 29), status="fasted"))
        db.commit()
    root, payload, review = _history_confirmation(client, owner, draft_id)
    assert review["rows"][0]["action"] == "invalid"
    assert review["rows"][0]["reason"] == "day_status_conflict"
    assert client.post(f"{root}/confirm", headers=owner, json=payload).status_code == 409
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 0
        assert db.get(FoodDiaryDayStatus, (owner_id, date(2024, 2, 29))).status == "fasted"


def test_legacy_catalog_based_confirmation_cannot_replace_source_facts(client, rows):
    owner = _auth(client, 984_712)
    owner_id = _user_id(984_712)
    with get_session_context() as db:
        user = db.get(User, owner_id)
        draft = _history_draft(db, user, rows, "history-legacy-upload")
        food = _active_food()
        db.add(food)
        db.flush()
        set_resolutions(
            db,
            user,
            draft.id,
            revision=draft.revision,
            matches={0: food.id},
            skipped_rows=[1, 2, 3, 4, 5],
        )
        preview = nutrition_import_preview(db, user, draft.id)
        draft_id = draft.id
        db.commit()
    response = client.post(
        f"/api/v1/nutrition/imports/{draft_id}/confirm",
        headers=owner,
        json={
            "revision": preview["revision"],
            "preview_signature": preview["preview_signature"],
            "confirm_key": "history-legacy-confirm",
            "confirmed": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "history_confirmation_required"
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 0


def test_users_can_import_the_same_source_independently(client, rows):
    owners = [_auth(client, 984_713), _auth(client, 984_714)]
    ids = [_user_id(984_713), _user_id(984_714)]
    for index, headers in enumerate(owners):
        with get_session_context() as db:
            draft_id = _history_draft(
                db, db.get(User, ids[index]), rows, f"history-owner-upload-{index}"
            ).id
            db.commit()
        root, payload, review = _history_confirmation(client, headers, draft_id)
        assert review["rows"][0]["action"] == "add"
        result = client.post(f"{root}/confirm", headers=headers, json=payload)
        assert result.status_code == 200, result.text
    with get_session_context() as db:
        assert [db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() for user_id in ids] == [
            1,
            1,
        ]


@pytest.mark.parametrize(
    "timezone_name,telegram_id", [("Pacific/Kiritimati", 984_716), ("America/New_York", 984_717)]
)
def test_calendar_dates_survive_user_timezones(client, rows, timezone_name, telegram_id):
    owner = _auth(client, telegram_id)
    _set_timezone(telegram_id, timezone_name)
    with get_session_context() as db:
        draft_id = _history_draft(
            db, db.get(User, _user_id(telegram_id)), rows, f"timezone-{telegram_id}"
        ).id
        db.commit()
    root, payload, _ = _history_confirmation(client, owner, draft_id)
    result = client.post(f"{root}/confirm", headers=owner, json=payload)
    assert result.status_code == 200, result.text
    diary = client.get(
        "/api/v1/nutrition/diary", headers=owner, params={"diary_date": "2024-02-29"}
    )
    assert diary.status_code == 200, diary.text
    assert diary.json()["diary_date"] == "2024-02-29"
    assert sum(len(meal["entries"]) for meal in diary.json()["meals"]) == 1


def test_history_and_catalog_confirm_independently(client, rows):
    owner = _auth(client, 984_718)
    with get_session_context() as db:
        draft_id = _history_draft(
            db, db.get(User, _user_id(984_718)), rows, "history-catalog-independent"
        ).id
        db.commit()
    root, payload, _ = _history_confirmation(client, owner, draft_id)
    history = client.post(f"{root}/confirm", headers=owner, json=payload)
    assert history.status_code == 200, history.text
    catalog_root = f"/api/v1/nutrition/imports/{draft_id}/catalog"
    preview = client.get(catalog_root, headers=owner)
    assert preview.status_code == 200, preview.text
    catalog = client.post(
        f"{catalog_root}/confirm",
        headers=owner,
        json={
            "revision": preview.json()["revision"],
            "preview_signature": preview.json()["preview_signature"],
            "confirm_key": "independent-catalog-key",
            "row_indexes": [],
            "confirmed": True,
        },
    )
    assert catalog.status_code == 200, catalog.text
    assert client.post(f"{root}/confirm", headers=owner, json=payload).json() == history.json()


def test_concurrent_history_confirm_is_idempotent_on_postgresql(client, rows):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locking")
    owner = _auth(client, 984_715)
    owner_id = _user_id(984_715)
    with get_session_context() as db:
        draft_id = _history_draft(db, db.get(User, owner_id), rows, "history-concurrent-upload").id
        db.commit()
    _, payload, _ = _history_confirmation(client, owner, draft_id)
    barrier = Barrier(2)

    def run():
        with get_session_context() as db:
            user = db.get(User, owner_id)
            barrier.wait(timeout=10)
            receipt = confirm_history(
                db, user, draft_id, HistoryConfirmRequest.model_validate(payload)
            )
            db.commit()
            return receipt

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: run(), range(2)))
    assert receipts[0] == receipts[1]
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 1
