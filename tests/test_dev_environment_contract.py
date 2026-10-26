"""Static contracts for the independently configured YFC DEV stack."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_dev_compose_is_separate_from_production() -> None:
    source = (ROOT / "compose.dev.yml").read_text(encoding="utf-8")
    assert "name: yfc-dev" in source
    assert "internal: true" in source
    assert "dev_postgres_data:" in source
    assert "APP_ENV: dev" in source
    assert "ENABLE_DEV_AUTH:" in source
    assert "BOT_POLLING_ENABLED:" in source
    assert "127.0.0.1:" in source
    assert "172.29." not in source
    assert "fitminiapp_bot_polling_lock" not in source
    assert "\n  bot:" not in source
    assert "\n  worker:" not in source

    # The backend uses a standard host-facing bridge for Windows Docker Desktop,
    # while the database and setup remain isolated from that bridge.
    config = yaml.safe_load(source)
    services = config["services"]
    assert services["db"]["networks"] == ["dev_internal"]
    assert services["setup"]["networks"] == ["dev_internal"]
    assert services["backend"]["networks"] == ["dev_internal", "dev_access"]
    assert config["networks"]["dev_internal"]["internal"] is True
    assert config["networks"]["dev_access"]["driver"] == "bridge"
    assert services["backend"]["ports"][0].startswith("127.0.0.1:")


def test_dev_secret_config_is_not_committed() -> None:
    template = (ROOT / ".env.dev.example").read_text(encoding="utf-8")
    assert "__GENERATE_DB_PASSWORD__" in template
    assert "__GENERATE_SECRET_KEY__" in template
    assert "__GENERATE_INTERNAL_TOKEN__" in template
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env.*" in ignore


def test_windows_powershell_script_is_utf8_with_bom() -> None:
    # Windows PowerShell 5.1 otherwise decodes UTF-8 Cyrillic text as ANSI.
    content = (ROOT / "scripts" / "dev.ps1").read_bytes()
    assert content.startswith(bytes((0xEF, 0xBB, 0xBF)))
