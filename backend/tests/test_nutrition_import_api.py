import logging
from pathlib import Path

import pytest
from test_food_diary import _active_food
from test_training_analytics import _auth, _user_id

from fitminiapp_api.api.v1 import nutrition_imports
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.nutrition_import import NutritionImportUploadAttempt
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import import NutritionImportV1
from fitminiapp_api.services.account_export import build_account_export
from fitminiapp_api.services.nutrition_import_drafts import NutritionDraftError
from fitminiapp_api.services.nutrition_import_limits import acquire_parser_slot
from fitminiapp_api.services.nutrition_import_runner import NutritionImportAdapter

URL = "/api/v1/nutrition/imports"
FIXTURE = Path(__file__).parent / "fixtures" / "nutrition_import" / "neutral-golden.json"


@pytest.fixture
def postgres():
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL transaction locks")


@pytest.fixture
def synthetic_adapter(monkeypatch):
    adapter = NutritionImportAdapter("fatsecret", "synthetic-v1", "synthetic-v1", ",", FIXTURE)
    monkeypatch.setitem(nutrition_imports.ADAPTERS, "synthetic", adapter)

    def parse(*args, **kwargs):
        return NutritionImportV1.model_validate_json(FIXTURE.read_bytes())

    monkeypatch.setattr(nutrition_imports, "run_nutrition_import_adapter", parse)


def _upload(client, headers, *, key="upload-key-123", adapter="synthetic"):
    return client.post(
        URL,
        headers={**headers, "Idempotency-Key": key},
        data={"adapter_id": adapter},
        files={"file": ("synthetic.csv", b"name,amount\nsynthetic,100\n", "text/csv")},
    )


def test_unknown_adapter_fails_closed_and_per_user_rate_limit(client, postgres):
    headers = _auth(client, 983_001)
    other = _auth(client, 983_002)
    for _ in range(10):
        assert _upload(client, headers, adapter="absent").status_code == 415
    limited = _upload(client, headers, adapter="absent")
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "rate_limited"
    assert _upload(client, other, adapter="absent").status_code == 415
    with get_session_context() as db:
        assert (
            db.query(NutritionImportUploadAttempt)
            .filter_by(owner_user_id=_user_id(983_001))
            .count()
            == 10
        )


def test_api_preview_confirm_and_ownership(client, postgres, synthetic_adapter):
    headers = _auth(client, 983_003)
    other = _auth(client, 983_004)
    with get_session_context() as db:
        food = _active_food(protein_g_per_100g=None)
        db.add(food)
        db.flush()
        food_id = food.id
    uploaded = _upload(client, headers)
    assert uploaded.status_code == 201, uploaded.text
    draft = uploaded.json()
    assert draft["schema_version"] == "nutrition-import-v1"
    assert draft["rows"][0]["status"] == "manual_resolution_required"
    assert client.get(f"{URL}/{draft['id']}", headers=other).status_code == 404
    assert (
        client.post(
            f"{URL}/{draft['id']}/confirm",
            headers=other,
            json={
                "revision": 1,
                "preview_signature": draft["preview_signature"],
                "confirm_key": "confirm-key-123",
                "confirmed": True,
            },
        ).status_code
        == 404
    )
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=_user_id(983_003)).count() == 0
    resolved = client.post(
        f"{URL}/{draft['id']}/resolve",
        headers=headers,
        json={
            "revision": 1,
            "matches": [{"index": 0, "food_id": food_id}],
            "skipped_rows": [1, 2, 3, 4],
        },
    )
    assert resolved.status_code == 200, resolved.text
    preview = resolved.json()
    assert preview["rows"][0]["status"] == "matched"
    assert preview["rows"][0]["action"]["nutrition_amount"]["protein_g"] is None
    confirm = {
        "revision": preview["revision"],
        "preview_signature": preview["preview_signature"],
        "confirm_key": "confirm-key-123",
        "confirmed": True,
    }
    invalid = client.post(
        f"{URL}/{draft['id']}/confirm", headers=headers, json={**confirm, "confirmed": 1}
    )
    assert invalid.status_code == 422
    result = client.post(f"{URL}/{draft['id']}/confirm", headers=headers, json=confirm)
    assert result.status_code == 200, result.text
    assert (
        client.post(f"{URL}/{draft['id']}/confirm", headers=headers, json=confirm).json()
        == result.json()
    )
    with get_session_context() as db:
        owner = db.get(User, _user_id(983_003))
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner.id).count() == 1
        exported = build_account_export(db, owner)
        assert exported["nutrition_import_drafts"][0]["id"] == draft["id"]
        assert (
            build_account_export(db, db.get(User, _user_id(983_004)))["nutrition_import_drafts"]
            == []
        )


def test_request_logs_do_not_expose_path_or_query_secrets(client, postgres, caplog):
    headers = _auth(client, 983_005)
    caplog.set_level(logging.INFO, logger="app.http")
    marker = "secret-path-983005"
    query = "secret-query-983005"
    response = client.get(f"{URL}/{marker}?token={query}", headers=headers)
    assert response.status_code == 404
    app_logs = "\n".join(
        record.getMessage() + str(getattr(record, "path", ""))
        for record in caplog.records
        if record.name == "app.http"
    )
    assert marker not in app_logs and query not in app_logs


def test_parser_slots_are_shared_across_postgresql_connections(client, postgres):
    for uid in (983_006, 983_007, 983_008):
        _auth(client, uid)
    with get_session_context() as db1, get_session_context() as db2, get_session_context() as db3:
        acquire_parser_slot(db1, db1.get(User, _user_id(983_006)))
        acquire_parser_slot(db2, db2.get(User, _user_id(983_007)))
        with pytest.raises(NutritionDraftError, match="parser_busy"):
            acquire_parser_slot(db3, db3.get(User, _user_id(983_008)))
        db1.rollback()
        acquire_parser_slot(db3, db3.get(User, _user_id(983_008)))


def test_cancellation_erases_draft_content_and_denies_retrieval(
    client, postgres, synthetic_adapter
):
    headers = _auth(client, 983_009)
    draft = _upload(client, headers).json()
    response = client.post(f"{URL}/{draft['id']}/cancel", headers=headers, json={"revision": 1})
    assert response.status_code == 204
    assert client.get(f"{URL}/{draft['id']}", headers=headers).status_code == 410
    from fitminiapp_api.models.nutrition_import import NutritionImportDraft

    with get_session_context() as db:
        row = db.get(NutritionImportDraft, draft["id"])
        assert row.document == {}
        assert row.resolutions == {}


def test_same_user_cannot_occupy_two_parser_slots(client, postgres):
    _auth(client, 983_010)
    owner_id = _user_id(983_010)
    with get_session_context() as db1, get_session_context() as db2:
        acquire_parser_slot(db1, db1.get(User, owner_id))
        with pytest.raises(NutritionDraftError, match="parser_busy"):
            acquire_parser_slot(db2, db2.get(User, owner_id))


def test_account_deletion_removes_only_owners_drafts_and_attempts(
    client, postgres, synthetic_adapter
):
    from fitminiapp_api.models.nutrition_import import NutritionImportDraft
    from fitminiapp_api.services.accounts import delete_user_cascade

    first = _auth(client, 983_011)
    second = _auth(client, 983_012)
    first_draft = _upload(client, first, key="first-upload-key").json()["id"]
    second_draft = _upload(client, second, key="second-upload-key").json()["id"]
    first_id, second_id = _user_id(983_011), _user_id(983_012)
    with get_session_context() as db:
        delete_user_cascade(db, db.get(User, first_id))
        db.commit()
        assert db.get(NutritionImportDraft, first_draft) is None
        assert db.get(NutritionImportDraft, second_draft) is not None
        assert db.query(NutritionImportUploadAttempt).filter_by(owner_user_id=first_id).count() == 0
        assert (
            db.query(NutritionImportUploadAttempt).filter_by(owner_user_id=second_id).count() == 1
        )


def test_expired_upload_attempts_are_cleaned_without_touching_recent(client, postgres):
    from datetime import UTC, datetime, timedelta

    from fitminiapp_api.services.nutrition_import_limits import expire_upload_attempts

    _auth(client, 983_013)
    owner_id = _user_id(983_013)
    now = datetime.now(UTC).replace(tzinfo=None)
    with get_session_context() as db:
        db.add_all(
            [
                NutritionImportUploadAttempt(
                    owner_user_id=owner_id, created_at=now - timedelta(hours=2)
                ),
                NutritionImportUploadAttempt(owner_user_id=owner_id, created_at=now),
            ]
        )
        db.flush()
        assert expire_upload_attempts(db, now=now) == 1
        db.flush()
        assert db.query(NutritionImportUploadAttempt).filter_by(owner_user_id=owner_id).count() == 1


def test_confirm_rechecks_revoked_session_family(client, postgres):
    from fitminiapp_api.api.v1.nutrition_imports import _lock_active_session
    from fitminiapp_api.db.session import SessionLocal
    from fitminiapp_api.services.jwt import decode_token
    from fitminiapp_api.services.token_service import revoke_refresh_token_family

    headers = _auth(client, 983_014)
    owner_id = _user_id(983_014)
    family_id = decode_token(
        headers["Authorization"].removeprefix("Bearer "), expected_type="access"
    )["sid"]
    with SessionLocal() as stale, SessionLocal() as revoker:
        user = stale.get(User, owner_id)
        revoke_refresh_token_family(revoker, owner_id, family_id)
        with pytest.raises(NutritionDraftError, match="access_revoked"):
            _lock_active_session(stale, user, family_id)
        stale.rollback()
