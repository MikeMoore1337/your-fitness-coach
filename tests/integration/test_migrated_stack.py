from __future__ import annotations

import os
import re
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

RUN_MIGRATED_STACK_TEST = os.environ.get("RUN_MIGRATED_STACK_TEST") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_MIGRATED_STACK_TEST,
    reason="set RUN_MIGRATED_STACK_TEST=1 and provide a migrated PostgreSQL database",
)


def test_migrated_postgres_serves_api_and_frontend() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    assert database_url.startswith("postgresql+psycopg://"), (
        "the migrated-stack test must run against PostgreSQL"
    )

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "backend"))

    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from fitminiapp_api.db.session import engine
    from fitminiapp_api.main import app

    alembic_config = Config(str(root / "backend" / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(root / "backend" / "alembic"))
    expected_revision = ScriptDirectory.from_config(alembic_config).get_current_head()
    with engine.connect() as connection:
        actual_revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert actual_revision == expected_revision

    with TestClient(app) as client:
        ready = client.get("/health/ready")
        frontend = client.get("/app")
        public_config = client.get("/api/v1/public/config")
        login = client.post(
            "/api/v1/auth/dev-login",
            json={
                "telegram_user_id": 9_900_001,
                "username": "ci_migrated_stack",
                "full_name": "CI Migrated Stack",
            },
        )

        assert ready.status_code == 200
        assert frontend.status_code == 200
        assert re.search(r'<div\s+id=["\']root["\'][^>]*>', frontend.text)
        assert public_config.status_code == 200
        assert public_config.json()["app_env"] == "test"
        assert login.status_code == 200

        me = client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["telegram_user_id"] == 9_900_001


def test_migrated_postgres_account_deletion_removes_owner_nutrition_graph() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    assert database_url.startswith("postgresql+psycopg://"), (
        "the account-deletion regression must run against PostgreSQL"
    )

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "backend"))

    from fastapi.testclient import TestClient

    from fitminiapp_api.core.timezone import now_msk_naive
    from fitminiapp_api.db.session import get_session_context
    from fitminiapp_api.main import app
    from fitminiapp_api.models.food import Food, FoodFavorite
    from fitminiapp_api.models.food_diary import (
        FoodDiaryCopyOperation,
        FoodDiaryDayStatus,
        FoodDiaryEntry,
    )
    from fitminiapp_api.models.nutrition import EnergyCalibration, NutritionTarget
    from fitminiapp_api.models.recipe import Recipe, RecipeIngredient

    with TestClient(app) as client:
        owner_login = client.post(
            "/api/v1/auth/dev-login",
            json={"telegram_user_id": 9_900_011, "full_name": "Deletion owner"},
        )
        other_login = client.post(
            "/api/v1/auth/dev-login",
            json={"telegram_user_id": 9_900_012, "full_name": "Deletion other"},
        )
        assert owner_login.status_code == 200
        assert other_login.status_code == 200
        owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
        other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
        owner_id = client.get("/api/v1/me", headers=owner_headers).json()["id"]
        other_id = client.get("/api/v1/me", headers=other_headers).json()["id"]

        with get_session_context() as db:
            today = now_msk_naive().date()
            private_food = Food(
                name="PostgreSQL deletion owner food",
                energy_kcal_per_100g=Decimal("210"),
                protein_g_per_100g=Decimal("12"),
                fat_g_per_100g=Decimal("8"),
                carbs_g_per_100g=Decimal("20"),
                food_type="user",
                owner_user_id=owner_id,
                provenance="user",
                source_name=None,
                trust_level="unverified",
                status="active",
            )
            other_food = Food(
                name="PostgreSQL deletion other food",
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
            db.add(FoodFavorite(user_id=owner_id, food_id=private_food_id))

            recipe = Recipe(owner_user_id=owner_id, name="PostgreSQL deletion recipe")
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
                food_brand=None,
                energy_kcal_per_100g=Decimal("210"),
                protein_g_per_100g=Decimal("12"),
                fat_g_per_100g=Decimal("8"),
                carbs_g_per_100g=Decimal("20"),
                fiber_g_per_100g=None,
            )
            db.add(ingredient)
            db.flush()
            ingredient_id = ingredient.id

            copy_operation = FoodDiaryCopyOperation(
                user_id=owner_id,
                idempotency_key="postgres-account-delete-copy",
                request_fingerprint="b" * 64,
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
            db.add(
                FoodDiaryEntry(
                    user_id=owner_id,
                    food_id=private_food_id,
                    copy_operation_id=copy_operation_id,
                    diary_date=today,
                    meal_type="lunch",
                    amount=Decimal("1"),
                    amount_unit="serving",
                    weight_g=Decimal("50"),
                    food_name=private_food.name,
                    food_brand=None,
                    energy_kcal_per_100g=Decimal("210"),
                    protein_g_per_100g=Decimal("12"),
                    fat_g_per_100g=Decimal("8"),
                    carbs_g_per_100g=Decimal("20"),
                    fiber_g_per_100g=None,
                    serving_amount=Decimal("1"),
                    serving_unit="serving",
                    serving_weight_g=Decimal("50"),
                )
            )
            db.add(FoodDiaryDayStatus(user_id=owner_id, diary_date=today, status="complete"))

            target = NutritionTarget(
                user_id=owner_id,
                assigned_by_user_id=owner_id,
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
                user_id=owner_id,
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

        deleted = client.request(
            "DELETE",
            "/api/v1/me/account",
            headers=owner_headers,
            json={"confirmation": "DELETE"},
        )
        assert deleted.status_code == 204

        with get_session_context() as db:
            assert db.get(Food, private_food_id) is None
            assert db.get(Food, other_food_id) is not None
            assert db.query(FoodFavorite).filter_by(user_id=owner_id).count() == 0
            assert db.get(Recipe, recipe_id) is None
            assert db.get(RecipeIngredient, ingredient_id) is None
            assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 0
            assert db.query(FoodDiaryDayStatus).filter_by(user_id=owner_id).count() == 0
            assert db.get(FoodDiaryCopyOperation, copy_operation_id) is None
            assert db.get(NutritionTarget, target_id) is None
            assert db.get(EnergyCalibration, calibration_id) is None


def test_program_schema_upgrades_from_0092_on_postgres16(monkeypatch) -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    assert database_url.startswith("postgresql+psycopg://"), (
        "the migration compatibility test must run against PostgreSQL"
    )

    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url

    from alembic import command

    root = Path(__file__).resolve().parents[2]
    database = make_url(database_url)
    assert database.database == "fitminiapp_test", "migration test database must be isolated"
    schema_name = f"task393_{os.getpid()}_{os.urandom(4).hex()}"
    maintenance_engine = create_engine(database_url)
    with maintenance_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        version = conn.execute(text("SELECT current_setting('server_version_num')")).scalar_one()
        assert str(version).startswith("16"), "the migration test requires PostgreSQL 16"
        conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))

    schema_url = database.update_query_dict({"options": f"-csearch_path={schema_name},public"})
    schema_database_url = schema_url.render_as_string(hide_password=False)
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "database_url", schema_database_url)
    alembic_config = Config(str(root / "backend" / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(root / "backend" / "alembic"))
    try:
        command.upgrade(alembic_config, "0092_coach_crm_core")
        schema_engine = create_engine(schema_database_url)
        try:
            with schema_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO program_templates "
                        "(slug, title, goal, level, split_type, default_duration_weeks, is_public) "
                        "VALUES (:slug, :title, 'strength', 'beginner', 'full_body', 1, :is_public)"
                    ),
                    [
                        {
                            "slug": "stronglifts-5x5",
                            "title": "StrongLifts",
                            "is_public": True,
                        },
                        {
                            "slug": "legacy-yfc-template",
                            "title": "Legacy YFC template",
                            "is_public": True,
                        },
                        {
                            "slug": "private-custom-template",
                            "title": "Private custom template",
                            "is_public": False,
                        },
                    ],
                )
        finally:
            schema_engine.dispose()

        command.upgrade(alembic_config, "head")
        schema_engine = create_engine(schema_database_url)
        try:
            inspector = inspect(schema_engine)
            provenance_columns = {
                column["name"]: column for column in inspector.get_columns("program_templates")
            }
            assert provenance_columns["provenance_type"]["nullable"] is True
            assert provenance_columns["provenance"]["nullable"] is True
            assert provenance_columns["program_metadata"]["nullable"] is True

            source_foreign_keys = {
                column
                for foreign_key in inspector.get_foreign_keys("user_workout_exercises")
                for column in foreign_key["constrained_columns"]
            }
            assert "source_template_exercise_id" not in source_foreign_keys
            assert "source_weekly_prescription_id" not in source_foreign_keys

            with schema_engine.connect() as connection:
                migration_context = connection.execute(
                    text(
                        "SELECT current_schema(), current_setting('search_path'), "
                        "(SELECT version_num FROM alembic_version)"
                    )
                ).one()
                template_schema = connection.execute(
                    text(
                        "SELECT n.nspname FROM pg_class AS c "
                        "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                        "WHERE c.oid = 'program_templates'::regclass"
                    )
                ).scalar_one()
                template_count = connection.execute(
                    text("SELECT count(*) FROM program_templates")
                ).scalar_one()
                backfill_batch = (
                    connection.execute(
                        text(
                            "SELECT id FROM program_templates WHERE provenance_type IS NULL "
                            "ORDER BY CASE WHEN owner_user_id IS NULL AND created_by_user_id IS NULL "
                            "AND is_public = TRUE THEN 0 ELSE 1 END, id LIMIT 10"
                        )
                    )
                    .scalars()
                    .all()
                )
                provenance = dict(
                    connection.execute(
                        text("SELECT slug, provenance_type FROM program_templates")
                    ).all()
                )
                revision_check = connection.execute(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conrelid = 'program_revisions'::regclass "
                        "AND conname = 'ck_program_revisions_change_kind'"
                    )
                ).scalar_one()
            assert migration_context[0] == schema_name, migration_context
            assert migration_context[2] == "0095_program_provenance_backfill", migration_context
            assert template_schema == schema_name, template_schema
            assert provenance == {
                "stronglifts-5x5": "SOURCE_ADAPTATION",
                "legacy-yfc-template": "YFC_GENERIC",
                "private-custom-template": "CUSTOM",
            }, (
                f"migration_context={migration_context!r}; template_schema={template_schema!r}; "
                f"template_count={template_count}; backfill_batch={backfill_batch!r}; "
                f"provenance={provenance!r}"
            )
            assert "exercise_replaced" not in revision_check
            assert "prescription_updated" not in revision_check
        finally:
            schema_engine.dispose()
    finally:
        with maintenance_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        maintenance_engine.dispose()
