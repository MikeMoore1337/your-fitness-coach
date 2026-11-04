import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration(connection, kind):
    filenames = {
        "0139": "0139_workout_exercise_notes.py",
        "0148": "0148_program_import_self_assignment.py",
    }
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / filenames[kind]
    spec = importlib.util.spec_from_file_location(f"migration_{kind}", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = Operations(MigrationContext.configure(connection))
    return migration


def _setup(connection, kind):
    if kind == "0139":
        connection.exec_driver_sql("CREATE TABLE user_workouts (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO user_workouts VALUES (1)")
    else:
        connection.exec_driver_sql("CREATE TABLE program_imports (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO program_imports VALUES (1)")
    migration = _migration(connection, kind)
    migration.upgrade()
    return migration


def _write(connection, kind):
    if kind == "0139":
        connection.exec_driver_sql(
            "INSERT INTO workout_exercise_notes "
            "(id, workout_id, workout_exercise_id, exercise_id, context_key, body, tags, "
            "version, created_at, updated_at) VALUES "
            "(1, 1, 1, 1, 'synthetic', 'sentinel', '[]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    else:
        connection.exec_driver_sql(
            "UPDATE program_imports SET self_assigned_program_id=123, "
            "self_assignment_request_hash='synthetic' WHERE id=1"
        )


@pytest.fixture(params=["sqlite", "postgresql"])
def target(request, tmp_path):
    if request.param == "sqlite":
        engine = sa.create_engine(
            f"sqlite:///{(tmp_path / 'guard.db').as_posix()}", connect_args={"timeout": 0.2}
        )
        schema = None
    else:
        from fitminiapp_api.db.session import engine

        if engine.dialect.name != "postgresql":
            pytest.skip("requires PostgreSQL")
        schema = f"downgrade_guard_{uuid4().hex}"
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
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
                connection.commit()
    if request.param == "sqlite":
        engine.dispose()


def _prepare_writer(writer, schema):
    if schema:
        writer.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        writer.exec_driver_sql("SET LOCAL lock_timeout = '300ms'")


@pytest.mark.parametrize("kind", ["0139", "0148"])
def test_empty_downgrade_removes_only_empty_objects(target, kind):
    _engine, connection, _schema = target
    migration = _setup(connection, kind)
    migration.downgrade()
    if kind == "0139":
        assert not sa.inspect(connection).has_table("workout_exercise_notes")
    else:
        assert {
            column["name"] for column in sa.inspect(connection).get_columns("program_imports")
        } == {"id"}


@pytest.mark.parametrize("kind", ["0139", "0148"])
def test_populated_downgrade_fails_and_preserves_data(target, kind):
    _engine, connection, _schema = target
    migration = _setup(connection, kind)
    _write(connection, kind)
    with pytest.raises(RuntimeError):
        migration.downgrade()
    if kind == "0139":
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


@pytest.mark.parametrize("kind", ["0139", "0148"])
def test_writer_cannot_commit_between_guard_and_ddl(target, kind):
    engine, connection, schema = target
    migration = _setup(connection, kind)
    connection.commit()
    method = "drop_table" if kind == "0139" else "drop_column"
    drop = getattr(migration.op, method)
    outcomes = []

    def interleaved_drop(*args, **kwargs):
        if not outcomes:
            try:
                with engine.begin() as writer:
                    _prepare_writer(writer, schema)
                    _write(writer, kind)
                outcomes.append("committed")
            except sa.exc.OperationalError as exc:
                if schema:
                    assert getattr(exc.orig, "sqlstate", None) == "55P03"
                else:
                    assert "locked" in str(exc).lower()
                outcomes.append("blocked")
        return drop(*args, **kwargs)

    setattr(migration.op, method, interleaved_drop)
    migration.downgrade()
    connection.commit()
    assert outcomes == ["blocked"]


@pytest.mark.parametrize("kind", ["0139", "0148"])
def test_inflight_writer_causes_safe_refusal_then_data_guard(target, kind):
    engine, connection, schema = target
    migration = _setup(connection, kind)
    connection.commit()
    with engine.connect() as writer:
        _prepare_writer(writer, schema)
        _write(writer, kind)
        if schema:
            connection.exec_driver_sql("SET LOCAL statement_timeout = '600ms'")
        with pytest.raises(sa.exc.OperationalError):
            migration.downgrade()
        connection.rollback()
        writer.commit()
    with pytest.raises(RuntimeError):
        migration.downgrade()
    connection.rollback()
    if kind == "0139":
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


@pytest.mark.parametrize("kind", ["0139", "0148"])
@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
def test_postgres_rejects_stale_transaction_snapshot(target, kind, isolation):
    engine, connection, schema = target
    if not schema:
        pytest.skip("requires PostgreSQL")
    migration = _setup(connection, kind)
    connection.commit()
    connection.exec_driver_sql(f"SET TRANSACTION ISOLATION LEVEL {isolation}")
    table = "workout_exercise_notes" if kind == "0139" else "program_imports"
    connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one()
    with engine.begin() as writer:
        _prepare_writer(writer, schema)
        _write(writer, kind)
    with pytest.raises(RuntimeError, match="READ COMMITTED"):
        migration.downgrade()
    connection.rollback()
    if kind == "0139":
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


@pytest.mark.parametrize("kind", ["0139", "0148"])
def test_postgres_autocommit_cannot_release_lock_before_ddl(target, kind):
    _engine, connection, schema = target
    if not schema:
        pytest.skip("requires PostgreSQL")
    migration = _setup(connection, kind)
    connection.commit()
    connection.execution_options(isolation_level="AUTOCOMMIT")
    with pytest.raises(sa.exc.DBAPIError) as error:
        migration.downgrade()
    assert getattr(error.value.orig, "sqlstate", None) == "25P01"
    connection.rollback()
    if kind == "0139":
        assert sa.inspect(connection).has_table("workout_exercise_notes")
    else:
        columns = {
            column["name"] for column in sa.inspect(connection).get_columns("program_imports")
        }
        assert {"self_assigned_program_id", "self_assignment_request_hash"} <= columns


@pytest.mark.parametrize("kind", ["0139", "0148"])
def test_downgrade_refuses_unknown_dialect(target, kind):
    _engine, connection, _schema = target
    migration = _migration(connection, kind)
    migration.op.get_bind = lambda: SimpleNamespace(dialect=SimpleNamespace(name="unknown"))
    with pytest.raises(RuntimeError, match="locking is unsupported"):
        migration.downgrade()


@pytest.mark.parametrize("kind", ["0139", "0148"])
def test_sqlite_downgrade_refuses_autocommit(kind):
    engine = sa.create_engine("sqlite:///:memory:", isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            migration = _setup(connection, kind)
            with pytest.raises(RuntimeError, match="requires a transaction"):
                migration.downgrade()
    finally:
        engine.dispose()
