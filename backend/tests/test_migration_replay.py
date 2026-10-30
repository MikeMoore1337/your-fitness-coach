from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_sqlite_numeric_precision_migration_fails_closed_on_excess_fractional_data(
    tmp_path: Path, monkeypatch
) -> None:
    from fitminiapp_api.core import config as app_config

    root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "numeric-precision-safety.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    alembic_config = Config(str(root / "backend" / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(root / "backend" / "alembic"))
    monkeypatch.setattr(app_config.settings, "database_url", database_url)

    previous_revision = "0132_rest_interval_unique_swap"
    command.upgrade(alembic_config, previous_revision)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO users (id, is_coach, is_admin, is_active) VALUES (1, 0, 0, 1)")
            )
            connection.execute(
                text("INSERT INTO user_profiles (id, user_id, height_cm) VALUES (1, 1, 178.251)")
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="Unsafe numeric precision migration"):
        command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == (previous_revision)
    finally:
        engine.dispose()


def test_sqlite_migration_history_replays_to_head(tmp_path: Path, monkeypatch) -> None:
    from fitminiapp_api.core import config as app_config

    root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "migration-replay.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    alembic_config = Config(str(root / "backend" / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(root / "backend" / "alembic"))
    monkeypatch.setattr(app_config.settings, "database_url", database_url)
    script = ScriptDirectory.from_config(alembic_config)
    expected_revision = script.get_current_head()
    previous_revision = script.get_revision(expected_revision).down_revision
    previous_revisions = (
        {previous_revision} if isinstance(previous_revision, str) else set(previous_revision or ())
    )
    assert previous_revisions

    command.upgrade(alembic_config, "head")

    def current_revisions() -> set[str]:
        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                return set(
                    connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
                )
        finally:
            engine.dispose()

    assert current_revisions() == {expected_revision}

    for previous in sorted(previous_revisions):
        command.downgrade(alembic_config, previous)
        assert current_revisions() == previous_revisions

        command.upgrade(alembic_config, "head")
        assert current_revisions() == {expected_revision}


def test_sqlite_stage7_upgrade_from_0092_preserves_expand_contract(
    tmp_path: Path, monkeypatch
) -> None:
    from fitminiapp_api.core import config as app_config

    root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "stage7-upgrade.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    alembic_config = Config(str(root / "backend" / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(root / "backend" / "alembic"))
    monkeypatch.setattr(app_config.settings, "database_url", database_url)

    command.upgrade(alembic_config, "0092_coach_crm_core")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO program_templates "
                    "(slug, title, goal, level, split_type, default_duration_weeks, is_public) "
                    "VALUES (:slug, :title, 'strength', 'beginner', 'full_body', 1, :is_public)"
                ),
                [
                    {
                        "slug": "stronglifts-5x5",
                        "title": "StrongLifts",
                        "is_public": True,
                    },
                    {
                        "slug": "legacy-yfc-template",
                        "title": "Legacy YFC template",
                        "is_public": True,
                    },
                    {
                        "slug": "private-custom-template",
                        "title": "Private custom template",
                        "is_public": False,
                    },
                ],
            )
    finally:
        engine.dispose()

    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        provenance_columns = {
            column["name"]: column for column in inspector.get_columns("program_templates")
        }
        assert provenance_columns["provenance_type"]["nullable"] is True
        assert provenance_columns["provenance"]["nullable"] is True
        assert provenance_columns["program_metadata"]["nullable"] is True

        for table, columns in {
            "program_template_exercises": {"group_id", "group_kind", "group_order", "prescription"},
            "program_template_exercise_weeks": {"prescription"},
            "user_workout_exercises": {
                "source_template_exercise_id",
                "source_weekly_prescription_id",
                "group_id",
                "group_kind",
                "group_order",
                "prescription",
            },
            "user_workout_sets": {
                "planned_role",
                "planned_group_id",
                "planned_group_kind",
                "planned_position",
                "planned_round",
            },
        }.items():
            actual = {column["name"] for column in inspector.get_columns(table)}
            assert columns <= actual
            added = actual & columns
            assert all(
                column["nullable"]
                for column in inspector.get_columns(table)
                if column["name"] in added
            )

        program_columns = {
            column["name"]: column for column in inspector.get_columns("user_programs")
        }
        assert program_columns["restarted_from_program_id"]["nullable"] is True
        lineage_foreign_keys = {
            column
            for foreign_key in inspector.get_foreign_keys("user_programs")
            for column in foreign_key["constrained_columns"]
        }
        assert "restarted_from_program_id" not in lineage_foreign_keys
        lineage_indexes = {
            column
            for index in inspector.get_indexes("user_programs")
            for column in index["column_names"]
        }
        assert "restarted_from_program_id" not in lineage_indexes

        source_foreign_keys = {
            column
            for foreign_key in inspector.get_foreign_keys("user_workout_exercises")
            for column in foreign_key["constrained_columns"]
        }
        assert "source_template_exercise_id" not in source_foreign_keys
        assert "source_weekly_prescription_id" not in source_foreign_keys
        source_indexes = {
            column
            for index in inspector.get_indexes("user_workout_exercises")
            for column in index["column_names"]
        }
        assert "source_template_exercise_id" not in source_indexes
        assert "source_weekly_prescription_id" not in source_indexes

        with engine.connect() as connection:
            provenance = dict(
                connection.execute(
                    text("SELECT slug, provenance_type FROM program_templates")
                ).all()
            )
            revision_check = connection.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'program_revisions'"
                )
            ).scalar_one()
        assert provenance == {
            "stronglifts-5x5": "SOURCE_ADAPTATION",
            "legacy-yfc-template": "YFC_GENERIC",
            "private-custom-template": "CUSTOM",
        }
        assert "exercise_replaced" not in revision_check
        assert "prescription_updated" not in revision_check
    finally:
        engine.dispose()
