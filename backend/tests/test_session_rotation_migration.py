from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0147_session_rotation.py"
    spec = importlib.util.spec_from_file_location("session_rotation_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_tables(connection):
    connection.exec_driver_sql("CREATE TABLE user_programs (id INTEGER PRIMARY KEY)")
    connection.exec_driver_sql(
        "CREATE TABLE user_workouts (id INTEGER PRIMARY KEY, user_program_id INTEGER, "
        "week_number INTEGER, day_number INTEGER, source_cycle_week INTEGER, status VARCHAR(32))"
    )
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX uq_user_workouts_cycle_occurrence ON user_workouts "
        "(user_program_id, week_number, day_number) WHERE source_cycle_week IS NOT NULL"
    )
    connection.exec_driver_sql("INSERT INTO user_programs (id) VALUES (1)")
    connection.exec_driver_sql("INSERT INTO user_workouts VALUES (1, 1, 1, 1, 1, 'completed')")


def _assert_constraints_and_rollback_guard(connection, migration):
    assert (
        connection.exec_driver_sql("SELECT schedule_mode FROM user_programs").scalar_one() is None
    )
    assert connection.exec_driver_sql(
        "SELECT status, source_cycle_week, rotation_epoch FROM user_workouts WHERE id=1"
    ).one() == ("completed", 1, None)
    with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
        connection.exec_driver_sql(
            "INSERT INTO user_workouts (id,user_program_id,week_number,day_number,"
            "source_cycle_week,status) VALUES (2,1,1,1,1,'planned')"
        )
    connection.exec_driver_sql(
        "INSERT INTO user_workouts (id,user_program_id,week_number,day_number,"
        "source_cycle_week,rotation_source_cycle_week,status,rotation_epoch,rotation_role,rotation_mutation_id) "
        "VALUES (3,1,1,1,NULL,1,'in_progress',2,'ordered','one')"
    )
    assert connection.exec_driver_sql(
        "SELECT source_cycle_week,rotation_source_cycle_week FROM user_workouts WHERE id=3"
    ).one() == (None, 1)
    with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
        connection.exec_driver_sql(
            "INSERT INTO user_workouts (id,user_program_id,week_number,day_number,"
            "status,rotation_epoch,rotation_mutation_id) VALUES (4,1,1,2,'in_progress',2,'two')"
        )
    with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
        connection.exec_driver_sql(
            "INSERT INTO user_workouts (id,user_program_id,week_number,day_number,"
            "status,rotation_epoch,rotation_mutation_id) VALUES (5,1,1,2,'skipped',2,'one')"
        )
    with pytest.raises(RuntimeError, match="Unsafe downgrade"):
        migration.downgrade()
    connection.exec_driver_sql("DELETE FROM user_workouts WHERE id=3")


def test_rotation_migration_preserves_calendar_and_guards_downgrade(tmp_path):
    engine = sa.create_engine(f"sqlite:///{(tmp_path / 'rotation.db').as_posix()}")
    with engine.begin() as connection:
        _create_legacy_tables(connection)
        migration = _migration()
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            _assert_constraints_and_rollback_guard(connection, migration)
            migration.downgrade()
        assert connection.exec_driver_sql("SELECT status FROM user_workouts").scalar_one() == (
            "completed"
        )
    engine.dispose()


def test_rotation_migration_postgres_preserves_calendar_and_guards_downgrade():
    from fitminiapp_api.db.session import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL")
    schema = f"rotation_migration_{uuid4().hex}"
    with engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET search_path TO "{schema}"')
        _create_legacy_tables(connection)
        connection.commit()
        migration = _migration()
        try:
            context = MigrationContext.configure(connection)
            with context.begin_transaction(), Operations.context(context):
                migration.upgrade()
            context = MigrationContext.configure(connection)
            with context.begin_transaction(), Operations.context(context):
                _assert_constraints_and_rollback_guard(connection, migration)
            context = MigrationContext.configure(connection)
            with context.begin_transaction(), Operations.context(context):
                migration.downgrade()
            assert connection.exec_driver_sql("SELECT status FROM user_workouts").scalar_one() == (
                "completed"
            )
            connection.commit()
        finally:
            connection.rollback()
            connection.exec_driver_sql('SET search_path TO "public"')
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            connection.commit()


def test_rotation_migration_rejects_a_wrong_existing_postgres_index():
    from fitminiapp_api.db.session import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL")
    schema = f"rotation_bad_index_{uuid4().hex}"
    with engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET search_path TO "{schema}"')
        _create_legacy_tables(connection)
        connection.exec_driver_sql("ALTER TABLE user_workouts ADD COLUMN rotation_epoch INTEGER")
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_user_workouts_rotation_mutation "
            "ON user_workouts (user_program_id) WHERE rotation_epoch IS NOT NULL"
        )
        connection.commit()
        try:
            migration = _migration()
            context = MigrationContext.configure(connection)
            with (
                pytest.raises(RuntimeError, match="Incomplete rotation mutation index"),
                context.begin_transaction(),
                Operations.context(context),
            ):
                migration.upgrade()
            assert connection.exec_driver_sql(
                "SELECT to_regclass('uq_user_workouts_cycle_occurrence') IS NOT NULL"
            ).scalar_one()
        finally:
            connection.rollback()
            connection.exec_driver_sql('SET search_path TO "public"')
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            connection.commit()
