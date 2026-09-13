from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, Column, Integer, MetaData, Table, create_engine, inspect
from sqlalchemy.exc import IntegrityError

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.food import (
    FoodCatalog,
    FoodNutrientsInput,
    UserFoodCreate,
    validate_gtin,
)
from fitminiapp_api.services.food_import import import_food_catalog
from fitminiapp_api.services.foods import (
    FoodError,
    calculate_food_nutrition,
    calculate_food_servings,
    create_user_food,
    get_owned_user_food,
    get_visible_food,
    list_visible_foods,
)


def _user_food_payload(**overrides: object) -> UserFoodCreate:
    values: dict[str, object] = {
        "name": "Овсяная каша",
        "energy_kcal_per_100g": "88.4",
        "protein_g_per_100g": "3.1",
        "fat_g_per_100g": "1.7",
        "carbs_g_per_100g": "15.0",
        "fiber_g_per_100g": "1.8",
        "standard_serving_amount": "1",
        "standard_serving_unit": "serving",
        "standard_serving_weight_g": "250",
    }
    values.update(overrides)
    return UserFoodCreate.model_validate(values)


def _catalog_payload(**food_overrides: object) -> dict[str, object]:
    food: dict[str, object] = {
        "external_id": "basic-oats-1",
        "food_type": "system",
        "name": "Овсяная крупа",
        "barcode": "4006381333931",
        "energy_kcal_per_100g": "366",
        "protein_g_per_100g": "12.3",
        "fat_g_per_100g": "6.1",
        "carbs_g_per_100g": "59.5",
        "fiber_g_per_100g": "8.5",
    }
    food.update(food_overrides)
    return {
        "schema_version": 1,
        "source": {
            "name": "reviewed-source",
            "version": "2026-08-18",
            "source_url": "https://data.example.test/catalog",
            "license": "Example Open Data License 1.0",
            "license_url": "https://data.example.test/license",
            "reviewed_by": "nutrition-data-owner",
            "reviewed_at": "2026-08-18",
            "license_verified": True,
        },
        "foods": [food],
    }


def _public_food(**overrides: object) -> Food:
    values: dict[str, object] = {
        "name": "Рис",
        "barcode": "4006381333931",
        "energy_kcal_per_100g": Decimal("360"),
        "protein_g_per_100g": Decimal("7"),
        "fat_g_per_100g": Decimal("1"),
        "carbs_g_per_100g": Decimal("79"),
        "food_type": "system",
        "owner_user_id": None,
        "provenance": "internal",
        "source_name": "yfc-reviewed",
        "trust_level": "verified",
        "status": "active",
    }
    values.update(overrides)
    return Food(**values)


def test_calculates_nutrients_by_mass_with_decimal_rounding() -> None:
    nutrients = FoodNutrientsInput(
        energy_kcal_per_100g="123.45",
        protein_g_per_100g="7.891",
        fat_g_per_100g="2.345",
        carbs_g_per_100g="15.678",
        fiber_g_per_100g=None,
    )

    result = calculate_food_nutrition(nutrients, Decimal("37.5"))

    assert result.weight_g == Decimal("37.500")
    assert result.energy_kcal == Decimal("46.29")
    assert result.protein_g == Decimal("2.959")
    assert result.fat_g == Decimal("0.879")
    assert result.carbs_g == Decimal("5.879")
    assert result.fiber_g is None


def test_calculates_nutrients_by_standard_serving() -> None:
    food = Food(
        standard_serving_weight_g=Decimal("30"),
        energy_kcal_per_100g=Decimal("400"),
        protein_g_per_100g=Decimal("20"),
        fat_g_per_100g=Decimal("10"),
        carbs_g_per_100g=Decimal("50"),
        fiber_g_per_100g=Decimal("5"),
    )

    result = calculate_food_servings(food, Decimal("1.5"))

    assert result.weight_g == Decimal("45.000")
    assert result.energy_kcal == Decimal("180.00")
    assert result.protein_g == Decimal("9.000")
    assert result.fiber_g == Decimal("2.250")


@pytest.mark.parametrize(
    "value",
    [Decimal("0"), Decimal("-1"), Decimal("0.0004"), Decimal("NaN")],
)
def test_calculation_rejects_invalid_mass(value: Decimal) -> None:
    with pytest.raises(FoodError):
        calculate_food_nutrition(FoodNutrientsInput(), value)


def test_validates_gtin_check_digit_and_standard_serving() -> None:
    assert validate_gtin("4006381333931") == "4006381333931"
    with pytest.raises(ValueError, match="check digit"):
        validate_gtin("4006381333932")
    with pytest.raises(ValidationError, match="provided together"):
        _user_food_payload(standard_serving_weight_g=None)
    with pytest.raises(ValidationError, match="must equal its weight"):
        _user_food_payload(
            standard_serving_amount="100",
            standard_serving_unit="g",
            standard_serving_weight_g="99",
        )


def test_user_foods_are_private_to_their_owner() -> None:
    with get_session_context() as db:
        first_user = db.query(User).filter(User.telegram_user_id == 2001).one()
        second_user = db.query(User).filter(User.telegram_user_id == 2002).one()
        first_food = create_user_food(db, first_user, _user_food_payload(name="Личный продукт"))
        second_food = create_user_food(db, second_user, _user_food_payload(name="Чужой продукт"))
        db.add(_public_food())
        db.flush()

        first_visible_ids = {food.id for food in list_visible_foods(db, first_user)}

        assert first_food.id in first_visible_ids
        assert second_food.id not in first_visible_ids
        assert {food.name for food in list_visible_foods(db, first_user)} == {
            "Личный продукт",
            "Рис",
        }
        with pytest.raises(FoodError, match="not found"):
            get_owned_user_food(db, first_user, second_food.id)
        with pytest.raises(FoodError, match="not found"):
            get_visible_food(db, first_user, second_food.id)


def test_database_rejects_external_food_without_complete_provenance() -> None:
    with pytest.raises(IntegrityError), get_session_context() as db:
        db.add(
            _public_food(
                provenance="external",
                source_name="external-source",
                external_id="row-1",
                source_license=None,
            )
        )


def test_barcode_uniqueness_is_scoped_to_catalog_or_user_owner() -> None:
    with pytest.raises(IntegrityError), get_session_context() as db:
        db.add_all([_public_food(name="Рис 1"), _public_food(name="Рис 2")])

    with get_session_context() as db:
        first_user = db.query(User).filter(User.telegram_user_id == 2001).one()
        second_user = db.query(User).filter(User.telegram_user_id == 2002).one()
        create_user_food(
            db,
            first_user,
            _user_food_payload(name="Мой штрихкод", barcode="4006381333931"),
        )
        create_user_food(
            db,
            second_user,
            _user_food_payload(name="Такой же личный штрихкод", barcode="4006381333931"),
        )


def test_catalog_requires_verified_license_and_import_is_idempotent() -> None:
    unverified = _catalog_payload()
    assert isinstance(unverified["source"], dict)
    unverified["source"]["license_verified"] = False
    with pytest.raises(ValidationError, match="license_verified"):
        FoodCatalog.model_validate(unverified)

    catalog = FoodCatalog.model_validate(_catalog_payload())
    with get_session_context() as db:
        first_result = import_food_catalog(db, catalog)
        db.flush()
        stored = db.query(Food).filter(Food.external_id == "basic-oats-1").one()
        assert stored.provenance == "external"
        assert stored.source_license_url == "https://data.example.test/license"
        assert stored.trust_level == "verified"

        updated_catalog = FoodCatalog.model_validate(_catalog_payload(name="Овсяная крупа цельная"))
        second_result = import_food_catalog(db, updated_catalog)
        db.flush()

        assert first_result.created == 1
        assert first_result.updated == 0
        assert second_result.created == 0
        assert second_result.updated == 1
        assert db.query(Food).count() == 1
        assert stored.name == "Овсяная крупа цельная"


def test_food_migration_upgrades_from_previous_head(tmp_path: Path) -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0034_food_domain_foundation.py"
    )
    spec = importlib.util.spec_from_file_location("food_domain_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "0033_auth_session_families"

    engine = create_engine(f"sqlite:///{(tmp_path / 'food-migration.db').as_posix()}")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        schema = inspect(connection)
        assert "foods" in schema.get_table_names()
        legacy_food_columns = {
            "nutrition_basis_kind",
            "nutrition_basis_amount",
            "nutrition_basis_unit",
            "canonical_facts",
            "nutrition_provenance",
            "canonical_complete",
            "catalog_quality",
        }
        assert {column["name"] for column in schema.get_columns("foods")} == {
            column.name
            for column in Food.__table__.columns
            if column.name != "search_text" and column.name not in legacy_food_columns
        }
        assert {constraint["name"] for constraint in schema.get_check_constraints("foods")} == {
            constraint.name
            for constraint in Food.__table__.constraints
            if isinstance(constraint, CheckConstraint)
            and constraint.name
            not in {
                "ck_foods_catalog_quality",
                "ck_foods_nutrition_basis_kind",
                "ck_foods_nutrition_basis_unit",
                "ck_foods_nutrition_basis_shape",
            }
        }
        assert {index["name"] for index in schema.get_indexes("foods")} == {
            "ix_foods_owner_status",
            "uq_foods_catalog_barcode",
            "uq_foods_external_source_id",
            "uq_foods_user_barcode",
        }
        migration.downgrade()
        assert "foods" not in inspect(connection).get_table_names()

    engine.dispose()
