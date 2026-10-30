import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_workout_start_utc_migration_preserves_history_and_guards_downgrade(tmp_path):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0140_workout_start_utc.py"
    spec = importlib.util.spec_from_file_location("workout_start_utc_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine(f"sqlite:///{(tmp_path / 'workout-start.db').as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE user_workouts (id INTEGER PRIMARY KEY, started_at TEXT, status TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO user_workouts VALUES (1, '2026-10-30 12:00:00', 'completed')"
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.exec_driver_sql(
                "SELECT started_at, started_at_utc, status FROM user_workouts WHERE id=1"
            ).one() == ("2026-10-30 12:00:00", None, "completed")
            connection.exec_driver_sql(
                "UPDATE user_workouts SET started_at_utc='2026-10-30 09:00:00' WHERE id=1"
            )
            with pytest.raises(RuntimeError, match="UTC workout start times exist"):
                migration.downgrade()
            connection.exec_driver_sql("UPDATE user_workouts SET started_at_utc=NULL WHERE id=1")
            migration.downgrade()
        assert connection.exec_driver_sql(
            "SELECT started_at, status FROM user_workouts WHERE id=1"
        ).one() == ("2026-10-30 12:00:00", "completed")
    engine.dispose()
