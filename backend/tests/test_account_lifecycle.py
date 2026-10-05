from __future__ import annotations

import io
import json
import zipfile
from datetime import timedelta
from decimal import Decimal

from fastapi.encoders import jsonable_encoder

from fitminiapp_api.api.v1 import me as me_api
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.account import AccountDataExport
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.auth_identity import AuthIdentity
from fitminiapp_api.models.exercise import Exercise, ExerciseGuideMetadata
from fitminiapp_api.models.food import Food, FoodFavorite
from fitminiapp_api.models.food_diary import (
    FoodDiaryCopyOperation,
    FoodDiaryDayStatus,
    FoodDiaryEntry,
)
from fitminiapp_api.models.notification import Notification, NotificationSetting
from fitminiapp_api.models.nutrition import EnergyCalibration, NutritionTarget
from fitminiapp_api.models.recipe import Recipe, RecipeIngredient
from fitminiapp_api.models.token import RefreshToken
from fitminiapp_api.models.user import BodyMeasurement, CoachClient, CoachClientInvite, User
from fitminiapp_api.models.weekly_digest import WeeklyDigestPreference
from fitminiapp_api.services import account_exports


def _login(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_export_job_is_current_user_only_zip_and_replaces_previous_artifact(client) -> None:
    owner_headers = _login(client, 9_650_001)
    other_headers = _login(client, 9_650_002)
    owner_id = client.get("/api/v1/me", headers=owner_headers).json()["id"]
    other_id = client.get("/api/v1/me", headers=other_headers).json()["id"]
    with get_session_context() as db:
        db.add_all(
            [
                BodyMeasurement(
                    user_id=owner_id,
                    measured_on=now_msk_naive().date(),
                    weight_kg=75.2,
                    note='=HYPERLINK("https://example.test", "Личная запись владельца")',
                ),
                BodyMeasurement(
                    user_id=other_id,
                    measured_on=now_msk_naive().date(),
                    weight_kg=91.4,
                    note="Чужая запись",
                ),
            ]
        )

    assert client.get("/api/v1/me/exports/current", headers=owner_headers).json() == {
        "status": "none",
        "export_id": None,
        "created_at": None,
        "completed_at": None,
        "expires_at": None,
        "filename": None,
        "content_size_bytes": None,
        "error_code": None,
    }
    created = client.post("/api/v1/me/exports", headers=owner_headers)
    assert created.status_code == 201
    status = created.json()
    assert status["status"] == "ready"
    assert status["export_id"]
    assert status["filename"].endswith(".zip")
    assert status["content_size_bytes"] > 0

    denied = client.get(
        f"/api/v1/me/exports/{status['export_id']}/download",
        headers=other_headers,
    )
    assert denied.status_code == 404
    downloaded = client.get(
        f"/api/v1/me/exports/{status['export_id']}/download",
        headers=owner_headers,
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/zip"
    assert downloaded.headers["cache-control"] == "no-store, private"
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert set(archive.namelist()) == {
            "account.json",
            "daily-wellbeing-check-ins.csv",
            "food-diary.csv",
            "manifest.json",
            "measurements.csv",
            "nutrition-target-history.csv",
            "weekly-check-ins.csv",
            "workout-history.csv",
        }
        payload = json.loads(archive.read("account.json"))
        measurements_csv = archive.read("measurements.csv").decode("utf-8-sig")
    assert payload["account"]["id"] == owner_id
    assert payload["measurements"][0]["note"].startswith("=HYPERLINK")
    assert "Чужая запись" not in json.dumps(payload, ensure_ascii=False)
    assert "'=HYPERLINK" in measurements_csv
    assert "91.4" not in measurements_csv
    assert "token_hash" not in json.dumps(jsonable_encoder(payload)).lower()

    replaced = client.post("/api/v1/me/exports", headers=owner_headers).json()
    assert replaced["status"] == "ready"
    assert replaced["export_id"] != status["export_id"]
    assert (
        client.get(
            f"/api/v1/me/exports/{status['export_id']}/download",
            headers=owner_headers,
        ).status_code
        == 404
    )
    with get_session_context() as db:
        assert db.query(AccountDataExport).filter_by(user_id=owner_id).count() == 1


def test_export_expiry_purges_bytes_and_tma_link_is_short_lived(client) -> None:
    headers = _login(client, 9_650_003)
    ready = client.post("/api/v1/me/exports", headers=headers).json()
    link = client.post(
        f"/api/v1/me/exports/{ready['export_id']}/download-link",
        headers=headers,
    )
    assert link.status_code == 200
    public_path = link.json()["url"].split("/api/v1", 1)[1]
    public_download = client.get(f"/api/v1{public_path}")
    assert public_download.status_code == 200
    assert public_download.headers["access-control-allow-origin"] == "https://web.telegram.org"

    with get_session_context() as db:
        row = db.query(AccountDataExport).filter_by(export_id=ready["export_id"]).one()
        row.expires_at = now_msk_naive() - timedelta(seconds=1)

    expired = client.get("/api/v1/me/exports/current", headers=headers)
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"
    assert expired.json()["content_size_bytes"] is None
    assert (
        client.get(
            f"/api/v1/me/exports/{ready['export_id']}/download",
            headers=headers,
        ).status_code
        == 410
    )
    assert client.get(f"/api/v1{public_path}").status_code == 404
    with get_session_context() as db:
        row = db.query(AccountDataExport).filter_by(export_id=ready["export_id"]).one()
        assert row.archive_bytes is None
        assert row.download_token_hash is None


def test_export_handles_empty_account_and_bounded_generation_error(client, monkeypatch) -> None:
    headers = _login(client, 9_650_007)
    ready = client.post("/api/v1/me/exports", headers=headers)
    assert ready.status_code == 201
    assert ready.json()["status"] == "ready"

    monkeypatch.setattr(account_exports, "ACCOUNT_EXPORT_MAX_SOURCE_BYTES", 1)
    bounded = client.post("/api/v1/me/exports", headers=headers)
    assert bounded.status_code == 201
    assert bounded.json()["status"] == "error"
    assert bounded.json()["error_code"] == "archive_too_large"
    with get_session_context() as db:
        row = (
            db.query(AccountDataExport)
            .filter_by(user_id=client.get("/api/v1/me", headers=headers).json()["id"])
            .one()
        )
        assert row.archive_bytes is None


def test_export_generation_removed_by_account_delete_returns_gone(client, monkeypatch) -> None:
    headers = _login(client, 9_650_009)

    def remove_generation(db, user_id: int, export_id: str):
        db.query(AccountDataExport).filter(
            AccountDataExport.user_id == user_id,
            AccountDataExport.export_id == export_id,
        ).delete(synchronize_session=False)
        db.commit()
        return None

    monkeypatch.setattr(me_api, "lock_account_export_generation", remove_generation)
    response = client.post("/api/v1/me/exports", headers=headers)

    assert response.status_code == 410
    assert response.json()["detail"] == "Аккаунт больше недоступен"


def test_superseded_export_generation_cannot_lock_the_newer_job(client) -> None:
    headers = _login(client, 9_650_008)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None
        first = account_exports.start_account_export(db, user)
        first_id = first.export_id

    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None
        second = account_exports.start_account_export(db, user)
        second_id = second.export_id

    assert second_id != first_id
    with get_session_context() as db:
        assert account_exports.lock_account_export_generation(db, user_id, first_id) is None
        current = account_exports.lock_account_export_generation(db, user_id, second_id)
        assert current is not None
        assert current.export_id == second_id


def test_unlink_preserves_account_guards_last_identity_and_disables_telegram(client) -> None:
    headers = _login(client, 9_650_004)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    now = now_msk_naive()
    with get_session_context() as db:
        db.add(
            AuthIdentity(
                user_id=user_id,
                provider="google",
                subject="task-65-google",
                email="task65@example.test",
                email_verified=True,
            )
        )
        setting = db.query(NotificationSetting).filter_by(user_id=user_id).one()
        setting.telegram_enabled = True
        db.add(
            WeeklyDigestPreference(
                user_id=user_id,
                telegram_chat_id=9_650_004,
                weekly_news_digest_enabled=True,
                consent_version="weekly-news-v1",
                subscribed_at=now,
            )
        )
        db.add(
            Notification(
                user_id=user_id,
                channel="telegram",
                category="workout_reminder",
                event_kind="reminder",
                title="Напоминание",
                body="Личный текст",
                scheduled_for=now + timedelta(hours=1),
                scheduled_for_utc=now + timedelta(hours=1),
                status="queued",
            )
        )
        db.add(
            BodyMeasurement(
                user_id=user_id,
                measured_on=now.date(),
                weight_kg=70,
            )
        )

    unlinked = client.delete("/api/v1/me/auth/identities/telegram", headers=headers)
    assert unlinked.status_code == 200
    assert unlinked.json()["telegram_user_id"] is None
    assert unlinked.json()["auth_providers"] == ["google"]
    assert client.get("/api/v1/me", headers=headers).status_code == 200
    with get_session_context() as db:
        assert db.get(User, user_id) is not None
        assert db.query(BodyMeasurement).filter_by(user_id=user_id).count() == 1
        setting = db.query(NotificationSetting).filter_by(user_id=user_id).one()
        notification = db.query(Notification).filter_by(user_id=user_id).one()
        assert setting.telegram_enabled is False
        assert notification.status == "cancelled"
        assert notification.last_error == "telegram_identity_unlinked"
        digest_preference = db.query(WeeklyDigestPreference).filter_by(user_id=user_id).one()
        assert digest_preference.weekly_news_digest_enabled is False
        assert digest_preference.telegram_chat_id is None
        assert digest_preference.disabled_reason == "telegram_identity_unlinked"

    blocked = client.delete("/api/v1/me/auth/identities/google", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "Нельзя отключить последний способ входа"


def test_delete_revokes_sessions_relationships_and_export_but_keeps_shared_catalog(client) -> None:
    headers = _login(client, 9_650_005)
    other_headers = _login(client, 9_650_006)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    other_id = client.get("/api/v1/me", headers=other_headers).json()["id"]
    ready = client.post("/api/v1/me/exports", headers=headers).json()
    with get_session_context() as db:
        today = now_msk_naive().date()
        shared_exercise_id = (
            db.query(Exercise.id).filter(Exercise.created_by_user_id.is_(None)).first()[0]
        )
        db.add(CoachClient(coach_user_id=other_id, client_user_id=user_id, status="active"))
        db.add(
            AuthIdentity(
                user_id=user_id,
                provider="google",
                subject="delete-oauth-only",
                email="delete-oauth-only@example.test",
                email_verified=True,
            )
        )
        unrelated_invite = CoachClientInvite(
            coach_user_id=other_id,
            source="invite_link",
            status="pending",
            token_hash="a" * 64,
            expires_at=now_msk_naive() + timedelta(days=1),
        )
        db.add(unrelated_invite)
        db.flush()
        unrelated_invite_id = unrelated_invite.id
        orphan_marker = "delete-private-orphan-marker"
        orphan_exercise = Exercise(
            slug=orphan_marker,
            title=orphan_marker,
            primary_muscle=orphan_marker,
            equipment=orphan_marker,
            created_by_user_id=user_id,
        )
        referenced_marker = "delete-private-referenced-marker"
        referenced_exercise = Exercise(
            slug=referenced_marker,
            title=referenced_marker,
            primary_muscle=referenced_marker,
            equipment=referenced_marker,
            created_by_user_id=user_id,
        )
        db.add_all([orphan_exercise, referenced_exercise])
        db.flush()
        orphan_exercise_id = orphan_exercise.id
        referenced_exercise_id = referenced_exercise.id
        db.add(
            ExerciseGuideMetadata(
                exercise_id=referenced_exercise_id,
                safety_notes=[referenced_marker],
                source_name=referenced_marker,
                source_url=f"https://example.test/{referenced_marker}",
                source_license=referenced_marker,
                media_reference=referenced_marker,
            )
        )
        retained_reference = Exercise(
            slug="retained-reference-after-account-delete",
            title="Retained reference",
            created_by_user_id=other_id,
            source_exercise_id=referenced_exercise_id,
        )
        db.add(retained_reference)
        db.flush()
        retained_reference_id = retained_reference.id
        occupied_anonymized_slug = f"deleted-user-exercise-{referenced_exercise_id}"
        occupied_exercise = Exercise(
            slug=occupied_anonymized_slug,
            title="Existing unrelated exercise",
            created_by_user_id=other_id,
        )
        db.add(occupied_exercise)
        db.flush()
        occupied_exercise_id = occupied_exercise.id

        private_food = Food(
            name="Удаляемый личный продукт",
            brand="Личный бренд",
            energy_kcal_per_100g=Decimal("210"),
            protein_g_per_100g=Decimal("12"),
            fat_g_per_100g=Decimal("8"),
            carbs_g_per_100g=Decimal("20"),
            fiber_g_per_100g=Decimal("3"),
            standard_serving_amount=Decimal("1"),
            standard_serving_unit="serving",
            standard_serving_weight_g=Decimal("50"),
            food_type="user",
            owner_user_id=user_id,
            provenance="user",
            source_name=None,
            trust_level="unverified",
            status="active",
        )
        other_food = Food(
            name="Чужой личный продукт",
            energy_kcal_per_100g=Decimal("180"),
            protein_g_per_100g=Decimal("9"),
            fat_g_per_100g=Decimal("7"),
            carbs_g_per_100g=Decimal("22"),
            food_type="user",
            owner_user_id=other_id,
            provenance="user",
            source_name=None,
            trust_level="unverified",
            status="active",
        )
        db.add_all([private_food, other_food])
        db.flush()
        private_food_id = private_food.id
        other_food_id = other_food.id
        db.add(FoodFavorite(user_id=user_id, food_id=private_food_id))

        recipe = Recipe(
            owner_user_id=user_id,
            name="Удаляемый личный рецепт",
            final_weight_g=Decimal("100"),
        )
        db.add(recipe)
        db.flush()
        recipe_id = recipe.id
        ingredient = RecipeIngredient(
            recipe_id=recipe_id,
            food_id=private_food_id,
            position=0,
            amount=Decimal("100"),
            amount_unit="g",
            weight_g=Decimal("100"),
            food_name=private_food.name,
            food_brand=private_food.brand,
            energy_kcal_per_100g=Decimal("210"),
            protein_g_per_100g=Decimal("12"),
            fat_g_per_100g=Decimal("8"),
            carbs_g_per_100g=Decimal("20"),
            fiber_g_per_100g=Decimal("3"),
        )
        db.add(ingredient)
        db.flush()
        ingredient_id = ingredient.id

        copy_operation = FoodDiaryCopyOperation(
            user_id=user_id,
            idempotency_key="account-delete-copy",
            request_fingerprint="a" * 64,
            copy_scope="product",
            source_entry_id=None,
            source_date=today,
            source_meal_type="breakfast",
            target_date=today,
            target_meal_type="lunch",
        )
        db.add(copy_operation)
        db.flush()
        copy_operation_id = copy_operation.id
        diary_entry = FoodDiaryEntry(
            user_id=user_id,
            food_id=private_food_id,
            recipe_id=None,
            copy_operation_id=copy_operation_id,
            diary_date=today,
            meal_type="lunch",
            amount=Decimal("1"),
            amount_unit="serving",
            weight_g=Decimal("50"),
            food_name=private_food.name,
            food_brand=private_food.brand,
            energy_kcal_per_100g=Decimal("210"),
            protein_g_per_100g=Decimal("12"),
            fat_g_per_100g=Decimal("8"),
            carbs_g_per_100g=Decimal("20"),
            fiber_g_per_100g=Decimal("3"),
            serving_amount=Decimal("1"),
            serving_unit="serving",
            serving_weight_g=Decimal("50"),
        )
        db.add(diary_entry)
        db.add(FoodDiaryDayStatus(user_id=user_id, diary_date=today, status="complete"))

        target = NutritionTarget(
            user_id=user_id,
            assigned_by_user_id=user_id,
            calories=2200,
            protein_g=150,
            fat_g=70,
            carbs_g=240,
            effective_from=today,
            source="manual",
        )
        db.add(target)
        db.flush()
        target_id = target.id
        calibration = EnergyCalibration(
            user_id=user_id,
            ruleset_version="account-delete-test-v1",
            status="accepted",
            sufficiency_status="sufficient",
            period_start=today - timedelta(days=28),
            period_end=today,
            goal="maintenance",
            logged_day_count=28,
            eligible_day_count=28,
            weight_point_count=6,
            weight_span_days=28,
            average_intake_kcal=2200,
            smoothed_start_weight_kg=Decimal("80.0"),
            smoothed_end_weight_kg=Decimal("80.0"),
            estimated_expenditure_kcal=2200,
            estimate_low_kcal=2100,
            estimate_high_kcal=2300,
            previous_target_calories=2200,
            previous_target_saved_at=now_msk_naive(),
            proposed_target_calories=None,
            sufficiency_counters={"logged_days": 28},
            sufficiency_reason_keys=[],
            rationale_keys=["stable_weight"],
            decided_at=now_msk_naive(),
        )
        db.add(calibration)
        db.flush()
        calibration_id = calibration.id

    unlinked = client.delete("/api/v1/me/auth/identities/telegram", headers=headers)
    assert unlinked.status_code == 200
    assert unlinked.json()["telegram_user_id"] is None
    assert unlinked.json()["username"] is None

    deleted = client.request(
        "DELETE",
        "/api/v1/me/account",
        headers=headers,
        json={"confirmation": "DELETE"},
    )
    assert deleted.status_code == 204
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    with get_session_context() as db:
        assert db.get(User, user_id) is None
        assert db.get(User, other_id) is not None
        assert db.get(CoachClientInvite, unrelated_invite_id) is not None
        assert db.get(Exercise, shared_exercise_id) is not None
        assert db.query(CoachClient).filter_by(client_user_id=user_id).count() == 0
        assert db.query(AccountDataExport).filter_by(export_id=ready["export_id"]).count() == 0
        assert db.query(RefreshToken).filter_by(user_id=user_id).count() == 0
        assert db.get(Exercise, orphan_exercise_id) is None
        anonymized = db.get(Exercise, referenced_exercise_id)
        assert anonymized is not None
        assert anonymized.slug.startswith("deleted-user-exercise-")
        assert anonymized.slug != occupied_anonymized_slug
        assert len(anonymized.slug) <= 64
        assert anonymized.title == "Удалённое пользовательское упражнение"
        assert anonymized.primary_muscle is None
        assert anonymized.equipment is None
        assert anonymized.created_by_user_id is None
        assert anonymized.is_deleted is True
        assert db.get(ExerciseGuideMetadata, referenced_exercise_id) is None
        assert db.get(Exercise, retained_reference_id).source_exercise_id == referenced_exercise_id
        assert db.get(Exercise, occupied_exercise_id).slug == occupied_anonymized_slug
        assert db.get(Food, private_food_id) is None
        assert db.get(Food, other_food_id) is not None
        assert db.query(FoodFavorite).filter_by(user_id=user_id).count() == 0
        assert db.get(Recipe, recipe_id) is None
        assert db.get(RecipeIngredient, ingredient_id) is None
        assert db.query(FoodDiaryEntry).filter_by(user_id=user_id).count() == 0
        assert db.query(FoodDiaryDayStatus).filter_by(user_id=user_id).count() == 0
        assert db.get(FoodDiaryCopyOperation, copy_operation_id) is None
        assert db.get(NutritionTarget, target_id) is None
        assert db.get(EnergyCalibration, calibration_id) is None
        deletion_event = db.query(AuditEvent).filter_by(action="account.self_deleted").one()
        assert deletion_event.actor_user_id is None
        assert deletion_event.target_user_id is None
        assert deletion_event.resource_id is None
        assert deletion_event.details == {}
