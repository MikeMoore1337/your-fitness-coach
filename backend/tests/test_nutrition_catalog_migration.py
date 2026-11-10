import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from fitminiapp_api.db.session import engine


def _migration(name):
    path = Path(__file__).resolve().parents[1] / "alembic/versions" / f"{name}.py"
    spec = spec_from_file_location(name, path)
    assert spec and spec.loader
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_sqlite_catalog_migration_preserves_existing_serving_label():
    migrations = [
        _migration("0154_nutrition_catalog_import"),
        _migration("0155_nutrition_catalog_indexes"),
        _migration("0156_nutrition_catalog_check"),
    ]
    label = json.dumps(
        {
            "source_basis": "per_serving",
            "serving_size": {"amount": "50", "unit": "ml"},
            "normalized_facts": {
                name: {"value": "1", "basis_ref": "per_100_ml"}
                for name in ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")
            },
        }
    )
    with sa.create_engine("sqlite://", poolclass=sa.pool.NullPool).connect() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE foods (id INTEGER PRIMARY KEY, food_type VARCHAR(16) NOT NULL, "
            "source_name VARCHAR(64), status TEXT NOT NULL, catalog_identity VARCHAR(512), "
            "energy_kcal_per_100g NUMERIC, protein_g_per_100g NUMERIC, "
            "fat_g_per_100g NUMERIC, carbs_g_per_100g NUMERIC, "
            "canonical_complete BOOLEAN, canonical_facts JSON, nutrition_basis_kind TEXT, "
            "standard_serving_amount NUMERIC, standard_serving_unit TEXT, "
            "CONSTRAINT ck_foods_active_nutrients CHECK "
            "(status <> 'active' OR (energy_kcal_per_100g IS NOT NULL "
            "AND protein_g_per_100g IS NOT NULL AND fat_g_per_100g IS NOT NULL "
            "AND carbs_g_per_100g IS NOT NULL) OR canonical_complete = true))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE nutrition_import_drafts (id TEXT PRIMARY KEY, owner_user_id INTEGER NOT NULL)"
        )
        connection.execute(
            sa.text(
                "INSERT INTO foods (id, food_type, source_name, status, canonical_complete, "
                "canonical_facts, nutrition_basis_kind, standard_serving_amount, standard_serving_unit) VALUES "
                "(1, 'branded', 'yfc_community', 'active', true, :facts, 'per_100_ml', 50, 'ml')"
            ),
            {"facts": label},
        )
        connection.commit()
        for migration in migrations:
            context = MigrationContext.configure(connection)
            with context.begin_transaction(), Operations.context(context):
                migration.upgrade()
        assert connection.exec_driver_sql("SELECT count(*) FROM foods").scalar_one() == 1
        invalid = json.loads(label)
        invalid["serving_size"]["unit"] = "g"
        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.execute(
                sa.text(
                    "INSERT INTO foods (id, food_type, source_name, status, canonical_complete, "
                    "canonical_facts, nutrition_basis_kind, standard_serving_amount, standard_serving_unit) VALUES "
                    "(2, 'branded', 'yfc_community', 'active', true, :facts, 'per_100_ml', 50, 'ml')"
                ),
                {"facts": json.dumps(invalid)},
            )


def test_postgres_catalog_migration_enforces_identity_and_guards_data():
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL concurrent index and constraints")
    schema = f"catalog_migration_{uuid4().hex}"
    migrations = [
        _migration("0154_nutrition_catalog_import"),
        _migration("0155_nutrition_catalog_indexes"),
        _migration("0156_nutrition_catalog_check"),
    ]
    with engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET search_path TO "{schema}"')
        connection.exec_driver_sql(
            "CREATE TABLE foods (id INTEGER PRIMARY KEY, food_type VARCHAR(16) NOT NULL, "
            "source_name VARCHAR(64), status TEXT NOT NULL, catalog_identity VARCHAR(512), "
            "energy_kcal_per_100g NUMERIC, protein_g_per_100g NUMERIC, "
            "fat_g_per_100g NUMERIC, carbs_g_per_100g NUMERIC, "
            "canonical_complete BOOLEAN, canonical_facts JSON, nutrition_basis_kind TEXT, "
            "standard_serving_amount NUMERIC, standard_serving_unit TEXT, "
            "CONSTRAINT ck_foods_active_nutrients CHECK "
            "(status <> 'active' OR (energy_kcal_per_100g IS NOT NULL "
            "AND protein_g_per_100g IS NOT NULL AND fat_g_per_100g IS NOT NULL "
            "AND carbs_g_per_100g IS NOT NULL) OR canonical_complete = true))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE nutrition_import_drafts (id TEXT PRIMARY KEY, owner_user_id INTEGER NOT NULL)"
        )
        serving_label = json.dumps(
            {
                "source_basis": "per_serving",
                "serving_size": {"amount": "50", "unit": "ml"},
                "normalized_facts": {
                    name: {"value": "1", "basis_ref": "per_100_ml"}
                    for name in ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")
                },
            }
        )
        connection.execute(
            sa.text(
                "INSERT INTO foods (id, food_type, source_name, status, canonical_complete, "
                "canonical_facts, nutrition_basis_kind, standard_serving_amount, standard_serving_unit) VALUES "
                "(8, 'branded', 'yfc_community', 'active', true, :facts, 'per_100_ml', 50, 'ml')"
            ),
            {"facts": serving_label},
        )
        connection.commit()
        try:
            for migration in migrations:
                context = MigrationContext.configure(connection)
                with context.begin_transaction(), Operations.context(context):
                    migration.upgrade()
            context = MigrationContext.configure(connection)
            with context.begin_transaction(), Operations.context(context):
                migrations[1].upgrade()
            canonical = json.dumps(
                {
                    "source_basis": "per_100_ml",
                    "normalized_facts": {
                        name: {"value": "1", "basis_ref": "per_100_ml"}
                        for name in ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")
                    },
                }
            )
            connection.execute(
                sa.text(
                    "INSERT INTO foods (id, food_type, source_name, status, catalog_identity, "
                    "canonical_complete, canonical_facts, nutrition_basis_kind) VALUES "
                    "(1, 'system', 'yfc_community', 'active', 'same', true, :facts, 'per_100_ml')"
                ),
                {"facts": canonical},
            )
            connection.exec_driver_sql(
                "INSERT INTO foods (id, food_type, source_name, status, canonical_complete) "
                "VALUES (6, 'system', 'yfc-test', 'active', true)"
            )
            with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                connection.execute(
                    sa.text(
                        "INSERT INTO foods (id, food_type, source_name, status, catalog_identity, "
                        "canonical_complete, canonical_facts, nutrition_basis_kind) VALUES "
                        "(2, 'branded', 'yfc_community', 'active', 'same', true, :facts, 'per_100_ml')"
                    ),
                    {"facts": canonical},
                )
            wrong_basis = json.loads(canonical)
            wrong_basis["normalized_facts"]["protein_g"]["basis_ref"] = "per_100_g"
            with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                connection.execute(
                    sa.text(
                        "INSERT INTO foods (id, food_type, source_name, status, canonical_complete, "
                        "canonical_facts, nutrition_basis_kind) VALUES "
                        "(7, 'system', 'yfc_community', 'active', true, :facts, 'per_100_ml')"
                    ),
                    {"facts": json.dumps(wrong_basis)},
                )
            invalid_serving = json.loads(serving_label)
            invalid_serving["serving_size"]["unit"] = "g"
            with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                connection.execute(
                    sa.text(
                        "INSERT INTO foods (id, food_type, source_name, status, canonical_complete, "
                        "canonical_facts, nutrition_basis_kind, standard_serving_amount, standard_serving_unit) VALUES "
                        "(9, 'branded', 'yfc_community', 'active', true, :facts, 'per_100_ml', 50, 'ml')"
                    ),
                    {"facts": json.dumps(invalid_serving)},
                )
            with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                connection.exec_driver_sql(
                    "INSERT INTO foods (id, food_type, source_name, status, canonical_complete) "
                    "VALUES (3, 'system', 'yfc_community', 'active', true)"
                )
            with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                connection.exec_driver_sql(
                    "INSERT INTO foods (id, food_type, source_name, status, canonical_complete, "
                    "canonical_facts, nutrition_basis_kind) VALUES "
                    "(4, 'system', 'yfc_community', 'active', true, '{}', 'per_100_ml')"
                )
            with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                connection.execute(
                    sa.text(
                        "INSERT INTO foods (id, food_type, source_name, status, canonical_complete, "
                        "canonical_facts) VALUES (5, 'system', 'yfc_community', 'active', true, :facts)"
                    ),
                    {"facts": canonical},
                )
            connection.commit()
            context = MigrationContext.configure(connection)
            with (
                pytest.raises(RuntimeError, match="Cannot discard"),
                context.begin_transaction(),
                Operations.context(context),
            ):
                migrations[2].downgrade()
            assert connection.exec_driver_sql("SELECT count(*) FROM foods").scalar_one() == 3
        finally:
            connection.rollback()
            connection.exec_driver_sql('SET search_path TO "public"')
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            connection.commit()


@pytest.mark.parametrize(
    "column,predicate", [("status", ""), ("catalog_identity", " WHERE status = 'active'")]
)
def test_postgres_catalog_migration_does_not_adopt_an_unrelated_index(column, predicate):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL concurrent index")
    schema = f"catalog_bad_index_{uuid4().hex}"
    migration = _migration("0155_nutrition_catalog_indexes")
    with engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET search_path TO "{schema}"')
        connection.exec_driver_sql(
            "CREATE TABLE foods (id INTEGER PRIMARY KEY, status TEXT, catalog_identity VARCHAR(512), "
            "food_type VARCHAR(16), source_name VARCHAR(64))"
        )
        connection.exec_driver_sql(
            f"CREATE UNIQUE INDEX uq_foods_community_shared_identity ON foods ({column}){predicate}"
        )
        connection.commit()
        try:
            context = MigrationContext.configure(connection)
            with (
                pytest.raises(RuntimeError, match="manual verification"),
                context.begin_transaction(),
                Operations.context(context),
            ):
                migration.upgrade()
            assert (
                connection.exec_driver_sql(
                    "SELECT pg_get_indexdef('uq_foods_community_shared_identity'::regclass, 1, true)"
                ).scalar_one()
                == column
            )
        finally:
            connection.rollback()
            connection.exec_driver_sql('SET search_path TO "public"')
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            connection.commit()


def test_postgres_catalog_migration_rejects_wrong_confirmation_index():
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL concurrent index")
    schema = f"catalog_bad_confirm_{uuid4().hex}"
    migration = _migration("0155_nutrition_catalog_indexes")
    with engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET search_path TO "{schema}"')
        connection.exec_driver_sql(
            "CREATE TABLE foods (id INTEGER PRIMARY KEY, catalog_identity VARCHAR(512), "
            "food_type VARCHAR(16), source_name VARCHAR(64))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE nutrition_import_drafts (owner_user_id INTEGER, catalog_confirm_key_hash VARCHAR(64))"
        )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_nutrition_import_owner_catalog_confirm "
            "ON nutrition_import_drafts (owner_user_id)"
        )
        connection.commit()
        try:
            context = MigrationContext.configure(connection)
            with (
                pytest.raises(
                    RuntimeError, match="confirmation index requires manual verification"
                ),
                context.begin_transaction(),
                Operations.context(context),
            ):
                migration.upgrade()
            assert (
                connection.exec_driver_sql(
                    "SELECT indnkeyatts FROM pg_index WHERE indexrelid = "
                    "'uq_nutrition_import_owner_catalog_confirm'::regclass"
                ).scalar_one()
                == 1
            )
        finally:
            connection.rollback()
            connection.exec_driver_sql('SET search_path TO "public"')
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            connection.commit()
