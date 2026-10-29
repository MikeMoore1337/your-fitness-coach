from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load(number):
    path = next(
        (Path(__file__).resolve().parents[1] / "alembic" / "versions").glob(f"{number}_*.py")
    )
    spec = importlib.util.spec_from_file_location(f"cycle_storage_{number}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migrated_cycle_database(tmp_path):
    engine = sa.create_engine(f"sqlite:///{(tmp_path / 'cycles.db').as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE program_templates (id INTEGER PRIMARY KEY, default_duration_weeks INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE program_template_exercise_weeks (id INTEGER PRIMARY KEY, week_number INTEGER CONSTRAINT ck_program_template_exercise_weeks_number CHECK (week_number >= 1 AND week_number <= 24))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE user_workouts (id INTEGER PRIMARY KEY, user_program_id INTEGER NOT NULL, week_number INTEGER NOT NULL, day_number INTEGER NOT NULL, status TEXT, completed_at TEXT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE user_workout_sets (id INTEGER PRIMARY KEY, actual_weight NUMERIC, actual_reps INTEGER, is_completed BOOLEAN)"
        )
        connection.exec_driver_sql("INSERT INTO program_templates VALUES (1, 16)")
        connection.exec_driver_sql("INSERT INTO program_template_exercise_weeks VALUES (1, 1)")
        connection.exec_driver_sql(
            "INSERT INTO user_workouts VALUES (1, 1, 1, 1, 'completed', '2026-08-01 12:00:00')"
        )
        connection.exec_driver_sql("INSERT INTO user_workout_sets VALUES (1, 42.25, 8, 1)")
        with Operations.context(MigrationContext.configure(connection)):
            for number in ("0134", "0135", "0136"):
                _load(number).upgrade()
    yield engine
    engine.dispose()


def test_cycle_storage_upgrade_preserves_facts_and_enforces_opt_in_identity(
    migrated_cycle_database,
):
    with migrated_cycle_database.begin() as connection:
        assert connection.exec_driver_sql(
            "SELECT status, completed_at, plan_materialized, source_cycle_week FROM user_workouts WHERE id=1"
        ).one() == ("completed", "2026-08-01 12:00:00", None, None)
        assert connection.exec_driver_sql(
            "SELECT actual_weight, actual_reps, is_completed FROM user_workout_sets"
        ).one() == (42.25, 8, 1)
        connection.exec_driver_sql(
            "UPDATE program_templates SET default_duration_weeks=30 WHERE id=1"
        )
        connection.exec_driver_sql(
            "UPDATE program_template_exercise_weeks SET week_number=30 WHERE id=1"
        )
        connection.exec_driver_sql(
            "INSERT INTO user_workouts (id,user_program_id,week_number,day_number) VALUES (2,1,1,1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO user_workouts (id,user_program_id,week_number,day_number,source_cycle_week,cycle_iteration,plan_materialized) VALUES (3,2,30,1,3,10,0)"
        )
        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.exec_driver_sql(
                "INSERT INTO user_workouts (id,user_program_id,week_number,day_number,source_cycle_week) VALUES (4,2,30,1,3)"
            )
        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.exec_driver_sql(
                "UPDATE program_template_exercise_weeks SET week_number=0 WHERE id=1"
            )


def test_cycle_storage_downgrade_fails_closed_and_safe_roundtrip_preserves_rows(
    migrated_cycle_database,
):
    with migrated_cycle_database.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE program_templates SET default_duration_weeks=30 WHERE id=1"
        )
        connection.exec_driver_sql(
            "UPDATE program_template_exercise_weeks SET week_number=30 WHERE id=1"
        )
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="Unsafe downgrade"):
                _load("0136").downgrade()
            with pytest.raises(RuntimeError, match="Unsafe downgrade"):
                _load("0135").downgrade()
            connection.exec_driver_sql(
                "UPDATE program_templates SET default_duration_weeks=16 WHERE id=1"
            )
            connection.exec_driver_sql(
                "UPDATE program_template_exercise_weeks SET week_number=1 WHERE id=1"
            )
            connection.exec_driver_sql("UPDATE user_workouts SET source_cycle_week=1 WHERE id=1")
            with pytest.raises(RuntimeError, match="Unsafe downgrade"):
                _load("0134").downgrade()
            connection.exec_driver_sql("UPDATE user_workouts SET source_cycle_week=NULL WHERE id=1")
            for number in ("0136", "0135", "0134"):
                _load(number).downgrade()
        columns = {item["name"] for item in sa.inspect(connection).get_columns("user_workouts")}
        assert "source_cycle_week" not in columns and "plan_materialized" not in columns
        assert connection.exec_driver_sql(
            "SELECT status, completed_at FROM user_workouts WHERE id=1"
        ).one() == ("completed", "2026-08-01 12:00:00")
        assert connection.exec_driver_sql(
            "SELECT actual_weight, actual_reps FROM user_workout_sets"
        ).one() == (42.25, 8)
