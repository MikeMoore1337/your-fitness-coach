import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATIONS = {
    "notes": "0139_workout_exercise_notes.py",
    "imports": "0148_program_import_self_assignment.py",
}


def _migration(connection, name):
    path = Path(__file__).resolve().parents[1] / "alembic/versions" / MIGRATIONS[name]
    spec = importlib.util.spec_from_file_location(f"downgrade_{name}", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = Operations(MigrationContext.configure(connection))
    return migration


@pytest.fixture(params=["sqlite", "postgresql"])
def database(request, tmp_path):
    if request.param == "sqlite":
        engine = sa.create_engine(
            f"sqlite:///{(tmp_path / 'downgrade.db').as_posix()}", connect_args={"timeout": 0.2}
        )
        schema = None
    else:
        from fitminiapp_api.db.session import engine

        if engine.dialect.name != "postgresql":
            pytest.skip("requires PostgreSQL")
        schema = f"downgrade_lock_{uuid4().hex}"

    with engine.connect() as connection:
        try:
            if schema:
                connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                connection.exec_driver_sql(f'SET search_path TO "{schema}"')
                connection.commit()
            yield engine, connection, schema
        finally:
            connection.rollback()
            if schema:
                connection.exec_driver_sql('SET search_path TO "public"')
                connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                connection.commit()
    if not schema:
        engine.dispose()


def _setup(connection, name):
    if name == "notes":
        connection.exec_driver_sql("CREATE TABLE user_workouts (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO user_workouts (id) VALUES (1)")
        connection.exec_driver_sql("INSERT INTO users (id) VALUES (1)")
    else:
        connection.exec_driver_sql("CREATE TABLE program_imports (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO program_imports (id) VALUES (1)")
    migration = _migration(connection, name)
    migration.upgrade()
    connection.commit()
    return migration


def _write(connection, name):
    if name == "notes":
        connection.exec_driver_sql(
            "INSERT INTO workout_exercise_notes "
            "(id, workout_id, workout_exercise_id, exercise_id, context_key, body, tags, "
            "version, created_at, updated_at) "
            "VALUES (1, 1, 1, 1, 'synthetic', 'sentinel', '[]', 1, "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        )
    else:
        connection.exec_driver_sql(
            "UPDATE program_imports SET self_assigned_program_id=123 WHERE id=1"
        )


@pytest.mark.parametrize("name", ["notes", "imports"])
def test_empty_downgrade_succeeds(database, name):
    _, connection, _ = database
    migration = _setup(connection, name)
    migration.downgrade()
    if name == "notes":
        assert not sa.inspect(connection).has_table("workout_exercise_notes")
        assert not sa.inspect(connection).has_table("workout_exercise_note_mutations")
    else:
        assert {
            column["name"] for column in sa.inspect(connection).get_columns("program_imports")
        } == {"id"}


@pytest.mark.parametrize("name", ["notes", "imports"])
def test_downgrade_preserves_committed_data(database, name):
    _, connection, _ = database
    migration = _setup(connection, name)
    _write(connection, name)
    connection.commit()
    with pytest.raises(RuntimeError):
        migration.downgrade()
    if name == "notes":
        assert (
            connection.exec_driver_sql("SELECT body FROM workout_exercise_notes").scalar_one()
            == "sentinel"
        )
    else:
        assert (
            connection.exec_driver_sql(
                "SELECT self_assigned_program_id FROM program_imports"
            ).scalar_one()
            == 123
        )


def test_downgrade_preserves_request_hash_alone(database):
    _, connection, _ = database
    migration = _setup(connection, "imports")
    connection.exec_driver_sql(
        "UPDATE program_imports SET self_assignment_request_hash='sentinel' WHERE id=1"
    )
    connection.commit()
    with pytest.raises(RuntimeError):
        migration.downgrade()
    assert (
        connection.exec_driver_sql(
            "SELECT self_assignment_request_hash FROM program_imports"
        ).scalar_one()
        == "sentinel"
    )


def test_sqlite_downgrade_preserves_orphan_mutation(tmp_path):
    engine = sa.create_engine(f"sqlite:///{(tmp_path / 'orphan.db').as_posix()}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE user_workouts (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            migration = _migration(connection, "notes")
            migration.upgrade()
            connection.exec_driver_sql(
                "INSERT INTO workout_exercise_note_mutations "
                "(id, note_id, user_id, mutation_id, request_fingerprint, applied_version) "
                "VALUES (1, 42, 1, 'sentinel', 'fingerprint', 1)"
            )
            with pytest.raises(RuntimeError):
                migration.downgrade()
            assert (
                connection.exec_driver_sql(
                    "SELECT mutation_id FROM workout_exercise_note_mutations"
                ).scalar_one()
                == "sentinel"
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("name", ["notes", "notes_mutations", "imports"])
def test_downgrade_blocks_writes_after_check(database, name):
    engine, connection, schema = database
    migration = _setup(connection, "notes" if name == "notes_mutations" else name)
    outcomes = []

    def writer():
        try:
            with engine.begin() as other:
                if schema:
                    other.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                    other.exec_driver_sql("SET LOCAL lock_timeout = '200ms'")
                if name == "notes_mutations":
                    other.exec_driver_sql(
                        "UPDATE workout_exercise_note_mutations SET id=id WHERE 1=0"
                    )
                else:
                    _write(other, name)
            return "committed"
        except sa.exc.OperationalError as exc:
            if schema:
                assert getattr(exc.orig, "sqlstate", None) == "55P03"
            else:
                assert "database is locked" in str(exc.orig)
            return "blocked"

    operation = "drop_table" if name.startswith("notes") else "drop_column"
    drop = getattr(migration.op, operation)
    with ThreadPoolExecutor(max_workers=1) as executor:

        def interleaved_drop(*args, **kwargs):
            if not outcomes:
                outcomes.append(executor.submit(writer).result(timeout=5))
                assert outcomes == ["blocked"]
            return drop(*args, **kwargs)

        setattr(migration.op, operation, interleaved_drop)
        migration.downgrade()
    assert outcomes == ["blocked"]


@pytest.mark.parametrize("name", ["notes", "imports"])
def test_downgrade_refuses_an_inflight_write(database, name):
    engine, connection, schema = database
    migration = _setup(connection, name)
    with engine.connect() as writer:
        if schema:
            writer.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        _write(writer, name)
        with pytest.raises(sa.exc.OperationalError) as caught:
            migration.downgrade()
        if schema:
            assert getattr(caught.value.orig, "sqlstate", None) == "55P03"
        else:
            assert "database is locked" in str(caught.value.orig)
        connection.rollback()
        writer.commit()

    with pytest.raises(RuntimeError):
        migration.downgrade()
    connection.rollback()
    if name == "notes":
        assert (
            connection.exec_driver_sql("SELECT body FROM workout_exercise_notes").scalar_one()
            == "sentinel"
        )
    else:
        assert (
            connection.exec_driver_sql(
                "SELECT self_assigned_program_id FROM program_imports"
            ).scalar_one()
            == 123
        )


@pytest.mark.parametrize("name", ["notes", "imports"])
@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
def test_postgres_downgrade_does_not_use_a_stale_snapshot(database, name, isolation):
    engine, connection, schema = database
    if not schema:
        pytest.skip("requires PostgreSQL")
    migration = _setup(connection, name)
    connection.exec_driver_sql(f"SET TRANSACTION ISOLATION LEVEL {isolation}")
    table = "workout_exercise_notes" if name == "notes" else "program_imports"
    connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one()
    with engine.begin() as writer:
        writer.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        _write(writer, name)

    with pytest.raises(RuntimeError, match="READ COMMITTED"):
        migration.downgrade()
    connection.rollback()
    if name == "notes":
        assert (
            connection.exec_driver_sql("SELECT body FROM workout_exercise_notes").scalar_one()
            == "sentinel"
        )
    else:
        assert (
            connection.exec_driver_sql(
                "SELECT self_assigned_program_id FROM program_imports"
            ).scalar_one()
            == 123
        )


@pytest.mark.parametrize("name", ["notes", "imports"])
def test_sqlite_wal_downgrade_does_not_use_a_stale_snapshot(tmp_path, name):
    engine = sa.create_engine(
        f"sqlite:///{(tmp_path / 'wal.db').as_posix()}", connect_args={"timeout": 0.2}
    )
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one() == "wal"
            connection.commit()
            migration = _setup(connection, name)
            connection.exec_driver_sql("BEGIN")
            table = "workout_exercise_notes" if name == "notes" else "program_imports"
            connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one()
            with engine.begin() as writer:
                _write(writer, name)
            with pytest.raises(sa.exc.OperationalError, match="database is locked"):
                migration.downgrade()
            connection.rollback()
            if name == "notes":
                assert (
                    connection.exec_driver_sql(
                        "SELECT body FROM workout_exercise_notes"
                    ).scalar_one()
                    == "sentinel"
                )
            else:
                assert (
                    connection.exec_driver_sql(
                        "SELECT self_assigned_program_id FROM program_imports"
                    ).scalar_one()
                    == 123
                )
    finally:
        engine.dispose()


@pytest.mark.parametrize("name", ["notes", "imports"])
def test_sqlite_downgrade_refuses_autocommit(name):
    engine = sa.create_engine("sqlite:///:memory:", isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            migration = _setup(connection, name)
            with pytest.raises(RuntimeError, match="requires a transaction"):
                migration.downgrade()
    finally:
        engine.dispose()


@pytest.mark.parametrize("name", ["notes", "imports"])
def test_downgrade_refuses_unsupported_database(database, name):
    _, connection, _ = database
    migration = _migration(connection, name)
    migration.op.get_bind = lambda: SimpleNamespace(dialect=SimpleNamespace(name="unknown"))
    with pytest.raises(RuntimeError, match="locking is unsupported"):
        migration.downgrade()
