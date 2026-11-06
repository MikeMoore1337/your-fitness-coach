from __future__ import annotations

from datetime import timedelta
from io import BytesIO

import pytest
from PIL import Image

from fitminiapp_api.api.v1 import nutrition as nutrition_api
from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.photo_meal import PhotoMealDraft
from fitminiapp_api.models.user import User
from fitminiapp_api.nutrition_label.meal_vision import (
    MealVisionCandidateExtraction,
    MealVisionExtraction,
)
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
    assert adapter.calls == 1
    draft_id = first.json()["draft_id"]
    cancelled = client.post(
        f"/api/v1/nutrition/photo-meals/{draft_id}/cancel?revision=1", headers=headers
    )
    assert cancelled.status_code == 204
    with get_session_context() as db:
        user_id = _user_id(516_010)
        assert db.query(PhotoMealDraft).filter_by(user_id=user_id).one().status == "cancelled"
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0


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
        assert db.query(PhotoMealDraft).filter_by(user_id=user_id).one().status == "expired"
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0


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
