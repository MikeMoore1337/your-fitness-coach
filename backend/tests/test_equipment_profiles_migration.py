import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
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


def test_sqlite_downgrade_removes_empty_columns(sqlite_connection):
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


def test_sqlite_downgrade_locks_out_writer_after_check(tmp_path):
    engine = sa.create_engine(
        f"sqlite:///{(tmp_path / 'equipment.db').as_posix()}", connect_args={"timeout": 0.2}
    )
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE user_profiles (id INTEGER PRIMARY KEY)")
            _migration(connection).upgrade()
            connection.exec_driver_sql("INSERT INTO user_profiles (id) VALUES (1)")

        def writer():
            try:
                with engine.begin() as connection:
                    connection.exec_driver_sql(
                        "UPDATE user_profiles SET equipment_profiles_revision=1 WHERE id=1"
                    )
                return "committed"
            except sa.exc.OperationalError:
                return "blocked"

        outcomes = []
        with ThreadPoolExecutor(max_workers=1) as executor, engine.begin() as connection:
            migration = _migration(connection)
            drop_column = migration.op.drop_column

            def interleaved_drop(*args, **kwargs):
                if not outcomes:
                    outcomes.append(executor.submit(writer).result(timeout=5))
                return drop_column(*args, **kwargs)

            migration.op.drop_column = interleaved_drop
            migration.downgrade()

        assert outcomes == ["blocked"]
    finally:
        engine.dispose()


def test_sqlite_downgrade_refuses_autocommit():
    engine = sa.create_engine("sqlite:///:memory:", isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("CREATE TABLE user_profiles (id INTEGER PRIMARY KEY)")
            migration = _migration(connection)
            migration.upgrade()
            connection.exec_driver_sql("INSERT INTO user_profiles (id) VALUES (1)")
            with pytest.raises(RuntimeError, match="requires a transaction"):
                migration.downgrade()
            assert "equipment_profiles" in {
                column["name"] for column in sa.inspect(connection).get_columns("user_profiles")
            }
    finally:
        engine.dispose()


def test_downgrade_refuses_an_unsupported_database(sqlite_connection):
    migration = _migration(sqlite_connection)
    migration.op.get_bind = lambda: SimpleNamespace(dialect=SimpleNamespace(name="unknown"))
    with pytest.raises(RuntimeError, match="locking is unsupported"):
        migration.downgrade()


@pytest.fixture
def postgres_migration():
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
            connection.commit()
            yield connection, migration
        finally:
            connection.rollback()
            connection.exec_driver_sql('SET search_path TO "public"')
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            connection.commit()


@pytest.mark.parametrize(
    ("column", "value_sql"),
    [
        ("equipment_profiles", '\'{"profiles":[{"name":"home"}]}\'::json'),
        ("active_equipment_profile_id", "'synthetic-profile'"),
        ("equipment_profiles_revision", "1"),
    ],
)
def test_postgres_downgrade_preserves_each_populated_column(postgres_migration, column, value_sql):
    connection, migration = postgres_migration
    connection.exec_driver_sql(f"INSERT INTO user_profiles (id, {column}) VALUES (1, {value_sql})")
    before = connection.exec_driver_sql(
        f"SELECT {column} FROM user_profiles WHERE id=1"
    ).scalar_one()
    with pytest.raises(RuntimeError, match="equipment profile data exists"):
        migration.downgrade()
    assert (
        connection.exec_driver_sql(f"SELECT {column} FROM user_profiles WHERE id=1").scalar_one()
        == before
    )


def test_postgres_downgrade_removes_empty_columns(postgres_migration):
    connection, migration = postgres_migration
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


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
def test_postgres_downgrade_rejects_stale_snapshot(postgres_migration, isolation):
    from fitminiapp_api.db.session import engine

    connection, migration = postgres_migration
    schema = connection.exec_driver_sql("SELECT current_schema()").scalar_one()
    connection.commit()
    connection.exec_driver_sql(f"SET TRANSACTION ISOLATION LEVEL {isolation}")
    connection.exec_driver_sql("SELECT count(*) FROM user_profiles").scalar_one()
    with engine.begin() as writer:
        writer.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        writer.exec_driver_sql(
            "INSERT INTO user_profiles (id, equipment_profiles_revision) VALUES (1, 9)"
        )
    with pytest.raises(RuntimeError, match="READ COMMITTED"):
        migration.downgrade()
    connection.rollback()
    assert (
        connection.exec_driver_sql(
            "SELECT equipment_profiles_revision FROM user_profiles WHERE id=1"
        ).scalar_one()
        == 9
    )
