import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from alembic import command


def test_snapshot_migration_preserves_targets_and_refuses_lossy_downgrade(
    tmp_path: Path, monkeypatch
) -> None:
    from fitminiapp_api.core import config as app_config

    root = Path(__file__).resolve().parents[2]
    database_url = f"sqlite:///{(tmp_path / 'nutrition-snapshots.db').as_posix()}"
    config = Config(str(root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(root / "backend" / "alembic"))
    monkeypatch.setattr(app_config.settings, "database_url", database_url)
    command.upgrade(config, "0148_import_self_assignment")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (telegram_user_id, is_coach, is_admin, is_active) "
                "VALUES (952100, 0, 0, 1)"
            )
        )
        user_id = connection.execute(
            text("SELECT id FROM users WHERE telegram_user_id = 952100")
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO nutrition_targets "
                "(user_id, effective_from, source, calories, protein_g, fat_g, carbs_g, saved_at) "
                "VALUES (:user_id, '2026-01-01', 'manual', 2000, 150, 70, 180, '2026-01-01')"
            ),
            {"user_id": user_id},
        )
        target_id = connection.execute(text("SELECT id FROM nutrition_targets")).scalar_one()
    engine.dispose()

    command.upgrade(config, "0149_nutrition_target_snapshots")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        assert (
            connection.execute(text("SELECT calories FROM nutrition_targets")).scalar_one() == 2000
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM nutrition_target_day_snapshots")
            ).scalar_one()
            == 0
        )
        connection.execute(
            text(
                "INSERT INTO nutrition_target_day_snapshots (user_id, diary_date, target_id) "
                "VALUES (:user_id, '2026-01-01', :target_id)"
            ),
            {"user_id": user_id, "target_id": target_id},
        )
    engine.dispose()
    with pytest.raises(
        RuntimeError, match="Cannot discard completed-day nutrition target snapshots"
    ):
        command.downgrade(config, "0148_import_self_assignment")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        assert (
            connection.execute(
                text("SELECT target_id FROM nutrition_target_day_snapshots")
            ).scalar_one()
            == target_id
        )
        connection.execute(text("DELETE FROM nutrition_target_day_snapshots"))
    engine.dispose()
    command.downgrade(config, "0148_import_self_assignment")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert not inspect(connection).has_table("nutrition_target_day_snapshots")
        assert (
            connection.execute(text("SELECT calories FROM nutrition_targets")).scalar_one() == 2000
        )
    engine.dispose()


def test_date_override_migration_preserves_data_and_blocks_lossy_downgrade(tmp_path: Path) -> None:
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0150_nutrition_date_overrides.py"
    spec = importlib.util.spec_from_file_location("nutrition_date_override_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'date-overrides.db').as_posix()}", poolclass=NullPool
    )
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text("CREATE TABLE nutrition_targets (id INTEGER PRIMARY KEY, calories INTEGER)")
        )
        connection.execute(text("INSERT INTO users VALUES (1)"))
        connection.execute(text("INSERT INTO nutrition_targets VALUES (1, 2000)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert connection.execute(
            text("SELECT calories, target_scope FROM nutrition_targets")
        ).one() == (2000, None)
        connection.execute(text("UPDATE nutrition_targets SET target_scope = 'date' WHERE id = 1"))
        connection.execute(
            text(
                "INSERT INTO nutrition_target_date_overrides "
                "(user_id, target_id, target_date, idempotency_key, request_hash) "
                "VALUES (1, 1, '2026-01-01', 'migration-test', 'hash')"
            )
        )
        with pytest.raises(RuntimeError, match="Cannot discard nutrition date overrides"):
            migration.downgrade()
        assert (
            connection.execute(
                text("SELECT count(*) FROM nutrition_target_date_overrides")
            ).scalar_one()
            == 1
        )
        connection.execute(text("DELETE FROM nutrition_target_date_overrides"))
        with pytest.raises(RuntimeError, match="Cannot discard scoped nutrition targets"):
            migration.downgrade()
        connection.execute(text("UPDATE nutrition_targets SET target_scope = NULL"))
        migration.downgrade()
        assert (
            connection.execute(text("SELECT calories FROM nutrition_targets")).scalar_one() == 2000
        )


def test_schedule_migration_blocks_loss_of_bindings_rules_and_targets(tmp_path: Path) -> None:
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0151_nutrition_schedule_rules.py"
    spec = importlib.util.spec_from_file_location("nutrition_schedule_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{(tmp_path / 'schedule.db').as_posix()}", poolclass=NullPool)
    with engine.begin() as connection:
        for statement in (
            "CREATE TABLE users (id INTEGER PRIMARY KEY)",
            "CREATE TABLE program_revisions (id INTEGER PRIMARY KEY)",
            "CREATE TABLE user_programs (id INTEGER PRIMARY KEY)",
            "CREATE TABLE nutrition_targets (id INTEGER PRIMARY KEY, calories INTEGER, target_scope TEXT)",
            "INSERT INTO users VALUES (1)",
            "INSERT INTO program_revisions VALUES (1)",
            "INSERT INTO nutrition_targets VALUES (1, 2000, NULL)",
        ):
            connection.execute(text(statement))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        connection.execute(
            text(
                "INSERT INTO nutrition_schedule_bindings (user_id, program_revision_id, effective_from, idempotency_key, request_hash) VALUES (1, 1, '2026-01-01', 'binding-key', 'hash')"
            )
        )
        with pytest.raises(RuntimeError, match="Cannot discard nutrition schedule bindings"):
            migration.downgrade()
        connection.execute(text("DELETE FROM nutrition_schedule_bindings"))
        connection.execute(
            text(
                "INSERT INTO nutrition_target_schedule_rules (user_id, target_id, scope, day_type, effective_from, idempotency_key, request_hash) VALUES (1, 1, 'recovery', 'recovery', '2026-01-01', 'rule-key', 'hash')"
            )
        )
        with pytest.raises(RuntimeError, match="Cannot discard nutrition schedule rules"):
            migration.downgrade()
        connection.execute(text("DELETE FROM nutrition_target_schedule_rules"))
        connection.execute(text("UPDATE nutrition_targets SET target_scope = 'schedule'"))
        with pytest.raises(RuntimeError, match="Cannot discard scheduled nutrition targets"):
            migration.downgrade()
        connection.execute(text("UPDATE nutrition_targets SET target_scope = NULL"))
        migration.downgrade()
        assert (
            connection.execute(text("SELECT calories FROM nutrition_targets")).scalar_one() == 2000
        )
