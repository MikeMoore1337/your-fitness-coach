from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi.encoders import jsonable_encoder

from fitminiapp_api.db.base import Base
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.auth_identity import AuthActionToken, AuthIdentity, LocalCredential
from fitminiapp_api.models.food import Food, FoodFavorite
from fitminiapp_api.models.food_diary import (
    FoodDiaryBatchOperation,
    FoodDiaryCopyOperation,
    FoodDiaryDayStatus,
    FoodDiaryEntry,
)
from fitminiapp_api.models.notification import (
    Notification,
    NotificationDelivery,
    WebPushSubscription,
)
from fitminiapp_api.models.nutrition_power import (
    FoodSearchAlias,
    NutritionMealTemplate,
    NutritionMealTemplateItem,
)
from fitminiapp_api.models.recipe import Recipe, RecipeIngredient
from fitminiapp_api.models.token import RefreshToken
from fitminiapp_api.models.user import CoachClient, User, UserProfile
from fitminiapp_api.services.account_export import (
    ACCOUNT_EXPORT_DATA_INVENTORY,
    ACCOUNT_EXPORT_EXCLUDED_DATA_INVENTORY,
    ACCOUNT_EXPORT_SCHEMA_VERSION,
    build_account_export,
)


def _reachable_user_tables() -> set[str]:
    tables = {"users"}
    changed = True
    while changed:
        changed = False
        for name, table in Base.metadata.tables.items():
            if name in tables:
                continue
            if any(
                foreign_key.column.table.name in tables
                for column in table.columns
                for foreign_key in column.foreign_keys
            ):
                tables.add(name)
                changed = True
    return tables


def _private_food(owner_user_id: int, name: str) -> Food:
    return Food(
        name=name,
        brand="Личный бренд",
        barcode=None,
        energy_kcal_per_100g=Decimal("210"),
        protein_g_per_100g=Decimal("12"),
        fat_g_per_100g=Decimal("8"),
        carbs_g_per_100g=Decimal("20"),
        fiber_g_per_100g=Decimal("3"),
        standard_serving_amount=Decimal("1"),
        standard_serving_unit="serving",
        standard_serving_weight_g=Decimal("50"),
        food_type="user",
        owner_user_id=owner_user_id,
        provenance="user",
        source_name=None,
        trust_level="unverified",
        status="active",
    )


def test_account_export_inventory_classifies_every_user_reachable_table() -> None:
    classified = set(ACCOUNT_EXPORT_DATA_INVENTORY) | set(ACCOUNT_EXPORT_EXCLUDED_DATA_INVENTORY)

    assert classified == _reachable_user_tables()
    assert not (set(ACCOUNT_EXPORT_DATA_INVENTORY) & set(ACCOUNT_EXPORT_EXCLUDED_DATA_INVENTORY))
    assert all(ACCOUNT_EXPORT_EXCLUDED_DATA_INVENTORY.values())


def test_account_export_includes_current_nutrition_domains_and_omits_secrets() -> None:
    with get_session_context() as db:
        owner = db.query(User).filter(User.telegram_user_id == 2001).one()
        foreign_user = db.query(User).filter(User.telegram_user_id == 2002).one()
        if owner.profile is None:
            owner.profile = UserProfile(timezone="Europe/Moscow")
        owner.profile.full_name = "Владелец экспорта"
        owner.profile.resting_heart_rate = 54
        owner_identity = AuthIdentity(
            user_id=owner.id,
            provider="google",
            subject="google-owner-subject",
            email="owner@example.test",
            email_verified=True,
        )
        credential = LocalCredential(
            user_id=owner.id,
            username_normalized="export_owner",
            password_hash="SECRET_PASSWORD_HASH",
        )
        action_token = AuthActionToken(
            user_id=owner.id,
            purpose="password_reset",
            token_hash="SECRET_ACTION_TOKEN_HASH",
            session_family_id="SECRET_SESSION_FAMILY",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        refresh_token = RefreshToken(
            user_id=owner.id,
            jti="secret-jti",
            family_id="secret-family",
            token_hash="SECRET_REFRESH_TOKEN_HASH",
            expires_at=datetime.now() + timedelta(days=1),
        )
        own_food = _private_food(owner.id, "Мой экспортируемый продукт")
        foreign_food = _private_food(foreign_user.id, "Чужой приватный продукт")
        db.add_all(
            [owner_identity, credential, action_token, refresh_token, own_food, foreign_food]
        )
        db.flush()
        db.add(FoodFavorite(user_id=owner.id, food_id=own_food.id))
        db.add(FoodFavorite(user_id=owner.id, food_id=foreign_food.id))
        recipe = Recipe(
            owner_user_id=owner.id,
            name="Мой рецепт",
            final_weight_g=Decimal("120"),
        )
        db.add(recipe)
        db.flush()
        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                food_id=own_food.id,
                position=0,
                amount=Decimal("100"),
                amount_unit="g",
                weight_g=Decimal("100"),
                food_name="Снимок ингредиента",
                food_brand="Снимок бренда",
                energy_kcal_per_100g=Decimal("200"),
                protein_g_per_100g=Decimal("10"),
                fat_g_per_100g=Decimal("5"),
                carbs_g_per_100g=Decimal("30"),
                fiber_g_per_100g=Decimal("4"),
            )
        )
        meal_template = NutritionMealTemplate(
            owner_user_id=owner.id,
            name="Мой шаблон экспорта",
        )
        db.add(meal_template)
        db.flush()
        db.add(
            NutritionMealTemplateItem(
                template_id=meal_template.id,
                position=0,
                item_kind="food",
                food_id=own_food.id,
                recipe_id=None,
                amount=Decimal("80"),
                amount_unit="g",
                source_name="Мой экспортируемый продукт",
                source_brand="Личный бренд",
            )
        )
        db.add(
            FoodSearchAlias(
                user_id=owner.id,
                alias="мой рис",
                normalized_alias="мой рис",
                food_id=own_food.id,
            )
        )
        copy_operation = FoodDiaryCopyOperation(
            user_id=owner.id,
            idempotency_key="SECRET_IDEMPOTENCY_KEY",
            request_fingerprint="SECRET_REQUEST_FINGERPRINT",
            copy_scope="product",
            source_entry_id=None,
            source_date=date(2026, 8, 18),
            source_meal_type="breakfast",
            target_date=date(2026, 8, 19),
            target_meal_type="lunch",
        )
        db.add(copy_operation)
        db.flush()
        db.add(
            FoodDiaryBatchOperation(
                user_id=owner.id,
                operation_kind="meal_template",
                template_id=meal_template.id,
                idempotency_key="SECRET_BATCH_IDEMPOTENCY_KEY",
                request_fingerprint="SECRET_BATCH_REQUEST_FINGERPRINT",
                diary_date=date(2026, 8, 19),
                meal_type="lunch",
            )
        )
        db.add(
            FoodDiaryEntry(
                user_id=owner.id,
                food_id=own_food.id,
                copy_operation_id=copy_operation.id,
                diary_date=date(2026, 8, 19),
                meal_type="lunch",
                amount=Decimal("1"),
                amount_unit="serving",
                weight_g=Decimal("50"),
                food_name="Снимок дневника",
                food_brand="Снимок бренда",
                energy_kcal_per_100g=Decimal("205"),
                protein_g_per_100g=Decimal("11"),
                fat_g_per_100g=Decimal("7"),
                carbs_g_per_100g=Decimal("21"),
                fiber_g_per_100g=Decimal("3"),
                serving_amount=Decimal("1"),
                serving_unit="serving",
                serving_weight_g=Decimal("50"),
            )
        )
        db.add(
            FoodDiaryDayStatus(
                user_id=owner.id,
                diary_date=date(2026, 8, 19),
                status="complete",
            )
        )
        db.add(
            CoachClient(
                coach_user_id=owner.id,
                client_user_id=foreign_user.id,
                private_name="SECRET_MANAGED_CLIENT_NAME",
                status="active",
            )
        )
        db.flush()
        push_notification = Notification(
            user_id=owner.id,
            category="trainer_program_update",
            event_kind="transactional",
            title="Web Push event",
            body="Private notification details",
            scheduled_for=datetime(2026, 8, 19, 9),
            scheduled_for_utc=datetime(2026, 8, 19, 6),
            status="sent",
        )
        db.add(push_notification)
        db.flush()
        push_subscription = WebPushSubscription(
            user_id=owner.id,
            endpoint="https://fcm.googleapis.com/fcm/send/SECRET_ENDPOINT_CAPABILITY",
            endpoint_hash="SECRET_ENDPOINT_HASH",
            p256dh="SECRET_P256DH",
            auth="SECRET_AUTH",
        )
        db.add(push_subscription)
        db.flush()
        db.add(
            NotificationDelivery(
                notification_id=push_notification.id,
                subscription_id=push_subscription.id,
                status="sent",
            )
        )
        db.flush()

        payload = build_account_export(db, owner)
        credential_metadata = {
            "username_normalized": credential.username_normalized,
            "created_at": credential.created_at,
            "password_changed_at": credential.password_changed_at,
        }

    assert payload["schema_version"] == ACCOUNT_EXPORT_SCHEMA_VERSION
    assert payload["profile"]["resting_heart_rate"] == 54
    assert (
        next(
            identity for identity in payload["auth_identities"] if identity["provider"] == "google"
        )["subject"]
        == "google-owner-subject"
    )
    assert payload["local_credential"] == credential_metadata
    assert payload["private_foods"][0]["name"] == "Мой экспортируемый продукт"
    assert payload["food_favorites"][0]["food"]["name"] == "Мой экспортируемый продукт"
    assert payload["recipes"][0]["ingredients"][0]["food_name"] == "Снимок ингредиента"
    assert payload["nutrition_meal_templates"][0]["name"] == "Мой шаблон экспорта"
    assert (
        payload["nutrition_meal_templates"][0]["items"][0]["source_name"]
        == "Мой экспортируемый продукт"
    )
    assert payload["food_search_aliases"][0]["alias"] == "мой рис"
    assert payload["food_diary_batch_operations"][0]["operation_kind"] == "meal_template"
    assert "idempotency_key" not in payload["food_diary_batch_operations"][0]
    assert "request_fingerprint" not in payload["food_diary_batch_operations"][0]
    assert payload["food_diary_entries"][0]["food_name"] == "Снимок дневника"
    assert payload["food_diary_entries"][0]["energy_kcal_per_100g"] == Decimal("205")
    assert payload["food_diary_day_statuses"][0]["status"] == "complete"
    assert payload["food_diary_copy_operations"][0]["copy_scope"] == "product"
    assert set(ACCOUNT_EXPORT_DATA_INVENTORY.values()) <= set(payload)

    encoded = json.dumps(jsonable_encoder(payload), ensure_ascii=False)
    for forbidden in (
        "SECRET_PASSWORD_HASH",
        "SECRET_ACTION_TOKEN_HASH",
        "SECRET_REFRESH_TOKEN_HASH",
        "SECRET_SESSION_FAMILY",
        "SECRET_IDEMPOTENCY_KEY",
        "SECRET_REQUEST_FINGERPRINT",
        "SECRET_BATCH_IDEMPOTENCY_KEY",
        "SECRET_BATCH_REQUEST_FINGERPRINT",
        "SECRET_MANAGED_CLIENT_NAME",
        "SECRET_ENDPOINT_CAPABILITY",
        "SECRET_ENDPOINT_HASH",
        "SECRET_P256DH",
        "SECRET_AUTH",
        "Чужой приватный продукт",
    ):
        assert forbidden not in encoded
