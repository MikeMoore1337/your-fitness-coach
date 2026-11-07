from __future__ import annotations

import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from random import Random
from threading import Barrier, Event
from time import monotonic, sleep

import pytest
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from fitminiapp_api.api.v1 import nutrition as nutrition_api
from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.lifecycle_milestone import LifecycleMilestone
from fitminiapp_api.models.photo_meal import PhotoMealDraft
from fitminiapp_api.models.user import User
from fitminiapp_api.nutrition_label.meal_vision import (
    MealVisionCandidateExtraction,
    MealVisionExtraction,
)
from fitminiapp_api.services import food_diary as food_diary_service
from fitminiapp_api.services import photo_meal as photo_meal_service
from fitminiapp_api.services import worker
from fitminiapp_api.services.accounts import delete_user_cascade


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_id(telegram_user_id: int) -> int:
    with get_session_context() as db:
        return db.query(User).filter(User.telegram_user_id == telegram_user_id).one().id


def _meal_image() -> bytes:
    image = Image.new("RGB", (128, 128), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class _FakeMealVisionAdapter:
    provider_class = "test_provider"
    model_class = "test_model"
    prompt_version = "test-photo-meal-v1"

    def __init__(self, extraction: MealVisionExtraction) -> None:
        self.extraction = extraction
        self.calls = 0

    def recognize(
        self,
        normalized_png: bytes,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        assert normalized_png.startswith(b"\x89PNG\r\n\x1a\n")
        assert timeout_seconds <= 8
        assert max_response_bytes > 0
        self.calls += 1
        return self.extraction.model_dump_json().encode()


def _extraction(*, confidence: str = "high") -> MealVisionExtraction:
    return MealVisionExtraction(
        candidates=[
            MealVisionCandidateExtraction(
                name="Курица с рисом",
                portion_amount=250,
                portion_unit="g",
                portion_confidence=confidence,
                identity_confidence=confidence,
                nutrition_confidence=confidence,
                energy_kcal=420,
                protein_g=34,
                fat_g=12,
                carbs_g=38,
            ),
            MealVisionCandidateExtraction(
                name="Овощи",
                portion_amount=None,
                portion_unit=None,
                portion_confidence="unknown",
                identity_confidence="medium",
                nutrition_confidence="low",
                energy_kcal=80,
                protein_g=None,
                fat_g=None,
                carbs_g=None,
            ),
        ],
        warnings=["identity_uncertain"],
    )


def _enable_photo_meal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "nutrition_label_scan_enabled", True)
    monkeypatch.setattr(settings, "nutrition_label_scan_kill_switch", False)


def test_photo_meal_accepts_near_limit_image_through_real_api(client, monkeypatch) -> None:
    headers = _auth(client, 516_024)
    _enable_photo_meal(monkeypatch)
    adapter = _FakeMealVisionAdapter(_extraction())
    monkeypatch.setattr(nutrition_api, "build_meal_vision_adapter", lambda: adapter)
    image = Image.frombytes("RGB", (576, 576), Random(955).randbytes(576 * 576 * 3))
    output = BytesIO()
    image.save(output, format="PNG")
    data = output.getvalue()
    assert 990_000 < len(data) <= 1_000_000
    response = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-limit-955"},
        files={"image": ("meal-photo", data, "image/png")},
    )
    assert response.status_code == 201, response.text
    assert adapter.calls == 1


def _draft_and_confirmation(client, monkeypatch, telegram_user_id: int):
    headers = _auth(client, telegram_user_id)
    _enable_photo_meal(monkeypatch)
    monkeypatch.setattr(
        nutrition_api, "build_meal_vision_adapter", lambda: _FakeMealVisionAdapter(_extraction())
    )
    response = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": f"photo-confirm-{telegram_user_id}"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )
    assert response.status_code == 201, response.text
    draft = response.json()
    fields = (
        "candidate_id",
        "name",
        "portion_amount",
        "portion_unit",
        "energy_kcal",
        "protein_g",
        "fat_g",
        "carbs_g",
    )
    payload = {
        "revision": draft["revision"],
        "diary_date": str(now_msk_naive().date()),
        "meal_type": "lunch",
        "items": [{key: candidate[key] for key in fields} for candidate in draft["candidates"]],
    }
    return headers, draft["draft_id"], payload


def _wait_for_db_lock(query_fragment: str) -> bool:
    deadline = monotonic() + 8
    while monotonic() < deadline:
        with engine.connect() as connection:
            waiting = connection.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                    "AND wait_event_type = 'Lock' AND query LIKE :pattern)"
                ),
                {"pattern": f"%{query_fragment}%"},
            ).scalar()
        if waiting:
            return True
        sleep(0.05)
    return False


def test_photo_confirm_replays_exact_request_and_preserves_unknown_mass(
    client, monkeypatch
) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_013)
    url = f"/api/v1/nutrition/photo-meals/{draft_id}/confirm"
    first = client.post(url, headers=headers, json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["replayed"] is False
    assert first.json()["entry"]["weight_g"] is None
    assert first.json()["entry"]["serving_weight_g"] is None
    replay_payload = {**payload, "items": [dict(item) for item in payload["items"]]}
    replay_payload["items"][0]["portion_amount"] = 250
    replay = client.post(url, headers=headers, json=replay_payload)
    assert replay.status_code == 201, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["entry"] == first.json()["entry"]
    changed = {**payload, "items": [dict(item) for item in payload["items"]]}
    changed["items"][0]["portion_amount"] = "251"
    assert client.post(url, headers=headers, json=changed).status_code == 409
    assert client.post(url, headers=_auth(client, 516_099), json=payload).status_code == 404
    with get_session_context() as db:
        user_id = _user_id(516_013)
        entry = db.query(FoodDiaryEntry).filter_by(user_id=user_id).one()
        draft = db.get(PhotoMealDraft, draft_id)
        assert entry.weight_g is None and entry.serving_weight_g is None
        assert entry.energy_kcal_per_100g is None and entry.protein_g_per_100g is None
        assert entry.fat_g_per_100g is None and entry.carbs_g_per_100g is None
        assert entry.nutrition_snapshot["candidates"][1]["portion_amount"] is None
        assert draft.status == "confirmed" and draft.confirmed_entry_id == entry.id


def test_photo_confirm_rolls_back_after_diary_creation_failure(client, monkeypatch) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_014)
    original = photo_meal_service.create_food_diary_entry

    def interrupt(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure before photo confirmation")

    monkeypatch.setattr(photo_meal_service, "create_food_diary_entry", interrupt)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        client.post(
            f"/api/v1/nutrition/photo-meals/{draft_id}/confirm", headers=headers, json=payload
        )
    with get_session_context() as db:
        user_id = _user_id(516_014)
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0
        assert (
            db.query(LifecycleMilestone)
            .filter_by(user_id=user_id, milestone_type="nutrition_entry_confirmed")
            .count()
            == 0
        )
        assert db.get(PhotoMealDraft, draft_id).status == "draft"
    monkeypatch.setattr(photo_meal_service, "create_food_diary_entry", original)
    retried = client.post(
        f"/api/v1/nutrition/photo-meals/{draft_id}/confirm", headers=headers, json=payload
    )
    assert retried.status_code == 201
    assert retried.json()["replayed"] is False


def test_photo_confirm_rolls_back_if_final_commit_fails(client, monkeypatch) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_018)
    original_commit = Session.commit

    def fail_confirmation_commit(session):
        if any(
            isinstance(row, PhotoMealDraft) and row.status == "confirmed"
            for row in session.identity_map.values()
        ):
            raise RuntimeError("synthetic commit failure")
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_confirmation_commit)
    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        client.post(
            f"/api/v1/nutrition/photo-meals/{draft_id}/confirm", headers=headers, json=payload
        )
    monkeypatch.setattr(Session, "commit", original_commit)
    with get_session_context() as db:
        user_id = _user_id(516_018)
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0
        assert (
            db.query(LifecycleMilestone)
            .filter_by(user_id=user_id, milestone_type="nutrition_entry_confirmed")
            .count()
            == 0
        )
        assert db.get(PhotoMealDraft, draft_id).status == "draft"
    assert (
        client.post(
            f"/api/v1/nutrition/photo-meals/{draft_id}/confirm", headers=headers, json=payload
        ).status_code
        == 201
    )


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_photo_confirm_replays_same_request_once(client, monkeypatch) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_015)
    barrier = Barrier(2)

    def confirm(_index):
        barrier.wait(timeout=10)
        return client.post(
            f"/api/v1/nutrition/photo-meals/{draft_id}/confirm", headers=headers, json=payload
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(confirm, range(2)))
    assert [response.status_code for response in responses] == [201, 201]
    assert sorted(response.json()["replayed"] for response in responses) == [False, True]
    assert responses[0].json()["entry"]["id"] == responses[1].json()["entry"]["id"]
    with get_session_context() as db:
        user_id = _user_id(516_015)
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 1
        assert db.get(PhotoMealDraft, draft_id).status == "confirmed"


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_photo_confirms_with_different_items_conflict(client, monkeypatch) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_019)
    changed = {**payload, "items": [dict(item) for item in payload["items"]]}
    changed["items"][0]["portion_amount"] = "251"
    requests = [payload, changed]
    barrier = Barrier(2)

    def confirm(index):
        barrier.wait(timeout=10)
        return client.post(
            f"/api/v1/nutrition/photo-meals/{draft_id}/confirm",
            headers=headers,
            json=requests[index],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(confirm, range(2)))
    assert sorted(response.status_code for response in responses) == [201, 409]
    winner = next(index for index, response in enumerate(responses) if response.status_code == 201)
    replay = client.post(
        f"/api/v1/nutrition/photo-meals/{draft_id}/confirm", headers=headers, json=requests[winner]
    )
    assert replay.status_code == 201 and replay.json()["replayed"] is True
    with get_session_context() as db:
        user_id = _user_id(516_019)
        entry = db.query(FoodDiaryEntry).filter_by(user_id=user_id).one()
        assert entry.nutrition_snapshot["candidates"][0]["portion_amount"] == str(
            requests[winner]["items"][0]["portion_amount"]
        )


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_photo_cancel_cannot_overwrite_inflight_confirmation(client, monkeypatch) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_020)
    entered = Event()
    release = Event()
    original = photo_meal_service.create_food_diary_entry

    def pause(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=15)
        return original(*args, **kwargs)

    monkeypatch.setattr(photo_meal_service, "create_food_diary_entry", pause)
    with ThreadPoolExecutor(max_workers=2) as executor:
        confirm = executor.submit(
            client.post,
            f"/api/v1/nutrition/photo-meals/{draft_id}/confirm",
            headers=headers,
            json=payload,
        )
        try:
            assert entered.wait(timeout=10)
            cancel = executor.submit(
                client.post,
                f"/api/v1/nutrition/photo-meals/{draft_id}/cancel?revision=1",
                headers=headers,
            )
            assert _wait_for_db_lock("photo_meal_drafts")
        finally:
            release.set()
        assert confirm.result(timeout=15).status_code == 201
        assert cancel.result(timeout=15).status_code == 409
    with get_session_context() as db:
        user_id = _user_id(516_020)
        assert db.get(PhotoMealDraft, draft_id).status == "confirmed"
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_photo_replay_and_diary_deletion_use_consistent_lock_order(client, monkeypatch) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_022)
    url = f"/api/v1/nutrition/photo-meals/{draft_id}/confirm"
    created = client.post(url, headers=headers, json=payload)
    assert created.status_code == 201
    entry_id = created.json()["entry"]["id"]
    entered = Event()
    release = Event()
    original = food_diary_service._lock_diary_user

    def pause_delete(db, user):
        original(db, user)
        entered.set()
        assert release.wait(timeout=15)

    monkeypatch.setattr(food_diary_service, "_lock_diary_user", pause_delete)
    with ThreadPoolExecutor(max_workers=2) as executor:
        deletion = executor.submit(
            client.delete, f"/api/v1/nutrition/diary/entries/{entry_id}", headers=headers
        )
        try:
            assert entered.wait(timeout=10)
            replay = executor.submit(client.post, url, headers=headers, json=payload)
            assert _wait_for_db_lock("users")
        finally:
            release.set()
        assert deletion.result(timeout=15).status_code == 204
        assert replay.result(timeout=15).status_code == 409
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=_user_id(516_022)).count() == 0
        assert db.get(PhotoMealDraft, draft_id).confirmed_entry_id is None


def test_photo_confirm_does_not_reuse_an_orphaned_legacy_entry(client, monkeypatch) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_021)
    old = client.post(
        "/api/v1/nutrition/diary/entries",
        headers={**headers, "Idempotency-Key": f"photo-meal-{draft_id}"},
        json={
            "diary_date": payload["diary_date"],
            "meal_type": payload["meal_type"],
            "amount": "1",
            "amount_unit": "serving",
            "quick_add": {
                "name": "Старая запись",
                "nutrition_source": "photo",
                "energy_kcal": "500",
            },
        },
    )
    assert old.status_code == 201
    assert (
        client.post(
            f"/api/v1/nutrition/photo-meals/{draft_id}/confirm", headers=headers, json=payload
        ).status_code
        == 409
    )
    with get_session_context() as db:
        user_id = _user_id(516_021)
        entry = db.query(FoodDiaryEntry).filter_by(user_id=user_id).one()
        assert entry.id == old.json()["id"] and entry.nutrition_snapshot is None
        assert db.get(PhotoMealDraft, draft_id).status == "draft"


def test_photo_confirm_replay_does_not_recreate_deleted_entry(client, monkeypatch) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_016)
    url = f"/api/v1/nutrition/photo-meals/{draft_id}/confirm"
    first = client.post(url, headers=headers, json=payload)
    assert first.status_code == 201
    entry_id = first.json()["entry"]["id"]
    assert (
        client.delete(f"/api/v1/nutrition/diary/entries/{entry_id}", headers=headers).status_code
        == 204
    )
    assert client.post(url, headers=headers, json=payload).status_code == 409
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=_user_id(516_016)).count() == 0


def test_photo_entry_can_change_meal_without_inventing_mass(client, monkeypatch) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_017)
    response = client.post(
        f"/api/v1/nutrition/photo-meals/{draft_id}/confirm", headers=headers, json=payload
    )
    assert response.status_code == 201
    entry_id = response.json()["entry"]["id"]
    updated = client.patch(
        f"/api/v1/nutrition/diary/entries/{entry_id}", headers=headers, json={"meal_type": "dinner"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["weight_g"] is None
    assert updated.json()["serving_weight_g"] is None
    assert updated.json()["nutrition"] == response.json()["entry"]["nutrition"]
    assert (
        client.post(
            f"/api/v1/nutrition/photo-meals/{draft_id}/confirm", headers=headers, json=payload
        ).status_code
        == 409
    )


def test_copying_photo_entry_preserves_unknown_mass_and_totals(client, monkeypatch) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_023)
    confirmed = client.post(
        f"/api/v1/nutrition/photo-meals/{draft_id}/confirm", headers=headers, json=payload
    )
    assert confirmed.status_code == 201, confirmed.text
    entry = confirmed.json()["entry"]
    request = {
        "source_entry_id": entry["id"],
        "source_date": payload["diary_date"],
        "source_meal_type": payload["meal_type"],
        "target_date": payload["diary_date"],
        "target_meal_type": "dinner",
    }
    preview = client.post(
        "/api/v1/nutrition/diary/copy/product/preview", headers=headers, json=request
    )
    assert preview.status_code == 200, preview.text
    copied = client.post(
        "/api/v1/nutrition/diary/copy/product",
        headers={**headers, "Idempotency-Key": "copy-photo-955"},
        json={**request, "preview_token": preview.json()["preview_token"]},
    )
    assert copied.status_code == 201, copied.text
    copied_entry = copied.json()["entries"][0]
    assert copied_entry["weight_g"] is None and copied_entry["serving_weight_g"] is None
    assert copied_entry["nutrition"] == entry["nutrition"]


def test_photo_meal_is_review_only_until_explicit_confirmation(client, monkeypatch) -> None:
    telegram_user_id = 516_001
    headers = _auth(client, telegram_user_id)
    _enable_photo_meal(monkeypatch)
    adapter = _FakeMealVisionAdapter(_extraction())
    monkeypatch.setattr(nutrition_api, "build_meal_vision_adapter", lambda: adapter)

    draft_response = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-meal-draft-516"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )

    assert draft_response.status_code == 201, draft_response.text
    draft = draft_response.json()
    assert draft["status"] == "draft"
    assert draft["requires_user_review"] is True
    assert draft["source_photo_retained"] is False
    assert "identity_uncertain" in draft["warnings"]
    assert draft["candidates"][0]["uncertainty_codes"] == []
    assert "portion_uncertain" in draft["candidates"][1]["uncertainty_codes"]
    user_id = _user_id(telegram_user_id)
    with get_session_context() as db:
        assert db.query(PhotoMealDraft).filter_by(user_id=user_id).count() == 1
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0
        stored = db.query(PhotoMealDraft).filter_by(user_id=user_id).one()
        assert "normalized_png" not in str(stored.canonical_payload)

    confirm_response = client.post(
        f"/api/v1/nutrition/photo-meals/{draft['draft_id']}/confirm",
        headers=headers,
        json={
            "revision": draft["revision"],
            "diary_date": str(now_msk_naive().date()),
            "meal_type": "lunch",
            "items": [
                {
                    "candidate_id": "food-1",
                    "name": "Курица и рис",
                    "portion_amount": 250,
                    "portion_unit": "g",
                    "energy_kcal": 430,
                    "protein_g": 35,
                    "fat_g": 12,
                    "carbs_g": 39,
                },
                {
                    "candidate_id": "food-2",
                    "name": "Овощи",
                    "portion_amount": None,
                    "portion_unit": None,
                    "energy_kcal": 80,
                    "protein_g": None,
                    "fat_g": None,
                    "carbs_g": None,
                },
            ],
        },
    )

    assert confirm_response.status_code == 201, confirm_response.text
    entry = confirm_response.json()["entry"]
    assert entry["nutrition_source"] == "photo"
    assert entry["nutrition_confidence"] == "partial"
    assert entry["nutrition"]["energy_kcal"] == "510.00"
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 1
        stored = db.query(PhotoMealDraft).filter_by(user_id=user_id).one()
        assert stored.status == "confirmed"
        assert stored.confirmed_entry_id == entry["id"]

    replay = client.post(
        f"/api/v1/nutrition/photo-meals/{draft['draft_id']}/confirm",
        headers=headers,
        json={
            "revision": draft["revision"],
            "diary_date": str(now_msk_naive().date()),
            "meal_type": "lunch",
            "items": [
                {
                    "candidate_id": "food-1",
                    "name": "Курица и рис",
                    "portion_amount": 250,
                    "portion_unit": "g",
                    "energy_kcal": 430,
                    "protein_g": 35,
                    "fat_g": 12,
                    "carbs_g": 39,
                }
            ],
        },
    )
    assert replay.status_code == 409
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 1


def test_photo_meal_fails_closed_when_provider_is_not_available(client, monkeypatch) -> None:
    telegram_user_id = 516_002
    headers = _auth(client, telegram_user_id)
    _enable_photo_meal(monkeypatch)
    monkeypatch.setattr(nutrition_api, "build_meal_vision_adapter", lambda: None)

    response = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-meal-off-516"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "vision_unavailable"
    with get_session_context() as db:
        user_id = _user_id(telegram_user_id)
        assert db.query(PhotoMealDraft).filter_by(user_id=user_id).count() == 0
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0


def test_photo_meal_rejects_confirmation_with_missing_candidates(client, monkeypatch) -> None:
    telegram_user_id = 516_007
    headers = _auth(client, telegram_user_id)
    _enable_photo_meal(monkeypatch)
    monkeypatch.setattr(
        nutrition_api, "build_meal_vision_adapter", lambda: _FakeMealVisionAdapter(_extraction())
    )
    created = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-meal-incomplete-955"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )
    assert created.status_code == 201
    draft = created.json()
    response = client.post(
        f"/api/v1/nutrition/photo-meals/{draft['draft_id']}/confirm",
        headers=headers,
        json={
            "revision": draft["revision"],
            "diary_date": str(now_msk_naive().date()),
            "meal_type": "lunch",
            "items": [{"candidate_id": "food-1", "name": "Курица с рисом", "energy_kcal": 420}],
        },
    )
    assert response.status_code == 422
    with get_session_context() as db:
        user_id = _user_id(telegram_user_id)
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0
        assert db.query(PhotoMealDraft).filter_by(user_id=user_id).one().status == "draft"


def test_photo_meal_unknown_sauce_requires_user_energy_before_confirmation(
    client, monkeypatch
) -> None:
    headers = _auth(client, 516_012)
    _enable_photo_meal(monkeypatch)
    extraction = _extraction()
    extraction.candidates.append(
        MealVisionCandidateExtraction(
            name="Соус или масло",
            portion_confidence="unknown",
            identity_confidence="low",
            nutrition_confidence="unknown",
        )
    )
    monkeypatch.setattr(
        nutrition_api, "build_meal_vision_adapter", lambda: _FakeMealVisionAdapter(extraction)
    )
    created = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-unknown-sauce-955"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )
    assert created.status_code == 201
    draft = created.json()
    sauce = draft["candidates"][2]
    assert sauce["portion_amount"] is None and sauce["portion_unit"] is None
    assert sauce["energy_kcal"] is None and sauce["fat_g"] is None
    assert set(sauce["uncertainty_codes"]) == {
        "identity_uncertain",
        "portion_uncertain",
        "nutrition_uncertain",
    }
    response = client.post(
        f"/api/v1/nutrition/photo-meals/{draft['draft_id']}/confirm",
        headers=headers,
        json={
            "revision": draft["revision"],
            "diary_date": str(now_msk_naive().date()),
            "meal_type": "lunch",
            "items": [
                {
                    "candidate_id": item["candidate_id"],
                    "name": item["name"],
                    "energy_kcal": item["energy_kcal"],
                }
                for item in draft["candidates"]
            ],
        },
    )
    assert response.status_code == 422
    with get_session_context() as db:
        user_id = _user_id(516_012)
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0


def test_photo_meal_uses_manual_fallback_for_low_confidence_results(client, monkeypatch) -> None:
    telegram_user_id = 516_003
    headers = _auth(client, telegram_user_id)
    _enable_photo_meal(monkeypatch)
    monkeypatch.setattr(
        nutrition_api,
        "build_meal_vision_adapter",
        lambda: _FakeMealVisionAdapter(_extraction(confidence="low")),
    )

    response = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-meal-low-516"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "manual_fallback_required"
    with get_session_context() as db:
        user_id = _user_id(telegram_user_id)
        assert db.query(PhotoMealDraft).filter_by(user_id=user_id).count() == 0


def test_photo_meal_draft_is_owner_scoped(client, monkeypatch) -> None:
    owner_headers = _auth(client, 516_004)
    other_headers = _auth(client, 516_005)
    _enable_photo_meal(monkeypatch)
    monkeypatch.setattr(
        nutrition_api,
        "build_meal_vision_adapter",
        lambda: _FakeMealVisionAdapter(_extraction()),
    )
    created = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**owner_headers, "Idempotency-Key": "photo-meal-owner-516"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )
    draft_id = created.json()["draft_id"]

    denied = client.get(f"/api/v1/nutrition/photo-meals/{draft_id}", headers=other_headers)
    assert denied.status_code == 404
    denied_cancel = client.post(
        f"/api/v1/nutrition/photo-meals/{draft_id}/cancel?revision=1", headers=other_headers
    )
    assert denied_cancel.status_code == 404
    denied_confirm = client.post(
        f"/api/v1/nutrition/photo-meals/{draft_id}/confirm",
        headers=other_headers,
        json={
            "revision": 1,
            "diary_date": str(now_msk_naive().date()),
            "meal_type": "lunch",
            "items": [{"candidate_id": "food-1", "name": "Рис", "energy_kcal": 100}],
        },
    )
    assert denied_confirm.status_code == 404


@pytest.mark.parametrize("case", ["mime", "invalid", "oversized", "tiny"])
def test_photo_meal_rejects_bad_images_before_provider(client, monkeypatch, case: str) -> None:
    headers = _auth(client, 516_008)
    _enable_photo_meal(monkeypatch)
    adapter = _FakeMealVisionAdapter(_extraction())
    monkeypatch.setattr(nutrition_api, "build_meal_vision_adapter", lambda: adapter)
    image = _meal_image()
    mime = "image/png"
    expected = {
        "mime": "unsupported_mime",
        "invalid": "invalid_image",
        "oversized": "oversized_image",
        "tiny": "retake_required",
    }[case]
    if case == "mime":
        mime = "text/plain"
    elif case == "invalid":
        image = b"not an image"
    elif case == "oversized":
        monkeypatch.setattr(settings, "nutrition_label_scan_max_image_bytes", 100)
    else:
        output = BytesIO()
        Image.new("RGB", (32, 32), "white").save(output, format="PNG")
        image = output.getvalue()
    response = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-bad-image-955"},
        files={"image": ("image", image, mime)},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == expected
    assert adapter.calls == 0
    with get_session_context() as db:
        user_id = _user_id(516_008)
        assert db.query(PhotoMealDraft).filter_by(user_id=user_id).count() == 0
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0


@pytest.mark.parametrize(
    ("error", "code"), [(TimeoutError, "vision_timeout"), (OSError, "vision_unavailable")]
)
def test_photo_meal_provider_failure_creates_no_draft(
    client, monkeypatch, error, code: str
) -> None:
    headers = _auth(client, 516_009)
    _enable_photo_meal(monkeypatch)
    adapter = _FakeMealVisionAdapter(_extraction())

    def fail(*_args, **_kwargs):
        raise error()

    monkeypatch.setattr(adapter, "recognize", fail)
    monkeypatch.setattr(nutrition_api, "build_meal_vision_adapter", lambda: adapter)
    response = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-failure-955"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == code
    with get_session_context() as db:
        user_id = _user_id(516_009)
        assert db.query(PhotoMealDraft).filter_by(user_id=user_id).count() == 0
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0


def test_photo_meal_creation_replay_and_cancel_do_not_write_diary(client, monkeypatch) -> None:
    headers = _auth(client, 516_010)
    _enable_photo_meal(monkeypatch)
    adapter = _FakeMealVisionAdapter(_extraction())
    monkeypatch.setattr(nutrition_api, "build_meal_vision_adapter", lambda: adapter)
    request = {
        "headers": {**headers, "Idempotency-Key": "photo-retry-955"},
        "files": {"image": ("meal.png", _meal_image(), "image/png")},
    }
    first = client.post("/api/v1/nutrition/photo-meals", **request)
    replay = client.post("/api/v1/nutrition/photo-meals", **request)
    assert first.status_code == replay.status_code == 201
    assert first.json()["draft_id"] == replay.json()["draft_id"]
    changed = BytesIO()
    Image.new("RGB", (128, 128), "red").save(changed, format="PNG")
    conflict = client.post(
        "/api/v1/nutrition/photo-meals",
        headers=request["headers"],
        files={"image": ("other.png", changed.getvalue(), "image/png")},
    )
    assert conflict.status_code == 409
    assert adapter.calls == 1
    draft_id = first.json()["draft_id"]
    with get_session_context() as db:
        stored = db.get(PhotoMealDraft, draft_id).canonical_payload
        fingerprint = stored["image_hmac"]
        assert fingerprint != hashlib.sha256(_meal_image()).hexdigest()
        assert fingerprint not in first.text
    cancelled = client.post(
        f"/api/v1/nutrition/photo-meals/{draft_id}/cancel?revision=1", headers=headers
    )
    assert cancelled.status_code == 204
    with get_session_context() as db:
        user_id = _user_id(516_010)
        assert db.query(PhotoMealDraft).filter_by(user_id=user_id).one().status == "cancelled"
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0


def test_photo_meal_legacy_draft_without_fingerprint_fails_closed(client, monkeypatch) -> None:
    headers, draft_id, _ = _draft_and_confirmation(client, monkeypatch, 516_025)
    with get_session_context() as db:
        row = db.get(PhotoMealDraft, draft_id)
        row.canonical_payload = {
            k: v for k, v in row.canonical_payload.items() if k != "image_hmac"
        }
    replay = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-confirm-516025"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )
    assert replay.status_code == 409


def test_photo_meal_fingerprints_are_scoped_to_owner_and_request(client, monkeypatch) -> None:
    _enable_photo_meal(monkeypatch)
    monkeypatch.setattr(
        nutrition_api, "build_meal_vision_adapter", lambda: _FakeMealVisionAdapter(_extraction())
    )
    first_owner = _auth(client, 516_030)
    second_owner = _auth(client, 516_031)
    fingerprints = []
    for headers, key in (
        (first_owner, "photo-scope-one"),
        (first_owner, "photo-scope-two"),
        (second_owner, "photo-scope-one"),
    ):
        created = client.post(
            "/api/v1/nutrition/photo-meals",
            headers={**headers, "Idempotency-Key": key},
            files={"image": ("meal.png", _meal_image(), "image/png")},
        )
        assert created.status_code == 201, created.text
        with get_session_context() as db:
            fingerprint = db.get(PhotoMealDraft, created.json()["draft_id"]).canonical_payload[
                "image_hmac"
            ]
        assert fingerprint not in created.text
        fingerprints.append(fingerprint)
    assert len(set(fingerprints)) == 3


def test_photo_meal_database_failure_does_not_log_fingerprint(client, monkeypatch, caplog) -> None:
    headers = _auth(client, 516_036)
    _enable_photo_meal(monkeypatch)
    monkeypatch.setattr(
        nutrition_api, "build_meal_vision_adapter", lambda: _FakeMealVisionAdapter(_extraction())
    )
    original_commit = Session.commit
    fingerprints = []

    def fail_on_create(session):
        for row in session.new:
            if isinstance(row, PhotoMealDraft):
                fingerprints.append(row.canonical_payload["image_hmac"])
                raise SQLAlchemyError(f"synthetic database error {fingerprints[-1]}")
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_on_create)
    response = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-db-error-955"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )
    assert response.status_code == 503
    assert len(fingerprints) == 1
    assert fingerprints[0] not in response.text
    assert fingerprints[0] not in caplog.text


def test_photo_confirm_database_failure_does_not_log_fingerprint(
    client, monkeypatch, caplog
) -> None:
    headers, draft_id, payload = _draft_and_confirmation(client, monkeypatch, 516_037)
    original_flush = Session.flush
    fingerprints = []

    def fail_confirmation(session, *args, **kwargs):
        for row in session.dirty:
            if isinstance(row, PhotoMealDraft) and row.status == "confirmed":
                fingerprints.append(row.canonical_payload["image_hmac"])
                raise SQLAlchemyError(f"synthetic database error {fingerprints[-1]}")
        return original_flush(session, *args, **kwargs)

    monkeypatch.setattr(Session, "flush", fail_confirmation)
    response = client.post(
        f"/api/v1/nutrition/photo-meals/{draft_id}/confirm", headers=headers, json=payload
    )
    assert response.status_code == 503
    assert len(fingerprints) == 1
    assert fingerprints[0] not in response.text
    assert fingerprints[0] not in caplog.text
    with get_session_context() as db:
        assert db.get(PhotoMealDraft, draft_id).status == "draft"
        assert db.query(FoodDiaryEntry).filter_by(user_id=_user_id(516_037)).count() == 0


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL locks")
@pytest.mark.parametrize("same_image", [True, False])
def test_concurrent_photo_creations_match_the_actual_image(client, monkeypatch, same_image) -> None:
    headers = _auth(client, 516_026)
    _enable_photo_meal(monkeypatch)
    entered = Event()
    release = Event()
    adapter = _FakeMealVisionAdapter(_extraction())
    recognize = adapter.recognize

    def concurrent_recognize(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return recognize(*args, **kwargs)

    monkeypatch.setattr(adapter, "recognize", concurrent_recognize)
    monkeypatch.setattr(nutrition_api, "build_meal_vision_adapter", lambda: adapter)
    second = BytesIO()
    Image.new("RGB", (128, 128), "red").save(second, format="PNG")
    images = [_meal_image(), _meal_image() if same_image else second.getvalue()]

    def create(image):
        return client.post(
            "/api/v1/nutrition/photo-meals",
            headers={**headers, "Idempotency-Key": "photo-race-955"},
            files={"image": ("meal.png", image, "image/png")},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(create, images[0])
        assert entered.wait(timeout=5)
        second_request = pool.submit(create, images[1])
        try:
            assert _wait_for_db_lock("pg_advisory_xact_lock")
        finally:
            release.set()
        responses = [first.result(timeout=15), second_request.result(timeout=15)]
    assert sorted(response.status_code for response in responses) == (
        [201, 201] if same_image else [201, 409]
    )
    if same_image:
        assert responses[0].json()["draft_id"] == responses[1].json()["draft_id"]
    assert adapter.calls == 1
    with get_session_context() as db:
        assert db.query(PhotoMealDraft).filter_by(user_id=_user_id(516_026)).count() == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL locks")
@pytest.mark.parametrize("different_owner", [True, False])
def test_photo_creation_lock_does_not_block_other_requests(
    client, monkeypatch, different_owner
) -> None:
    first_headers = _auth(client, 516_034)
    second_headers = _auth(client, 516_035) if different_owner else first_headers
    _enable_photo_meal(monkeypatch)
    entered = Event()
    release = Event()
    adapter = _FakeMealVisionAdapter(_extraction())
    recognize = adapter.recognize

    def block_first(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(timeout=10)
        return recognize(*args, **kwargs)

    monkeypatch.setattr(adapter, "recognize", block_first)
    monkeypatch.setattr(nutrition_api, "build_meal_vision_adapter", lambda: adapter)

    def create(headers, key):
        return client.post(
            "/api/v1/nutrition/photo-meals",
            headers={**headers, "Idempotency-Key": key},
            files={"image": ("meal.png", _meal_image(), "image/png")},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(create, first_headers, "photo-distinct-one")
        assert entered.wait(timeout=5)
        second_key = "photo-distinct-one" if different_owner else "photo-distinct-two"
        second = pool.submit(create, second_headers, second_key)
        try:
            assert second.result(timeout=5).status_code == 201
        finally:
            release.set()
        assert first.result(timeout=15).status_code == 201
    assert adapter.calls == 2


def test_photo_meal_expired_draft_cannot_be_confirmed(client, monkeypatch) -> None:
    headers = _auth(client, 516_011)
    _enable_photo_meal(monkeypatch)
    monkeypatch.setattr(
        nutrition_api, "build_meal_vision_adapter", lambda: _FakeMealVisionAdapter(_extraction())
    )
    created = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-expired-955"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )
    assert created.status_code == 201
    draft_id = created.json()["draft_id"]
    with get_session_context() as db:
        db.get(PhotoMealDraft, draft_id).expires_at = now_msk_naive() - timedelta(seconds=1)
    response = client.post(
        f"/api/v1/nutrition/photo-meals/{draft_id}/confirm",
        headers=headers,
        json={
            "revision": 1,
            "diary_date": str(now_msk_naive().date()),
            "meal_type": "lunch",
            "items": [{"candidate_id": "food-1", "name": "Рис", "energy_kcal": 100}],
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "draft_expired"
    with get_session_context() as db:
        user_id = _user_id(516_011)
        expired = db.query(PhotoMealDraft).filter_by(user_id=user_id).one()
        assert expired.status == "expired"
        assert expired.canonical_payload == {"retention_cleaned": True}
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0


def test_photo_meal_worker_cleans_expired_drafts_but_keeps_diary(client, monkeypatch) -> None:
    headers, confirmed_id, payload = _draft_and_confirmation(client, monkeypatch, 516_027)
    confirmed = client.post(
        f"/api/v1/nutrition/photo-meals/{confirmed_id}/confirm", headers=headers, json=payload
    )
    assert confirmed.status_code == 201, confirmed.text
    entry_id = confirmed.json()["entry"]["id"]
    _, expired_id, _ = _draft_and_confirmation(client, monkeypatch, 516_028)
    _, fresh_id, _ = _draft_and_confirmation(client, monkeypatch, 516_029)
    cancelled_headers, cancelled_id, _ = _draft_and_confirmation(client, monkeypatch, 516_032)
    cancelled = client.post(
        f"/api/v1/nutrition/photo-meals/{cancelled_id}/cancel?revision=1",
        headers=cancelled_headers,
    )
    assert cancelled.status_code == 204
    with get_session_context() as db:
        for draft_id in (confirmed_id, expired_id, cancelled_id):
            db.get(PhotoMealDraft, draft_id).expires_at = now_msk_naive() - timedelta(seconds=1)

    asyncio.run(worker.run_once(sync_reminders=False))
    with get_session_context() as db:
        confirmed_row = db.get(PhotoMealDraft, confirmed_id)
        expired_row = db.get(PhotoMealDraft, expired_id)
        fresh_row = db.get(PhotoMealDraft, fresh_id)
        assert confirmed_row.status == "confirmed" and confirmed_row.confirmed_entry_id == entry_id
        assert confirmed_row.canonical_payload == {"retention_cleaned": True}
        assert expired_row.status == "expired"
        assert expired_row.canonical_payload == {"retention_cleaned": True}
        cancelled_row = db.get(PhotoMealDraft, cancelled_id)
        assert cancelled_row.status == "cancelled"
        assert cancelled_row.canonical_payload == {"retention_cleaned": True}
        assert "image_hmac" in fresh_row.canonical_payload
        assert db.get(FoodDiaryEntry, entry_id).nutrition_snapshot["kind"] == "photo_meal"
    replay = client.post(
        f"/api/v1/nutrition/photo-meals/{confirmed_id}/confirm", headers=headers, json=payload
    )
    assert replay.status_code == 409
    assert (
        client.get(f"/api/v1/nutrition/photo-meals/{confirmed_id}", headers=headers).status_code
        == 409
    )
    duplicate_create = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-confirm-516027"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )
    assert duplicate_create.status_code == 409
    asyncio.run(worker.run_once(sync_reminders=False))
    with get_session_context() as db:
        assert db.get(PhotoMealDraft, confirmed_id).canonical_payload == {"retention_cleaned": True}
        assert db.get(FoodDiaryEntry, entry_id) is not None


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_photo_meal_cleanup_skips_locked_draft_then_cleans_it(client, monkeypatch) -> None:
    _, draft_id, _ = _draft_and_confirmation(client, monkeypatch, 516_033)
    with get_session_context() as db:
        db.get(PhotoMealDraft, draft_id).expires_at = now_msk_naive() - timedelta(seconds=1)
    with Session(engine) as lock_holder:
        lock_holder.query(PhotoMealDraft).filter_by(id=draft_id).with_for_update().one()
        with get_session_context() as db:
            db.execute(text("SET LOCAL lock_timeout = '2s'"))
            assert photo_meal_service.expire_photo_meal_drafts(db) == 0
        lock_holder.rollback()
    with get_session_context() as db:
        assert photo_meal_service.expire_photo_meal_drafts(db) == 1
    with get_session_context() as db:
        assert db.get(PhotoMealDraft, draft_id).canonical_payload == {"retention_cleaned": True}


def test_photo_meal_draft_is_deleted_with_account(client, monkeypatch) -> None:
    telegram_user_id = 516_006
    headers = _auth(client, telegram_user_id)
    _enable_photo_meal(monkeypatch)
    monkeypatch.setattr(
        nutrition_api,
        "build_meal_vision_adapter",
        lambda: _FakeMealVisionAdapter(_extraction()),
    )
    created = client.post(
        "/api/v1/nutrition/photo-meals",
        headers={**headers, "Idempotency-Key": "photo-meal-delete-516"},
        files={"image": ("meal.png", _meal_image(), "image/png")},
    )
    assert created.status_code == 201, created.text
    user_id = _user_id(telegram_user_id)

    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None
        delete_user_cascade(db, user)
        db.commit()

    with get_session_context() as db:
        assert db.query(PhotoMealDraft).filter_by(user_id=user_id).count() == 0


def test_photo_meal_draft_rejects_body_or_medical_provider_fields() -> None:
    payload = _extraction().model_dump(mode="json")
    payload["body_fat_percent"] = 20
    with pytest.raises(ValueError):
        MealVisionExtraction.model_validate(payload)
