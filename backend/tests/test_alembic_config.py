import runpy
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
    assert revisions.get_heads() == ["0078_ai_coach_personal_consent"]
    assert relocated_marker.revision in {
        revision.revision
        for revision in revisions.iterate_revisions("head", legacy_support.revision)
    }
