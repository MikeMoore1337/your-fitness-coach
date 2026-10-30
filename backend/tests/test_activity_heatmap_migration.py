import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations

from alembic import command


def test_utc_completion_migration_preserves_existing_and_blocks_data_loss():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0134_workout_completed_at_utc.py"
    spec = importlib.util.spec_from_file_location("activity_heatmap_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE user_workouts (id INTEGER PRIMARY KEY)"))
        connection.execute(sa.text("INSERT INTO user_workouts (id) VALUES (1)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert (
            connection.execute(sa.text("SELECT completed_at_utc FROM user_workouts")).scalar()
            is None
        )
        connection.execute(
            sa.text("UPDATE user_workouts SET completed_at_utc = '2026-03-08 04:30:00'")
        )
        with pytest.raises(RuntimeError, match="Cannot discard"):
            migration.downgrade()
        assert connection.execute(sa.text("SELECT completed_at_utc FROM user_workouts")).scalar()
    engine.dispose()


@pytest.mark.parametrize(
    "starting_revision", ["0134_workout_completed_at_utc", "0136_program_week_unbounded"]
)
def test_activity_and_cycle_migrations_converge_without_rewriting_facts(starting_revision):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        for statement in (
            "CREATE TABLE program_templates (id INTEGER PRIMARY KEY, default_duration_weeks INTEGER)",
            "CREATE TABLE program_template_exercise_weeks (id INTEGER PRIMARY KEY, week_number INTEGER CONSTRAINT ck_program_template_exercise_weeks_number CHECK (week_number >= 1 AND week_number <= 24))",
            "CREATE TABLE user_workouts (id INTEGER PRIMARY KEY, user_program_id INTEGER NOT NULL, week_number INTEGER NOT NULL, day_number INTEGER NOT NULL, status TEXT, completed_at TEXT)",
            "CREATE TABLE user_workout_sets (id INTEGER PRIMARY KEY, actual_weight NUMERIC, actual_reps INTEGER, is_completed BOOLEAN)",
            "CREATE TABLE user_profiles (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)",
            "INSERT INTO program_templates VALUES (1, 16)",
            "INSERT INTO program_template_exercise_weeks VALUES (1, 1)",
            "INSERT INTO user_workouts VALUES (1, 1, 1, 1, 'completed', '2026-08-01 12:00:00')",
            "INSERT INTO user_workout_sets VALUES (1, 42.25, 8, 1)",
            "INSERT INTO user_profiles VALUES (1, 7)",
        ):
            connection.exec_driver_sql(statement)
        connection.commit()
        config.attributes["connection"] = connection
        command.stamp(config, "0133_profile_height_numeric")
        connection.commit()
        command.upgrade(config, starting_revision)
        connection.commit()
        activity_first = starting_revision == "0134_workout_completed_at_utc"
        if activity_first:
            connection.exec_driver_sql(
                "UPDATE user_workouts SET completed_at_utc = '2026-08-01 09:00:00'"
            )
        else:
            connection.exec_driver_sql(
                "UPDATE user_workouts SET source_cycle_week=1, cycle_iteration=2, plan_revision_number=3"
            )
            connection.exec_driver_sql("UPDATE user_workout_sets SET plan_version=3")
        connection.commit()
        command.upgrade(config, "head")
        connection.commit()
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").all() == [
            ("0138_equipment_profiles",)
        ]
        assert connection.exec_driver_sql(
            "SELECT user_id, equipment_profiles, active_equipment_profile_id, equipment_profiles_revision FROM user_profiles"
        ).one() == (7, None, None, None)
        assert connection.exec_driver_sql(
            "SELECT status, completed_at, completed_at_utc, source_cycle_week, cycle_iteration, plan_revision_number FROM user_workouts"
        ).one() == (
            "completed",
            "2026-08-01 12:00:00",
            "2026-08-01 09:00:00" if activity_first else None,
            None if activity_first else 1,
            None if activity_first else 2,
            None if activity_first else 3,
        )
        assert connection.exec_driver_sql(
            "SELECT actual_weight, actual_reps, is_completed, plan_version FROM user_workout_sets"
        ).one() == (42.25, 8, 1, None if activity_first else 3)
    engine.dispose()
