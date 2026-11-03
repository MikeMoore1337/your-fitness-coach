import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration(connection):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0138_equipment_profiles.py"
    spec = importlib.util.spec_from_file_location("equipment_profiles_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = Operations(MigrationContext.configure(connection))
    return migration


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("equipment_profiles", '{"profiles": [{"name": "home"}]}'),
        ("active_equipment_profile_id", "synthetic-profile"),
        ("equipment_profiles_revision", 1),
    ],
)
def test_downgrade_refuses_to_discard_any_equipment_profile_data(column, value, sqlite_connection):
    connection = sqlite_connection
    connection.exec_driver_sql("CREATE TABLE user_profiles (id INTEGER PRIMARY KEY)")
    migration = _migration(connection)
    migration.upgrade()
    connection.execute(
        sa.text(f"INSERT INTO user_profiles (id, {column}) VALUES (1, :value)"), {"value": value}
    )

    with pytest.raises(RuntimeError, match="equipment profile"):
        migration.downgrade()

    assert (
        connection.execute(sa.text(f"SELECT {column} FROM user_profiles WHERE id=1")).scalar_one()
        == value
    )


@pytest.fixture
def sqlite_connection():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            yield connection
    finally:
        engine.dispose()


def test_downgrade_preserves_rows_when_all_new_columns_are_empty(sqlite_connection):
    connection = sqlite_connection
    connection.exec_driver_sql("CREATE TABLE user_profiles (id INTEGER PRIMARY KEY)")
    migration = _migration(connection)
    migration.upgrade()
    connection.exec_driver_sql("INSERT INTO user_profiles (id) VALUES (1)")

    migration.downgrade()

    assert connection.exec_driver_sql("SELECT id FROM user_profiles").scalar_one() == 1
    assert {column["name"] for column in sa.inspect(connection).get_columns("user_profiles")} == {
        "id"
    }


def test_postgres_downgrade_does_not_race_a_profile_update():
    from fitminiapp_api.db.session import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL")
    schema = f"equipment_downgrade_{uuid4().hex}"
    with engine.connect() as connection:
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
            connection.exec_driver_sql("CREATE TABLE user_profiles (id INTEGER PRIMARY KEY)")
            migration = _migration(connection)
            migration.upgrade()
            connection.exec_driver_sql("INSERT INTO user_profiles (id) VALUES (1)")
            connection.commit()

            with engine.connect() as writer:
                writer.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                writer.exec_driver_sql(
                    "UPDATE user_profiles SET equipment_profiles_revision=1 WHERE id=1"
                )
                connection.exec_driver_sql("SET statement_timeout = '1500ms'")
                with pytest.raises(sa.exc.OperationalError):
                    migration.downgrade()
                connection.rollback()
                writer.commit()

            with pytest.raises(RuntimeError, match="equipment profile"):
                migration.downgrade()
            connection.rollback()
            assert (
                connection.exec_driver_sql(
                    "SELECT equipment_profiles_revision FROM user_profiles WHERE id=1"
                ).scalar_one()
                == 1
            )
        finally:
            connection.rollback()
            connection.exec_driver_sql('SET search_path TO "public"')
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            connection.commit()
