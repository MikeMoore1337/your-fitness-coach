from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from io import BytesIO
from threading import Event, Lock

import pytest
from PIL import Image

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import SessionLocal, engine, get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.nutrition_label import (
    NutritionCatalogContribution,
    NutritionLabelDraft,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.nutrition_label.image import ImageIngressError, normalize_uploaded_image
from fitminiapp_api.nutrition_label.parser import build_draft_from_ocr
from fitminiapp_api.schemas.nutrition_label import NutritionLabelConfirmRequest
from fitminiapp_api.services import nutrition_label as nutrition_label_service
from fitminiapp_api.services.accounts import delete_user_cascade
from fitminiapp_api.services.foods import FoodError, calculate_food_amount, search_foods


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "is_coach": False,
            "is_admin": False,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_id(telegram_user_id: int) -> int:
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == telegram_user_id).one()
        return user.id


def _enable_scan(monkeypatch: pytest.MonkeyPatch, user_id: int) -> None:
    del user_id
    monkeypatch.setattr(settings, "nutrition_label_scan_enabled", True)
    monkeypatch.setattr(settings, "nutrition_label_scan_kill_switch", False)
    monkeypatch.setattr(settings, "nutrition_label_scan_internal_user_ids", "")


def _label_text() -> str:
    return "\n".join(
        (
            "Nutrition Facts",
            "Per 100 g",
            "Energy 250 kcal 1046 kJ",
            "Protein 10 g",
            "Fat 5 g",
            "Carbohydrate 30 g",
            "Sugars 12 g",
            "Salt 0,5 g",
            "Sodium 200 mg",
        )
    )


def _label_image() -> bytes:
    image = Image.new("RGB", (128, 128), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class _FakeOcr:
    name = "local_tesseract"
    version = "synthetic-locked-v1"

    def extract_text(self, image_bytes: bytes) -> str:
        assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        return _label_text()


def _confirm_payload(*, visibility: str = "private", barcode: str | None = None) -> dict:
    return {
        "revision": 1,
        "name": "Тестовый батончик",
        "brand": "YFC Test",
        "barcode": barcode,
        "visibility": visibility,
        "nutrition": {
            "source_basis": "per_100_g",
            "energy_kcal": "250",
            "energy_kj": "1046",
            "protein_g": "10",
            "fat_g": "5",
            "carbohydrate_g": "30",
            "sugars_g": "12",
            "salt_g": "0.5",
            "sodium_mg": "200",
        },
    }


def test_parser_keeps_canonical_basis_units_and_separates_salt_from_sodium() -> None:
    draft = build_draft_from_ocr(_label_text())

    assert draft.source_basis == "per_100_g"
    assert draft.normalized_facts.energy_kcal is not None
    assert draft.normalized_facts.energy_kcal.value == 250
    assert draft.normalized_facts.energy_kj is not None
    assert draft.normalized_facts.energy_kj.value == 1046
    assert draft.normalized_facts.salt_g is not None
    assert draft.normalized_facts.salt_g.value == 0.5
    assert draft.normalized_facts.sodium_mg is not None
    assert draft.normalized_facts.sodium_mg.value == 200
    assert draft.field_evidence.salt_g == "read"
    assert draft.field_evidence.sodium_mg == "read"
    assert "dv_as_mass" not in draft.warnings


def test_parser_refuses_ambiguous_basis_and_does_not_normalize() -> None:
    draft = build_draft_from_ocr(
        "\n".join(
            (
                "Per 100 g and per serving",
                "Energy 250 kcal",
                "Protein 10 g",
                "Fat 5 g",
                "Carbohydrate 30 g",
            )
        )
    )

    assert draft.source_basis == "ambiguous"
    assert draft.normalized_facts.energy_kcal is None
    assert draft.normalized_facts.protein_g is None
    assert draft.source_facts.energy_kcal is not None
    assert draft.source_facts.energy_kcal[0].value is None
    assert draft.source_facts.energy_kcal[0].evidence == "ambiguous"
    assert "ambiguous_basis" in draft.warnings


def test_parser_ignores_zero_serving_size_without_dividing_by_zero() -> None:
    draft = build_draft_from_ocr(
        "\n".join(
            (
                "Per serving",
                "Serving size 0 g",
                "Energy 250 kcal",
                "Protein 10 g",
                "Fat 5 g",
                "Carbohydrate 30 g",
            )
        )
    )

    assert draft.serving_size is None
    assert draft.normalized_facts.energy_kcal is not None
    assert draft.normalized_facts.energy_kcal.value == 250
    assert "serving_size_required_for_normalization" in draft.warnings


def test_basis_aware_food_amount_does_not_guess_density_or_serving_mass() -> None:
    per_ml = build_draft_from_ocr(
        "\n".join(
            (
                "Per 100 ml",
                "Energy 40 kcal",
                "Protein 2 g",
                "Fat 1 g",
                "Carbohydrate 5 g",
            )
        )
    )
    ml_food = Food(canonical_facts=per_ml.model_dump(mode="json"))
    ml_amount = calculate_food_amount(ml_food, Decimal("250"), "ml")
    assert ml_amount.weight_g is None
    assert ml_amount.energy_kcal == Decimal("100.00")
    assert ml_amount.protein_g == Decimal("5.000")
    with pytest.raises(FoodError, match="grams and millilitres"):
        calculate_food_amount(ml_food, Decimal("250"), "g")

    per_serving = build_draft_from_ocr(
        "\n".join(
            (
                "Per serving",
                "Energy 250 kcal",
                "Protein 10 g",
                "Fat 5 g",
                "Carbohydrate 30 g",
            )
        )
    )
    serving_food = Food(canonical_facts=per_serving.model_dump(mode="json"))
    serving_amount = calculate_food_amount(serving_food, Decimal("2"), "serving")
    assert serving_amount.weight_g is None
    assert serving_amount.energy_kcal == Decimal("500.00")
    with pytest.raises(FoodError, match="serving mass or volume"):
        calculate_food_amount(serving_food, Decimal("100"), "g")

    per_serving = build_draft_from_ocr(
        "\n".join(
            (
                "Per serving",
                "Serving size 50 g",
                "Energy 250 kcal",
                "Protein 10 g",
                "Fat 5 g",
                "Carbohydrate 30 g",
            )
        )
    )
    serving_with_mass = Food(canonical_facts=per_serving.model_dump(mode="json"))
    serving_amount = calculate_food_amount(serving_with_mass, Decimal("2"), "serving")
    assert serving_amount.weight_g == Decimal("100.000")
    assert serving_amount.energy_kcal == Decimal("500.00")


def test_image_ingress_requires_matching_magic_and_bounds_pixels() -> None:
    data = _label_image()
    normalized = normalize_uploaded_image(
        data,
        "image/png",
        max_bytes=8 * 1024 * 1024,
        max_pixels=20_000_000,
    )
    assert normalized.mime == "image/png"
    assert normalized.width == 128
    assert normalized.height == 128

    with pytest.raises(ImageIngressError, match="invalid_image"):
        normalize_uploaded_image(
            data,
            "image/jpeg",
            max_bytes=8 * 1024 * 1024,
            max_pixels=20_000_000,
        )

    with pytest.raises(ImageIngressError, match="retake_required"):
        normalize_uploaded_image(
            _small_png(),
            "image/png",
            max_bytes=8 * 1024 * 1024,
            max_pixels=20_000_000,
        )


def _small_png() -> bytes:
    image = Image.new("RGB", (32, 32), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_scan_is_disabled_by_default_and_does_not_invoke_ocr(client, monkeypatch) -> None:
    headers = _auth(client, 128_101)

    def fail_if_called() -> _FakeOcr:
        raise AssertionError("OCR must not run while the feature flag is disabled")

    monkeypatch.setattr(nutrition_label_service, "_build_ocr_engine", fail_if_called)
    response = client.post(
        "/api/v1/nutrition/label-scans",
        headers={**headers, "Idempotency-Key": "disabled-scan-1"},
        files={"image": ("label.png", _label_image(), "image/png")},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "feature_disabled"


def test_enabled_scan_is_available_to_accounts_without_internal_allowlist(
    client, monkeypatch
) -> None:
    telegram_user_id = 128_115
    headers = _auth(client, telegram_user_id)
    _enable_scan(monkeypatch, _user_id(telegram_user_id))
    monkeypatch.setattr(nutrition_label_service, "_build_ocr_engine", lambda: _FakeOcr())

    response = client.post(
        "/api/v1/nutrition/label-scans",
        headers={**headers, "Idempotency-Key": "public-rollout-128"},
        files={"image": ("label.png", _label_image(), "image/png")},
    )

    assert response.status_code == 201, response.text


def test_scan_creates_owner_draft_without_food_or_diary_write(client, monkeypatch) -> None:
    telegram_user_id = 128_102
    headers = _auth(client, telegram_user_id)
    _enable_scan(monkeypatch, _user_id(telegram_user_id))
    monkeypatch.setattr(nutrition_label_service, "_build_ocr_engine", lambda: _FakeOcr())

    response = client.post(
        "/api/v1/nutrition/label-scans",
        headers={**headers, "Idempotency-Key": "draft-scan-128"},
        files={"image": ("label.png", _label_image(), "image/png")},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["nutrition"]["source_basis"] == "per_100_g"
    assert body["requires_user_review"] is True

    with get_session_context() as db:
        user_id = _user_id(telegram_user_id)
        assert db.query(NutritionLabelDraft).filter_by(user_id=user_id).count() == 1
        assert db.query(Food).filter_by(owner_user_id=user_id).count() == 0
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0
        assert db.query(NutritionCatalogContribution).count() == 0

    replay = client.post(
        "/api/v1/nutrition/label-scans",
        headers={**headers, "Idempotency-Key": "draft-scan-128"},
        files={"image": ("label.png", _label_image(), "image/png")},
    )
    assert replay.status_code == 201
    assert replay.json()["draft_id"] == body["draft_id"]


def test_draft_is_owner_scoped_and_confirmation_is_revision_bound(client, monkeypatch) -> None:
    owner_telegram_id = 128_108
    other_telegram_id = 128_109
    owner_headers = _auth(client, owner_telegram_id)
    other_headers = _auth(client, other_telegram_id)
    owner_id = _user_id(owner_telegram_id)
    other_id = _user_id(other_telegram_id)
    _enable_scan(monkeypatch, owner_id)
    monkeypatch.setattr(
        settings,
        "nutrition_label_scan_internal_user_ids",
        f"{owner_id},{other_id}",
    )
    monkeypatch.setattr(nutrition_label_service, "_build_ocr_engine", lambda: _FakeOcr())

    draft = client.post(
        "/api/v1/nutrition/label-scans",
        headers={**owner_headers, "Idempotency-Key": "owner-scan-128"},
        files={"image": ("label.png", _label_image(), "image/png")},
    ).json()
    draft_id = draft["draft_id"]

    assert (
        client.get(f"/api/v1/nutrition/label-scans/{draft_id}", headers=other_headers).status_code
        == 404
    )
    stale = client.post(
        f"/api/v1/nutrition/label-scans/{draft_id}/confirm",
        headers=owner_headers,
        json={**_confirm_payload(), "revision": 2},
    )
    assert stale.status_code == 409

    cancelled = client.post(
        f"/api/v1/nutrition/label-scans/{draft_id}/cancel",
        headers=owner_headers,
        params={"revision": 1},
    )
    assert cancelled.status_code == 204
    closed = client.post(
        f"/api/v1/nutrition/label-scans/{draft_id}/confirm",
        headers=owner_headers,
        json=_confirm_payload(),
    )
    assert closed.status_code == 409

    with get_session_context() as db:
        assert db.query(Food).filter(Food.provenance == "user_confirmed_package").count() == 0


def test_private_confirmation_creates_private_food_but_never_diary_entry(
    client, monkeypatch
) -> None:
    telegram_user_id = 128_103
    headers = _auth(client, telegram_user_id)
    user_id = _user_id(telegram_user_id)
    _enable_scan(monkeypatch, user_id)
    monkeypatch.setattr(nutrition_label_service, "_build_ocr_engine", lambda: _FakeOcr())

    draft = client.post(
        "/api/v1/nutrition/label-scans",
        headers={**headers, "Idempotency-Key": "private-scan-128"},
        files={"image": ("label.png", _label_image(), "image/png")},
    ).json()
    confirmed = client.post(
        f"/api/v1/nutrition/label-scans/{draft['draft_id']}/confirm",
        headers=headers,
        json=_confirm_payload(),
    )

    assert confirmed.status_code == 201, confirmed.text
    body = confirmed.json()
    assert body["visibility"] == "private"
    assert body["contribution_state"] == "private"
    assert body["catalog_quality"] == "private"
    assert body["food"]["food_type"] == "user"
    assert body["food"]["provenance"] == "user"
    assert body["diary_entry_created"] is False
    other_headers = _auth(client, 128_114)
    assert (
        client.get(
            f"/api/v1/nutrition/foods/{body['food']['id']}", headers=other_headers
        ).status_code
        == 404
    )
    other_search = client.get(
        "/api/v1/nutrition/foods/search",
        headers=other_headers,
        params={"q": "Тестовый батончик"},
    )
    assert other_search.status_code == 200, other_search.text
    assert all(item["id"] != body["food"]["id"] for item in other_search.json()["items"])

    with get_session_context() as db:
        assert db.query(Food).filter_by(owner_user_id=user_id).count() == 1
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0
        stored = db.get(NutritionLabelDraft, draft["draft_id"])
        assert stored is not None and stored.status == "confirmed"
        assert stored.confirmed_food_id == body["food"]["id"]
        assert stored.canonical_payload["metadata"]["provider"] == "local_tesseract"
        assert stored.canonical_payload.get("raw_image") is None

    confirmed_draft = client.get(
        f"/api/v1/nutrition/label-scans/{draft['draft_id']}", headers=headers
    )
    assert confirmed_draft.status_code == 200
    assert confirmed_draft.json()["status"] == "confirmed"


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL concurrency")
def test_concurrent_private_confirmations_create_one_food(client, monkeypatch) -> None:
    telegram_user_id = 128_113
    headers = _auth(client, telegram_user_id)
    user_id = _user_id(telegram_user_id)
    _enable_scan(monkeypatch, user_id)
    monkeypatch.setattr(nutrition_label_service, "_build_ocr_engine", lambda: _FakeOcr())

    draft = client.post(
        "/api/v1/nutrition/label-scans",
        headers={**headers, "Idempotency-Key": "concurrent-private-scan-128"},
        files={"image": ("label.png", _label_image(), "image/png")},
    ).json()
    draft_id = draft["draft_id"]

    original_canonical_from_confirmation = nutrition_label_service._canonical_from_confirmation
    first_confirmation_has_lock = Event()
    release_first_confirmation = Event()
    call_count = 0
    call_count_lock = Lock()

    def pause_after_first_lock(*args, **kwargs):
        nonlocal call_count
        with call_count_lock:
            call_count += 1
            is_first = call_count == 1
        if is_first:
            first_confirmation_has_lock.set()
            assert release_first_confirmation.wait(timeout=5)
        return original_canonical_from_confirmation(*args, **kwargs)

    monkeypatch.setattr(
        nutrition_label_service,
        "_canonical_from_confirmation",
        pause_after_first_lock,
    )

    def confirm_in_session() -> str:
        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            assert user is not None
            request = NutritionLabelConfirmRequest.model_validate(_confirm_payload())
            try:
                nutrition_label_service.confirm_label_draft(db, user, draft_id, request)
            except nutrition_label_service.NutritionLabelConflictError as exc:
                db.rollback()
                return str(exc)
            return "confirmed"
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(confirm_in_session)
        assert first_confirmation_has_lock.wait(timeout=5)
        second = executor.submit(confirm_in_session)
        release_first_confirmation.set()
        assert first.result(timeout=5) == "confirmed"
        assert second.result(timeout=5) == "draft_not_active"

    with get_session_context() as db:
        assert db.query(Food).filter_by(owner_user_id=user_id).count() == 1
        stored = db.get(NutritionLabelDraft, draft_id)
        assert stored is not None and stored.status == "confirmed"


def test_shared_confirmation_is_community_unverified_and_visible_by_barcode(
    client, monkeypatch
) -> None:
    telegram_user_id = 128_104
    other_telegram_user_id = 128_105
    headers = _auth(client, telegram_user_id)
    other_headers = _auth(client, other_telegram_user_id)
    _enable_scan(monkeypatch, _user_id(telegram_user_id))
    monkeypatch.setattr(nutrition_label_service, "_build_ocr_engine", lambda: _FakeOcr())

    draft = client.post(
        "/api/v1/nutrition/label-scans",
        headers={**headers, "Idempotency-Key": "shared-scan-128"},
        files={"image": ("label.png", _label_image(), "image/png")},
    ).json()
    confirmed = client.post(
        f"/api/v1/nutrition/label-scans/{draft['draft_id']}/confirm",
        headers=headers,
        json=_confirm_payload(visibility="share_to_yfc_catalog", barcode="4006381333931"),
    )

    assert confirmed.status_code == 201, confirmed.text
    body = confirmed.json()
    assert body["catalog_quality"] == "community_unverified"
    assert body["provenance"] == "user_confirmed_package"
    assert body["food"]["food_type"] == "branded"
    assert body["food"]["barcode"] == "4006381333931"

    food_id = body["food"]["id"]
    visible = client.get(f"/api/v1/nutrition/foods/{food_id}", headers=other_headers)
    assert visible.status_code == 200
    lookup = client.get(
        "/api/v1/nutrition/foods/barcode/4006381333931",
        headers=other_headers,
    )
    assert lookup.status_code == 200
    assert lookup.json()["source"] == "local"
    assert lookup.json()["local_item"]["catalog_quality"] == "community_unverified"
    name_search = client.get(
        "/api/v1/nutrition/foods/search",
        headers=other_headers,
        params={"q": "Тестовый батончик"},
    )
    assert name_search.status_code == 200, name_search.text
    assert any(item["id"] == food_id for item in name_search.json()["items"])

    with get_session_context() as db:
        stored_food = db.get(Food, food_id)
        assert stored_food is not None
        assert stored_food.provenance == "user_confirmed_package"
        assert stored_food.legacy_provenance == "internal"
        contribution = db.query(NutritionCatalogContribution).one()
        assert contribution.state == "accepted"
        assert contribution.visibility == "share_to_yfc_catalog"
        assert db.query(FoodDiaryEntry).filter_by(user_id=_user_id(telegram_user_id)).count() == 0


def test_local_fuzzy_search_ranks_verified_catalog_above_community_candidate() -> None:
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 128_104).one_or_none()
        if user is None:
            user = User(
                telegram_user_id=128_104,
                is_coach=False,
                is_admin=False,
            )
            db.add(user)
            db.flush()
        db.add_all(
            [
                Food(
                    name="Греческий йогурт",
                    brand="Verified",
                    energy_kcal_per_100g=70,
                    protein_g_per_100g=5,
                    fat_g_per_100g=2,
                    carbs_g_per_100g=7,
                    food_type="branded",
                    owner_user_id=None,
                    provenance="internal",
                    source_name="yfc_catalog",
                    trust_level="verified",
                    status="active",
                    catalog_quality="verified",
                ),
                Food(
                    name="Греческий йогурт",
                    brand="Community",
                    energy_kcal_per_100g=70,
                    protein_g_per_100g=5,
                    fat_g_per_100g=2,
                    carbs_g_per_100g=7,
                    food_type="branded",
                    owner_user_id=None,
                    provenance="user_confirmed_package",
                    source_name="yfc_community",
                    source_version="nutrition-label-local-v1",
                    trust_level="unverified",
                    status="active",
                    catalog_quality="community_unverified",
                ),
            ]
        )
        db.commit()
        response = search_foods(db, user, "йогуртт", limit=20, offset=0)

    assert [item.brand for item in response.items] == ["Verified", "Community"]


def test_shared_confirmation_requires_gtin_before_catalog_write(client, monkeypatch) -> None:
    telegram_user_id = 128_106
    headers = _auth(client, telegram_user_id)
    _enable_scan(monkeypatch, _user_id(telegram_user_id))
    monkeypatch.setattr(nutrition_label_service, "_build_ocr_engine", lambda: _FakeOcr())
    draft = client.post(
        "/api/v1/nutrition/label-scans",
        headers={**headers, "Idempotency-Key": "gtin-scan-128"},
        files={"image": ("label.png", _label_image(), "image/png")},
    ).json()

    response = client.post(
        f"/api/v1/nutrition/label-scans/{draft['draft_id']}/confirm",
        headers=headers,
        json=_confirm_payload(visibility="share_to_yfc_catalog", barcode="123"),
    )

    assert response.status_code == 422
    with get_session_context() as db:
        assert db.query(NutritionCatalogContribution).count() == 0
        assert db.query(Food).filter(Food.provenance == "user_confirmed_package").count() == 0


def test_diary_uses_per_100_ml_snapshot_without_fabricating_grams(client) -> None:
    telegram_user_id = 128_107
    headers = _auth(client, telegram_user_id)
    per_ml = build_draft_from_ocr(
        "\n".join(
            (
                "Per 100 ml",
                "Energy 40 kcal",
                "Protein 2 g",
                "Fat 1 g",
                "Carbohydrate 5 g",
            )
        )
    )
    with get_session_context() as db:
        food = Food(
            name="Тестовый напиток",
            brand="YFC Test",
            energy_kcal_per_100g=None,
            protein_g_per_100g=None,
            fat_g_per_100g=None,
            carbs_g_per_100g=None,
            fiber_g_per_100g=None,
            nutrition_basis_kind="per_100_ml",
            nutrition_basis_amount=Decimal("100"),
            nutrition_basis_unit="ml",
            canonical_facts=per_ml.model_dump(mode="json"),
            canonical_complete=True,
            catalog_quality="community_unverified",
            food_type="branded",
            owner_user_id=None,
            provenance="user_confirmed_package",
            source_name="yfc_community",
            source_version="nutrition-label-local-v1",
            trust_level="unverified",
            status="active",
        )
        db.add(food)
        db.commit()
        db.refresh(food)
        food_id = food.id

    response = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=headers,
        json={
            "food_id": food_id,
            "diary_date": date.today().isoformat(),
            "meal_type": "lunch",
            "amount": "250",
            "amount_unit": "ml",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["amount_unit"] == "ml"
    assert body["weight_g"] is None
    assert body["nutrition_basis_unit"] == "ml"
    assert body["nutrition"]["energy_kcal"] == "100.00"
    assert body["nutrition"]["protein_g"] == "5.000"
    with get_session_context() as db:
        entry = db.query(FoodDiaryEntry).filter(FoodDiaryEntry.id == body["id"]).one()
        assert entry.legacy_weight_g == Decimal("1.000")
        assert entry.legacy_energy_kcal_per_100g == Decimal("0.00")
        assert entry.legacy_protein_g_per_100g == Decimal("0.000")


def test_account_deletion_removes_draft_and_anonymizes_shared_contribution(
    client, monkeypatch
) -> None:
    telegram_user_id = 128_110
    headers = _auth(client, telegram_user_id)
    user_id = _user_id(telegram_user_id)
    _enable_scan(monkeypatch, user_id)
    monkeypatch.setattr(nutrition_label_service, "_build_ocr_engine", lambda: _FakeOcr())
    draft = client.post(
        "/api/v1/nutrition/label-scans",
        headers={**headers, "Idempotency-Key": "delete-scan-128"},
        files={"image": ("label.png", _label_image(), "image/png")},
    ).json()
    confirmed = client.post(
        f"/api/v1/nutrition/label-scans/{draft['draft_id']}/confirm",
        headers=headers,
        json=_confirm_payload(visibility="share_to_yfc_catalog", barcode="4006381333931"),
    )
    assert confirmed.status_code == 201, confirmed.text
    food_id = confirmed.json()["food"]["id"]

    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None
        delete_user_cascade(db, user)
        db.commit()
        assert db.get(Food, food_id) is not None
        assert db.get(NutritionLabelDraft, draft["draft_id"]) is None
        contribution = db.query(NutritionCatalogContribution).one()
        assert contribution.contributor_user_id is None
