from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

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
