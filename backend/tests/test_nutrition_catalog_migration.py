import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from fitminiapp_api.db.session import engine


def test_postgres_catalog_migration_enforces_identity_and_guards_data():
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL concurrent index and constraints")
    schema = f"catalog_migration_{uuid4().hex}"
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0154_nutrition_catalog_import.py"
    spec = spec_from_file_location("nutrition_catalog_migration", path)
    assert spec and spec.loader
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET search_path TO "{schema}"')
        connection.exec_driver_sql(
            "CREATE TABLE foods (id INTEGER PRIMARY KEY, food_type TEXT NOT NULL, "
            "source_name TEXT, status TEXT NOT NULL, catalog_identity VARCHAR(512), "
            "energy_kcal_per_100g NUMERIC, protein_g_per_100g NUMERIC, "
            "fat_g_per_100g NUMERIC, carbs_g_per_100g NUMERIC, "
            "canonical_complete BOOLEAN, canonical_facts JSON, nutrition_basis_kind TEXT, "
            "CONSTRAINT ck_foods_active_nutrients CHECK "
            "(status <> 'active' OR (energy_kcal_per_100g IS NOT NULL "
            "AND protein_g_per_100g IS NOT NULL AND fat_g_per_100g IS NOT NULL "
            "AND carbs_g_per_100g IS NOT NULL)))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE nutrition_import_drafts (id TEXT PRIMARY KEY, owner_user_id INTEGER NOT NULL)"
        )
        connection.commit()
        try:
            context = MigrationContext.configure(connection)
            with context.begin_transaction(), Operations.context(context):
                migration.upgrade()
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
                migration.downgrade()
            assert connection.exec_driver_sql("SELECT count(*) FROM foods").scalar_one() == 2
        finally:
            connection.rollback()
            connection.exec_driver_sql('SET search_path TO "public"')
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            connection.commit()


def test_postgres_catalog_migration_does_not_adopt_an_unrelated_index():
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL concurrent index")
    schema = f"catalog_bad_index_{uuid4().hex}"
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0154_nutrition_catalog_import.py"
    spec = spec_from_file_location("nutrition_catalog_bad_index_migration", path)
    assert spec and spec.loader
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET search_path TO "{schema}"')
        connection.exec_driver_sql("CREATE TABLE foods (id INTEGER PRIMARY KEY, status TEXT)")
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_foods_community_shared_identity ON foods (status)"
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
                == "status"
            )
        finally:
            connection.rollback()
            connection.exec_driver_sql('SET search_path TO "public"')
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            connection.commit()
