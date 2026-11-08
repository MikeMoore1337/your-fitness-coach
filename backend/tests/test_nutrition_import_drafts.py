import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from test_food_diary import _active_food
from test_training_analytics import _auth, _user_id

from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.nutrition_import import NutritionImportDraft
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import import NutritionImportV1
from fitminiapp_api.services.nutrition_import_drafts import (
    NutritionDraftError,
    _entry_action,
    confirm_nutrition_import_draft,
    create_nutrition_import_draft,
    expire_nutrition_import_drafts,
    nutrition_import_preview,
    set_resolutions,
    set_skipped_rows,
)

FIXTURE = Path(__file__).parent / "fixtures" / "nutrition_import" / "neutral-golden.json"
SOURCE = b"name,amount\nsynthetic,100\n"


def _create(db, user, *, key="test-upload-key", source=SOURCE):
    document = NutritionImportV1.model_validate_json(FIXTURE.read_bytes())
    return create_nutrition_import_draft(
        db,
        user,
        document=document,
        source=source,
        filename="synthetic.csv",
        content_type="text/csv",
        delimiter=",",
        parser_version="synthetic-v1",
        upload_key=key,
    )


def test_draft_is_owner_scoped_idempotent_and_never_writes_canonical_data(client):
    _auth(client, 982_001)
    _auth(client, 982_002)
    with get_session_context() as db:
        owner = db.get(User, _user_id(982_001))
        other = db.get(User, _user_id(982_002))
        before = (db.query(Food).count(), db.query(FoodDiaryEntry).count())
        draft = _create(db, owner)
        assert draft.source_sha256 == hashlib.sha256(SOURCE).hexdigest()
        assert SOURCE.decode() not in json.dumps(draft.document, ensure_ascii=False)
        assert _create(db, owner).id == draft.id
        with pytest.raises(NutritionDraftError, match="upload_key_conflict"):
            _create(db, owner, source=b"different,content\n")
        assert _create(db, other).id != draft.id
        with pytest.raises(NutritionDraftError, match="not_found"):
            nutrition_import_preview(db, other, draft.id)
        preview = nutrition_import_preview(db, owner, draft.id)
        assert preview["schema_version"] == "nutrition-import-v1"
        assert preview["rows"][0]["status"] == "manual_resolution_required"
        with pytest.raises(NutritionDraftError, match="unresolved_rows"):
            confirm_nutrition_import_draft(
                db,
                owner,
                draft.id,
                revision=1,
                preview_signature=preview["preview_signature"],
                confirm_key="test-confirm-key",
                confirmed=True,
            )
        assert (db.query(Food).count(), db.query(FoodDiaryEntry).count()) == before


def test_stale_revision_expiry_tampering_and_skips_fail_closed(client):
    _auth(client, 982_003)
    with get_session_context() as db:
        owner = db.get(User, _user_id(982_003))
        draft = _create(db, owner)
        set_skipped_rows(db, owner, draft.id, revision=1, skipped_rows=[0])
        assert nutrition_import_preview(db, owner, draft.id)["rows"][0]["status"] == "skipped"
        with pytest.raises(NutritionDraftError, match="stale_revision"):
            confirm_nutrition_import_draft(
                db,
                owner,
                draft.id,
                revision=1,
                preview_signature="stale",
                confirm_key="test-confirm-key",
                confirmed=True,
            )
        with pytest.raises(NutritionDraftError, match="invalid_rows"):
            set_skipped_rows(db, owner, draft.id, revision=2, skipped_rows=[0, 0])
        draft.document = {**draft.document, "completeness": "unknown"}
        db.flush()
        with pytest.raises(NutritionDraftError, match="draft_changed"):
            nutrition_import_preview(db, owner, draft.id)
        draft.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db.flush()
        with pytest.raises(NutritionDraftError, match="draft_unavailable"):
            nutrition_import_preview(db, owner, draft.id)
        assert expire_nutrition_import_drafts(db) == 1
        db.flush()
        assert db.get(NutritionImportDraft, draft.id) is None


def test_concurrent_same_key_creates_one_draft_in_postgresql(client):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locking")
    _auth(client, 982_004)
    owner_id = _user_id(982_004)
    barrier = Barrier(2)

    def run():
        with get_session_context() as db:
            owner = db.get(User, owner_id)
            barrier.wait(timeout=10)
            draft = _create(db, owner)
            result = draft.id
            db.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert results[0] == results[1]
    with get_session_context() as db:
        assert db.query(NutritionImportDraft).filter_by(owner_user_id=owner_id).count() == 1


def _prepared(db, user, *, matches=None, key="ready-upload-key"):
    food = _active_food(protein_g_per_100g=None)
    db.add(food)
    db.flush()
    draft = _create(db, user, key=key)
    selected = matches or {0: food.id}
    selected = dict.fromkeys(selected, food.id)
    skipped = [index for index in range(len(draft.document["rows"])) if index not in selected]
    set_resolutions(db, user, draft.id, revision=1, matches=selected, skipped_rows=skipped)
    preview = nutrition_import_preview(db, user, draft.id)
    return draft.id, food.id, preview


def _confirm(db, user, draft_id, preview, *, key="test-confirm-key"):
    return confirm_nutrition_import_draft(
        db,
        user,
        draft_id,
        revision=preview["revision"],
        preview_signature=preview["preview_signature"],
        confirm_key=key,
        confirmed=True,
    )


def test_confirm_matches_preview_and_replays_after_commit(client):
    _auth(client, 982_005)
    with get_session_context() as db:
        owner = db.get(User, _user_id(982_005))
        draft_id, _, preview = _prepared(db, owner)
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner.id).count() == 0
        assert preview["rows"][0]["status"] == "matched"
        assert preview["rows"][0]["action"]["nutrition_amount"]["protein_g"] is None
        receipt = _confirm(db, owner, draft_id, preview)
        db.commit()
        entry = db.get(FoodDiaryEntry, receipt["entry_ids"][0])
        assert str(entry.amount) == "100.000"
        assert entry.nutrition_amount == preview["rows"][0]["action"]["nutrition_amount"]
        assert _entry_action(entry) == preview["rows"][0]["action"]
        assert entry.protein_g_per_100g is None
    with get_session_context() as db:
        owner = db.get(User, _user_id(982_005))
        assert _confirm(db, owner, draft_id, preview) == receipt
        with pytest.raises(NutritionDraftError, match="confirmation_conflict"):
            _confirm(db, owner, draft_id, preview, key="different-confirm-key")


def test_catalog_change_and_unowned_food_fail_closed(client):
    _auth(client, 982_006)
    _auth(client, 982_007)
    with get_session_context() as db:
        owner = db.get(User, _user_id(982_006))
        other = db.get(User, _user_id(982_007))
        private = _active_food(food_type="user", owner_user_id=other.id, provenance="user")
        db.add(private)
        db.flush()
        draft_id, food_id, preview = _prepared(db, owner)
        with pytest.raises(NutritionDraftError, match="invalid_match"):
            set_resolutions(
                db, owner, draft_id, revision=2, matches={0: private.id}, skipped_rows=[1, 2, 3, 4]
            )
        food = db.get(Food, food_id)
        food.energy_kcal_per_100g = 220
        db.flush()
        with pytest.raises(NutritionDraftError, match="preview_changed"):
            _confirm(db, owner, draft_id, preview)
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner.id).count() == 0


def test_mid_write_failure_rolls_back_all_entries(client, monkeypatch):
    import fitminiapp_api.services.nutrition_import_drafts as service

    _auth(client, 982_008)
    with get_session_context() as db:
        owner = db.get(User, _user_id(982_008))
        draft_id, food_id, preview = _prepared(db, owner, matches={0: 1, 4: 1})
        from datetime import date
        from decimal import Decimal

        from fitminiapp_api.schemas.food_diary import FoodDiaryEntryCreate
        from fitminiapp_api.services.food_diary import create_food_diary_entry

        existing = create_food_diary_entry(
            db,
            owner,
            FoodDiaryEntryCreate(
                food_id=food_id,
                diary_date=date(2024, 3, 1),
                meal_type="breakfast",
                amount=Decimal("50"),
                amount_unit="g",
            ),
        )
        existing_id = existing.id
        db.commit()
    original = service._planned_entry
    calls = 0

    def fail_on_second_write(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise RuntimeError("synthetic failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_planned_entry", fail_on_second_write)
    with get_session_context() as db:
        owner = db.get(User, _user_id(982_008))
        with pytest.raises(RuntimeError, match="synthetic failure"):
            _confirm(db, owner, draft_id, preview)
        db.rollback()
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner.id).count() == 1
        assert str(db.get(FoodDiaryEntry, existing_id).amount) == "50.000"
        assert db.get(NutritionImportDraft, draft_id).status == "pending"


def test_concurrent_confirm_writes_once_in_postgresql(client):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locking")
    _auth(client, 982_009)
    owner_id = _user_id(982_009)
    with get_session_context() as db:
        owner = db.get(User, owner_id)
        draft_id, _, preview = _prepared(db, owner)
        db.commit()
    barrier = Barrier(2)

    def run():
        with get_session_context() as db:
            owner = db.get(User, owner_id)
            barrier.wait(timeout=10)
            receipt = _confirm(db, owner, draft_id, preview)
            db.commit()
            return receipt

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert results[0] == results[1]
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 1


def test_modified_content_hash_and_duplicate_reupload_are_rejected(client):
    _auth(client, 982_010)
    with get_session_context() as db:
        owner = db.get(User, _user_id(982_010))
        draft_id, food_id, preview = _prepared(db, owner)
        receipt = _confirm(db, owner, draft_id, preview)
        db.commit()
        duplicate = _create(db, owner, key="different-upload-key")
        set_resolutions(
            db, owner, duplicate.id, revision=1, matches={0: food_id}, skipped_rows=[1, 2, 3, 4]
        )
        repeated = nutrition_import_preview(db, owner, duplicate.id)
        with pytest.raises(NutritionDraftError, match="duplicate_import"):
            _confirm(db, owner, duplicate.id, repeated, key="different-confirm-key")
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner.id).count() == 1
        assert db.get(FoodDiaryEntry, receipt["entry_ids"][0]) is not None
        duplicate.source_sha256 = "a" * 64
        db.flush()
        with pytest.raises(NutritionDraftError, match="draft_changed"):
            nutrition_import_preview(db, owner, duplicate.id)


def test_database_disconnect_rolls_back_then_retry_succeeds(client):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL backend termination")
    import re

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from fitminiapp_api.db.session import SessionLocal

    _auth(client, 982_011)
    owner_id = _user_id(982_011)
    with get_session_context() as db:
        owner = db.get(User, owner_id)
        draft_id, _, preview = _prepared(db, owner)
        db.commit()
    with SessionLocal() as db:
        owner = db.get(User, owner_id)
        database = db.execute(text("SELECT current_database()")).scalar_one()
        if re.fullmatch(r"[A-Za-z0-9_]*_test(?:_gw[0-9]+)?", database) is None:
            pytest.skip("only disposable test databases may terminate a connection")
        _confirm(db, owner, draft_id, preview)
        backend_pid = db.execute(text("SELECT pg_backend_pid()")).scalar_one()
        with engine.begin() as terminator:
            assert terminator.execute(
                text("SELECT pg_terminate_backend(:pid)"), {"pid": backend_pid}
            ).scalar_one()
        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()
    with get_session_context() as db:
        owner = db.get(User, owner_id)
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 0
        assert db.get(NutritionImportDraft, draft_id).status == "pending"
        receipt = _confirm(db, owner, draft_id, preview)
        db.commit()
        assert len(receipt["entry_ids"]) == 1


def test_resolutions_keep_distinct_food_snapshots(client):
    _auth(client, 982_012)
    with get_session_context() as db:
        owner = db.get(User, _user_id(982_012))
        first = _active_food(name="Synthetic A", energy_kcal_per_100g=200)
        second = _active_food(name="Synthetic B", energy_kcal_per_100g=300)
        db.add_all([first, second])
        db.flush()
        draft = _create(db, owner)
        set_resolutions(
            db,
            owner,
            draft.id,
            revision=1,
            matches={0: first.id, 4: second.id},
            skipped_rows=[1, 2, 3],
        )
        preview = nutrition_import_preview(db, owner, draft.id)
        assert preview["rows"][0]["action"]["food_name"] == "Synthetic A"
        assert preview["rows"][4]["action"]["food_name"] == "Synthetic B"
        receipt = _confirm(db, owner, draft.id, preview)
        db.flush()
        assert [
            db.get(FoodDiaryEntry, entry_id).food_name for entry_id in receipt["entry_ids"]
        ] == ["Synthetic A", "Synthetic B"]


def test_confirm_rechecks_account_after_authentication(client):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL transaction isolation")
    from fitminiapp_api.db.session import SessionLocal

    _auth(client, 982_013)
    owner_id = _user_id(982_013)
    with get_session_context() as setup:
        owner = setup.get(User, owner_id)
        draft_id, _, preview = _prepared(setup, owner)
        setup.commit()
    with SessionLocal() as stale, SessionLocal() as revoker:
        stale_owner = stale.get(User, owner_id)
        assert stale_owner.is_active
        revoker.get(User, owner_id).is_active = False
        revoker.commit()
        with pytest.raises(NutritionDraftError, match="access_revoked"):
            _confirm(stale, stale_owner, draft_id, preview)
        stale.rollback()
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 0
