import importlib.util
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration(name="0143_workout_set_sides"):
    path = Path(__file__).resolve().parents[1] / f"alembic/versions/{name}.py"
    spec = importlib.util.spec_from_file_location("workout_set_sides_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_preserves_legacy_and_refuses_to_drop_side_facts():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE user_workout_sets (id INTEGER PRIMARY KEY, actual_reps INTEGER, "
            "actual_weight NUMERIC(10,2), is_completed BOOLEAN)"
        )
        connection.exec_driver_sql("INSERT INTO user_workout_sets VALUES (1, 8, 40, TRUE)")
        connection.exec_driver_sql(
            "CREATE TABLE legacy_set_references (id INTEGER PRIMARY KEY, workout_set_id INTEGER "
            "REFERENCES user_workout_sets(id) ON DELETE CASCADE)"
        )
        connection.exec_driver_sql("INSERT INTO legacy_set_references VALUES (1, 1)")
        with Operations.context(MigrationContext.configure(connection)):
            migration = _migration()
            migration.upgrade()
            constraint = _migration("0144_workout_side_metadata_ck")
            constraint.upgrade()
            assert connection.exec_driver_sql(
                "SELECT actual_reps, actual_weight, execution_mode, first_side "
                "FROM user_workout_sets WHERE id=1"
            ).one() == (8, 40, None, None)
            assert (
                connection.exec_driver_sql("SELECT COUNT(*) FROM legacy_set_references").scalar()
                == 1
            )
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            for field, value in (("execution_mode", "invalid"), ("first_side", "both")):
                with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                    connection.exec_driver_sql(
                        f"UPDATE user_workout_sets SET {field} = '{value}' WHERE id=1"
                    )
            connection.exec_driver_sql(
                "INSERT INTO user_workout_set_sides "
                "(workout_set_id, side, actual_reps, actual_weight, is_completed) "
                "VALUES (1, 'left', 10, 18, TRUE)"
            )
            with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                connection.exec_driver_sql(
                    "INSERT INTO user_workout_set_sides (workout_set_id, side, is_completed) "
                    "VALUES (1, 'left', TRUE)"
                )
            with pytest.raises(RuntimeError, match="side-specific workout facts"):
                migration.downgrade()
            connection.exec_driver_sql("DELETE FROM user_workout_set_sides")
            constraint.downgrade()
            migration.downgrade()
            assert connection.exec_driver_sql(
                "SELECT actual_reps, actual_weight FROM user_workout_sets WHERE id=1"
            ).one() == (8, 40)
            assert (
                connection.exec_driver_sql("SELECT COUNT(*) FROM legacy_set_references").scalar()
                == 1
            )
    engine.dispose()


def test_sqlite_constraint_migration_refuses_foreign_key_cascade():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.exec_driver_sql("CREATE TABLE user_workout_sets (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO user_workout_sets VALUES (1)")
            with Operations.context(MigrationContext.configure(connection)):
                _migration().upgrade()
                connection.exec_driver_sql(
                    "INSERT INTO user_workout_set_sides (workout_set_id, side, is_completed) "
                    "VALUES (1, 'left', TRUE)"
                )
                with pytest.raises(RuntimeError, match="foreign keys disabled"):
                    _migration("0144_workout_side_metadata_ck").upgrade()
            assert (
                connection.exec_driver_sql("SELECT COUNT(*) FROM user_workout_sets").scalar() == 1
            )
            assert (
                connection.exec_driver_sql("SELECT COUNT(*) FROM user_workout_set_sides").scalar()
                == 1
            )
    finally:
        engine.dispose()


def test_postgresql_migration_constraints_and_preservation():
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("Requires an isolated PostgreSQL test database")
    engine = sa.create_engine(url)
    schema = f"issue_832_{uuid.uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            connection.exec_driver_sql(
                "CREATE TABLE user_workout_sets (id INTEGER PRIMARY KEY, actual_reps INTEGER, "
                "actual_weight NUMERIC(10,2), is_completed BOOLEAN)"
            )
            connection.exec_driver_sql("INSERT INTO user_workout_sets VALUES (1, 8, 40, TRUE)")
            connection.exec_driver_sql(
                "CREATE TABLE legacy_set_references (id INTEGER PRIMARY KEY, workout_set_id INTEGER "
                "REFERENCES user_workout_sets(id) ON DELETE CASCADE)"
            )
            connection.exec_driver_sql("INSERT INTO legacy_set_references VALUES (1, 1)")
            with Operations.context(MigrationContext.configure(connection)):
                migration = _migration()
                migration.upgrade()
                constraint = _migration("0144_workout_side_metadata_ck")
                constraint.upgrade()
                assert connection.exec_driver_sql(
                    "SELECT actual_reps, actual_weight, execution_mode FROM user_workout_sets"
                ).one() == (8, 40, None)
                assert (
                    connection.exec_driver_sql(
                        "SELECT COUNT(*) FROM legacy_set_references"
                    ).scalar()
                    == 1
                )
                with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                    connection.exec_driver_sql(
                        "UPDATE user_workout_sets SET execution_mode = 'invalid' WHERE id=1"
                    )
                with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                    connection.exec_driver_sql(
                        "UPDATE user_workout_sets SET first_side = 'both' WHERE id=1"
                    )
                connection.exec_driver_sql(
                    "INSERT INTO user_workout_set_sides "
                    "(workout_set_id, side, actual_reps, actual_weight, is_completed) "
                    "VALUES (1, 'left', 10, 18, TRUE)"
                )
                with pytest.raises(RuntimeError, match="side-specific workout facts"):
                    migration.downgrade()
                connection.exec_driver_sql("DELETE FROM user_workout_set_sides")
                constraint.downgrade()
                migration.downgrade()
                assert connection.exec_driver_sql(
                    "SELECT actual_reps, actual_weight FROM user_workout_sets"
                ).one() == (8, 40)
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        engine.dispose()
