import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue
from time import monotonic, sleep
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from fitminiapp_api.db.session import engine as app_engine


def _load_migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0140_workout_start_utc.py"
    spec = importlib.util.spec_from_file_location("workout_start_utc_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_workout_start_utc_migration_preserves_history_and_guards_downgrade(tmp_path):
    migration = _load_migration()
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


@pytest.mark.skipif(app_engine.dialect.name != "postgresql", reason="requires PostgreSQL locks")
def test_workout_start_utc_downgrade_waits_for_concurrent_start():
    schema = f"test_workout_start_{uuid4().hex}"
    with app_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(
            f'CREATE TABLE "{schema}".user_workouts '
            "(id INTEGER PRIMARY KEY, started_at_utc TIMESTAMP)"
        )
        connection.exec_driver_sql(f'INSERT INTO "{schema}".user_workouts (id) VALUES (1)')
    writer = app_engine.connect()
    transaction = writer.begin()
    pids = Queue()

    def downgrade():
        with app_engine.begin() as connection:
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            pids.put(connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one())
            with Operations.context(MigrationContext.configure(connection)):
                _load_migration().downgrade()

    try:
        writer.exec_driver_sql(
            f"UPDATE \"{schema}\".user_workouts SET started_at_utc='2026-10-30 09:00:00' WHERE id=1"
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(downgrade)
            try:
                pid = pids.get(timeout=10)
                deadline = monotonic() + 10
                wait_type = None
                with app_engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                ) as inspector:
                    while monotonic() < deadline:
                        wait_type = inspector.execute(
                            sa.text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"),
                            {"pid": pid},
                        ).scalar_one_or_none()
                        if wait_type == "Lock":
                            break
                        sleep(0.05)
                assert wait_type == "Lock"
                transaction.commit()
                with pytest.raises(RuntimeError, match="UTC workout start times exist"):
                    future.result(timeout=10)
            finally:
                if transaction.is_active:
                    transaction.rollback()
        with app_engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    f'SELECT started_at_utc FROM "{schema}".user_workouts WHERE id=1'
                ).scalar_one()
                is not None
            )
    finally:
        writer.close()
        with app_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
