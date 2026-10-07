import runpy
import subprocess
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_env_accepts_percent_encoded_database_url(monkeypatch) -> None:
    from alembic import context
    from fitminiapp_api.core import config as app_config

    root = Path(__file__).resolve().parents[2]
    captured: dict[str, str] = {}
    fake_config = SimpleNamespace(
        config_file_name=None,
        config_ini_section="alembic",
        set_main_option=lambda key, value: captured.setdefault(key, value),
        get_main_option=lambda key: captured[key],
    )
    monkeypatch.setattr(context, "config", fake_config, raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(context, "configure", lambda **_kwargs: None)
    monkeypatch.setattr(context, "begin_transaction", nullcontext)
    monkeypatch.setattr(context, "run_migrations", lambda: None)
    monkeypatch.setattr(
        app_config.settings,
        "database_url",
        "postgresql+psycopg://app:encoded%21password@db/app",
    )

    runpy.run_path(str(root / "backend" / "alembic" / "env.py"))

    assert captured["sqlalchemy.url"] == ("postgresql+psycopg://app:encoded%%21password@db/app")


def test_legacy_support_revision_remains_in_the_linear_upgrade_path() -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(root / "backend" / "alembic"))
    revisions = ScriptDirectory.from_config(config)

    legacy_support = revisions.get_revision("0033_bot_support_cases")
    auth_families = revisions.get_revision("0033_auth_session_families")
    relocated_marker = revisions.get_revision("0051_bot_support_cases")

    assert legacy_support is not None
    assert auth_families is not None
    assert relocated_marker is not None
    assert auth_families.down_revision == legacy_support.revision
    assert revisions.get_heads() == ["0127_check_in_templates"]
    assert relocated_marker.revision in {
        revision.revision
        for revision in revisions.iterate_revisions("head", legacy_support.revision)
    }


def test_lifecycle_milestone_migration_passes_the_online_rollout_gate(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[2]
    active_revision = subprocess.run(
        [
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            "backend/alembic/versions/0111_coach_task_source_kind_constraint.py",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    checker = runpy.run_path(str(root / "scripts" / "check_online_migrations.py"))

    monkeypatch.chdir(root)
    migration_path = Path("backend/alembic/versions/0112_lifecycle_milestones.py")
    checker["validate_added_migration"](migration_path)
    checker["validate_added_migration"](
        Path("backend/alembic/versions/0113_lifecycle_workout_instances.py")
    )
    checker["validate_added_migration"](
        Path("backend/alembic/versions/0114_lifecycle_missed_workout_constraint.py")
    )
    checker["check_online_migrations"](active_revision, target_revision)


def test_check_in_templates_migration_passes_the_online_rollout_gate() -> None:
    root = Path(__file__).resolve().parents[2]
    checker = runpy.run_path(str(root / "scripts" / "check_online_migrations.py"))

    checker["validate_added_migration"](
        root / "backend" / "alembic" / "versions" / "0127_configurable_check_in_templates.py"
    )
