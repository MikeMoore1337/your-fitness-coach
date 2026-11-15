import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import date, timedelta
from threading import Event

import pytest
from fastapi import HTTPException
from scripts.db_maintenance import NOTES_RECOVERY_HOLD_SQL

from fitminiapp_api.core.timezone import today_in_timezone
from fitminiapp_api.db.session import SessionLocal, engine, get_session_context
from fitminiapp_api.models.nutrition_notes import NutritionNotesConsent
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.schemas.nutrition_notes import NutritionMealNoteUpdate
from fitminiapp_api.services.nutrition_notes import save_note, set_consent


def _auth(client, telegram_id, *, is_coach=False):
    response = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": telegram_id, "is_coach": is_coach}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_private_notes_require_consent_and_revoke_removes_them(client):
    owner = _auth(client, 956001)
    other = _auth(client, 956002)
    day = date(2026, 1, 1)
    endpoint = f"/api/v1/nutrition-notes/{day}/breakfast"
    payload = {"hunger_before": "none", "note": "Личная заметка"}

    assert client.put(endpoint, json=payload, headers=owner).status_code == 403
    assert client.post("/api/v1/nutrition-notes/consent/enable", headers=owner).status_code == 200
    saved = client.put(endpoint, json=payload, headers=owner)
    assert saved.status_code == 200
    assert saved.json()["hunger_before"] == "none"
    assert saved.json()["fullness_after"] is None
    assert "no-store" in saved.headers["cache-control"]
    original_timezone = saved.json()["timezone_at_entry"]
    with get_session_context() as db:
        account = db.query(User).filter_by(telegram_user_id=956001).one()
        account.profile.timezone = "UTC"
    partial = client.put(endpoint, json={"fullness_after": "low"}, headers=owner)
    assert partial.status_code == 200
    assert partial.json()["timezone_at_entry"] == original_timezone
    assert partial.json()["hunger_before"] == "none"
    assert partial.json()["note"] == payload["note"]
    cleared = client.put(endpoint, json={"fullness_after": None}, headers=owner)
    assert cleared.json()["hunger_before"] == "none"
    assert cleared.json()["note"] == payload["note"]
    long_note = "секрет" * 100
    invalid = client.put(endpoint, json={"note": long_note}, headers=owner)
    assert invalid.status_code == 422
    assert long_note not in invalid.text
    assert client.get(f"/api/v1/nutrition-notes/{day}", headers=other).status_code == 403
    client.post("/api/v1/nutrition-notes/consent/enable", headers=other)
    assert client.get(f"/api/v1/nutrition-notes/{day}", headers=other).json() == []
    exported = client.get("/api/v1/me/export", headers=owner)
    assert exported.status_code == 200
    assert exported.json()["nutrition_meal_notes"][0]["note"] == payload["note"]
    assert client.post("/api/v1/nutrition-notes/consent/disable", headers=owner).status_code == 200
    assert client.get(f"/api/v1/nutrition-notes/{day}", headers=owner).status_code == 403
    assert client.post("/api/v1/nutrition-notes/consent/enable", headers=owner).status_code == 200
    assert len(client.get(f"/api/v1/nutrition-notes/{day}", headers=owner).json()) == 1
    assert client.post("/api/v1/nutrition-notes/consent/revoke", headers=owner).status_code == 200
    assert client.get(f"/api/v1/nutrition-notes/{day}", headers=owner).status_code == 403
    client.post("/api/v1/nutrition-notes/consent/enable", headers=owner)
    assert client.get(f"/api/v1/nutrition-notes/{day}", headers=owner).json() == []


def test_recovery_hold_denies_notes_and_export_until_deleted(client):
    owner = _auth(client, 956003)
    day = date(2026, 1, 1)
    client.post("/api/v1/nutrition-notes/consent/enable", headers=owner)
    endpoint = f"/api/v1/nutrition-notes/{day}/breakfast"
    assert client.put(endpoint, json={"note": "Старый снимок"}, headers=owner).status_code == 200
    with get_session_context() as db:
        user = db.query(User).filter_by(telegram_user_id=956003).one()
        db.query(NutritionNotesConsent).filter_by(user_id=user.id).one().status = "recovery_hold"
    assert client.get(f"/api/v1/nutrition-notes/{day}", headers=owner).status_code == 403
    assert client.post("/api/v1/nutrition-notes/consent/enable", headers=owner).status_code == 409
    assert client.get("/api/v1/me/export", headers=owner).json()["nutrition_meal_notes"] == []
    assert client.post("/api/v1/nutrition-notes/consent/revoke", headers=owner).status_code == 200
    assert client.post("/api/v1/nutrition-notes/consent/enable", headers=owner).status_code == 200
    assert client.get(f"/api/v1/nutrition-notes/{day}", headers=owner).json() == []


def test_active_coach_report_does_not_include_personal_notes(client):
    owner = _auth(client, 956006)
    coach = _auth(client, 956007, is_coach=True)
    client.post("/api/v1/nutrition-notes/consent/enable", headers=owner)
    note = "Личная отметка только для владельца"
    assert (
        client.put(
            "/api/v1/nutrition-notes/2026-01-01/lunch", json={"note": note}, headers=owner
        ).status_code
        == 200
    )
    with get_session_context() as db:
        owner_user = db.query(User).filter_by(telegram_user_id=956006).one()
        coach_user = db.query(User).filter_by(telegram_user_id=956007).one()
        client_id = owner_user.id
        db.add(CoachClient(coach_user_id=coach_user.id, client_user_id=client_id, status="active"))
    report = client.get(f"/api/v1/coach/clients/{client_id}/nutrition-report", headers=coach)
    assert report.status_code == 200
    assert note not in report.text
    assert "nutrition_meal_notes" not in report.text
    assert client.get("/api/v1/nutrition-notes/2026-01-01", headers=coach).status_code == 403


def test_deleted_note_invalidates_existing_export_and_csv_is_formula_safe(client):
    owner = _auth(client, 956008)
    client.post("/api/v1/nutrition-notes/consent/enable", headers=owner)
    endpoint = "/api/v1/nutrition-notes/2026-01-01/lunch"
    assert client.put(endpoint, json={"note": "=1+2"}, headers=owner).status_code == 200
    created = client.post("/api/v1/me/exports", headers=owner)
    assert created.status_code == 201
    export_id = created.json()["export_id"]
    download = f"/api/v1/me/exports/{export_id}/download"
    archive = client.get(download, headers=owner)
    with zipfile.ZipFile(io.BytesIO(archive.content)) as file:
        assert "'=1+2" in file.read("nutrition-meal-notes.csv").decode("utf-8-sig")
    assert client.delete(endpoint, headers=owner).status_code == 204
    assert client.get(download, headers=owner).status_code == 410


def test_copy_day_never_copies_personal_notes(client):
    owner = _auth(client, 956009)
    today = today_in_timezone("Europe/Moscow")
    source = today - timedelta(days=1)
    assert client.post("/api/v1/nutrition-notes/consent/enable", headers=owner).status_code == 200
    assert (
        client.put(
            f"/api/v1/nutrition-notes/{source}/breakfast",
            json={"note": "Личная отметка"},
            headers=owner,
        ).status_code
        == 200
    )
    entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=owner,
        json={
            "quick_add": {"energy_kcal": "320"},
            "diary_date": str(source),
            "meal_type": "breakfast",
            "amount": "1",
            "amount_unit": "serving",
        },
    )
    assert entry.status_code == 201
    body = {"source_date": str(source), "target_date": str(today)}
    preview = client.post("/api/v1/nutrition/diary/copy/day/preview", headers=owner, json=body)
    assert preview.status_code == 200
    copied = client.post(
        "/api/v1/nutrition/diary/copy/day",
        headers={**owner, "Idempotency-Key": "notes-copy-test"},
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert copied.status_code == 201
    assert "Личная отметка" not in copied.text
    assert client.get(f"/api/v1/nutrition-notes/{today}", headers=owner).json() == []
    assert len(client.get(f"/api/v1/nutrition-notes/{source}", headers=owner).json()) == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_revoke_serializes_against_a_pending_write(client):
    owner = _auth(client, 956004)
    client.post("/api/v1/nutrition-notes/consent/enable", headers=owner)
    started = Event()
    with SessionLocal() as db:
        user = db.query(User).filter_by(telegram_user_id=956004).one()
        db.query(User.id).filter_by(id=user.id).with_for_update().one()

        def save_after_lock():
            with SessionLocal() as writer:
                target = writer.get(User, user.id)
                started.set()
                try:
                    save_note(
                        writer,
                        target,
                        date(2026, 1, 1),
                        "breakfast",
                        NutritionMealNoteUpdate(note="test"),
                    )
                except HTTPException as error:
                    return error.status_code
                return 200

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(save_after_lock)
            assert started.wait(5)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.2)
            set_consent(db, user, "revoke")
            assert future.result(timeout=5) == 403


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL")
def test_recovery_hold_sql_blocks_restored_notes(client):
    owner = _auth(client, 956005)
    client.post("/api/v1/nutrition-notes/consent/enable", headers=owner)
    endpoint = "/api/v1/nutrition-notes/2026-01-01/breakfast"
    assert (
        client.put(endpoint, json={"note": "Запись до восстановления"}, headers=owner).status_code
        == 200
    )
    export = client.post("/api/v1/me/exports", headers=owner)
    assert export.status_code == 201
    download = f"/api/v1/me/exports/{export.json()['export_id']}/download"
    with engine.begin() as connection:
        connection.exec_driver_sql(NOTES_RECOVERY_HOLD_SQL.decode())
    assert client.get("/api/v1/nutrition-notes/2026-01-01", headers=owner).status_code == 403
    assert client.get("/api/v1/me/export", headers=owner).json()["nutrition_meal_notes"] == []
    assert client.get(download, headers=owner).status_code == 410
