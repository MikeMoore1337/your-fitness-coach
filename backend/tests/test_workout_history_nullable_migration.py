import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0141_workout_history_nullable.py"
    spec = importlib.util.spec_from_file_location("workout_history_nullable_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_history(connection):
    connection.exec_driver_sql("CREATE TABLE user_programs (id INTEGER PRIMARY KEY)")
    connection.exec_driver_sql(
        "CREATE TABLE user_workouts (id INTEGER PRIMARY KEY, user_program_id INTEGER NOT NULL "
        "REFERENCES user_programs(id), day_number INTEGER NOT NULL, week_number INTEGER NOT NULL, "
        "status TEXT NOT NULL)"
    )
    connection.exec_driver_sql(
        "CREATE TABLE user_workout_exercises (id INTEGER PRIMARY KEY, "
        "workout_id INTEGER REFERENCES user_workouts(id), prescribed_sets INTEGER NOT NULL, "
        "prescribed_reps VARCHAR(32) NOT NULL, rest_seconds INTEGER NOT NULL)"
    )
    connection.exec_driver_sql(
        "CREATE TABLE workout_adaptations (id INTEGER PRIMARY KEY, "
        "workout_id INTEGER REFERENCES user_workouts(id) ON DELETE CASCADE)"
    )
    connection.exec_driver_sql("INSERT INTO user_programs VALUES (1)")
    connection.exec_driver_sql("INSERT INTO user_workouts VALUES (1, 1, 2, 3, 'completed')")
    connection.exec_driver_sql("INSERT INTO user_workout_exercises VALUES (1, 1, 4, '8', 90)")
    connection.exec_driver_sql("INSERT INTO workout_adaptations VALUES (1, 1)")


def _assert_history(connection):
    assert connection.exec_driver_sql(
        "SELECT id, user_program_id, day_number, week_number, status FROM user_workouts"
    ).all() == [(1, 1, 2, 3, "completed")]
    assert connection.exec_driver_sql(
        "SELECT id, workout_id, prescribed_sets, prescribed_reps, rest_seconds "
        "FROM user_workout_exercises"
    ).all() == [(1, 1, 4, "8", 90)]
    assert connection.exec_driver_sql("SELECT * FROM workout_adaptations").all() == [(1, 1)]


def _assert_plan_guards(connection):
    statements = (
        "INSERT INTO user_workouts (id, user_program_id, day_number, week_number, status) "
        "VALUES (20, 1, NULL, 1, 'planned')",
        "INSERT INTO user_workouts (id, user_program_id, day_number, week_number, status, history_imported) "
        "VALUES (21, NULL, NULL, NULL, 'planned', TRUE)",
        "INSERT INTO user_workout_exercises "
        "(id, workout_id, prescribed_sets, prescribed_reps, rest_seconds) "
        "VALUES (20, 1, NULL, '8', 90)",
        "INSERT INTO user_workout_exercises "
        "(id, workout_id, prescribed_sets, prescribed_reps, rest_seconds, history_imported) "
        "VALUES (21, 1, 1, '8', 90, TRUE)",
    )
    for statement in statements:
        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.exec_driver_sql(statement)


def test_nullable_migration_preserves_sqlite_history_and_guards_downgrade():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _create_history(connection)
        with Operations.context(MigrationContext.configure(connection)):
            _migration().upgrade()
            _assert_history(connection)
            _assert_plan_guards(connection)
            connection.exec_driver_sql(
                "INSERT INTO user_workouts "
                "(id, user_program_id, day_number, week_number, status, history_imported) "
                "VALUES (2, NULL, NULL, NULL, 'completed', TRUE)"
            )
            with pytest.raises(RuntimeError, match="without program or prescription"):
                _migration().downgrade()
    engine.dispose()


def test_sqlite_foreign_keys_fail_closed_before_any_cascading_delete():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        _create_history(connection)
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="foreign keys disabled"):
                _migration().upgrade()
            _assert_history(connection)
    engine.dispose()


def test_postgres_nullable_migration_preserves_data_and_refuses_unsafe_downgrade():
    from uuid import uuid4

    from fitminiapp_api.db.session import engine as app_engine

    if app_engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL")
    schema = f"test_history_import_{uuid4().hex}"
    with app_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    try:
        with app_engine.begin() as connection:
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            _create_history(connection)
            with Operations.context(MigrationContext.configure(connection)):
                _migration().upgrade()
                _assert_history(connection)
                _assert_plan_guards(connection)
                connection.exec_driver_sql(
                    "INSERT INTO user_workouts "
                    "(id, user_program_id, day_number, week_number, status, history_imported) "
                    "VALUES (2, NULL, NULL, NULL, 'completed', TRUE)"
                )
                with pytest.raises(RuntimeError, match="without program or prescription"):
                    _migration().downgrade()
                connection.exec_driver_sql("DELETE FROM user_workouts WHERE id=2")
                _migration().downgrade()
                _assert_history(connection)
    finally:
        with app_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
