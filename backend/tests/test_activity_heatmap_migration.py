import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


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
