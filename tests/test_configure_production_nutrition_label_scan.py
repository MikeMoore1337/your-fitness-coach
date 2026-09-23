import json
from pathlib import Path

import pytest
from scripts.configure_production_nutrition_label_scan import (
    PRODUCTION_NUTRITION_LABEL_SCAN_FLAGS,
    configure_production_nutrition_label_scan,
)


def test_enables_scan_once_without_changing_unrelated_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    marker = tmp_path / "operations" / "deployments" / "task-128I.json"
    env_file.write_text(
        "SECRET_KEY=keep-this-secret\n"
        "NUTRITION_LABEL_SCAN_ENABLED=false\n"
        "NUTRITION_LABEL_SCAN_KILL_SWITCH=true\n"
        "NUTRITION_LABEL_SCAN_ENABLED=false\n"
        "DATABASE_URL=keep-this-value\n",
        encoding="utf-8",
    )

    assert configure_production_nutrition_label_scan(env_file, marker) is True

    content = env_file.read_text(encoding="utf-8")
    assert content == (
        "SECRET_KEY=keep-this-secret\n"
        "NUTRITION_LABEL_SCAN_ENABLED=true\n"
        "NUTRITION_LABEL_SCAN_KILL_SWITCH=false\n"
        "DATABASE_URL=keep-this-value\n"
    )
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "task_id": "128I",
        "flags": PRODUCTION_NUTRITION_LABEL_SCAN_FLAGS,
    }

    updated_by_operator = content.replace(
        "NUTRITION_LABEL_SCAN_ENABLED=true\nNUTRITION_LABEL_SCAN_KILL_SWITCH=false\n",
        "NUTRITION_LABEL_SCAN_ENABLED=false\nNUTRITION_LABEL_SCAN_KILL_SWITCH=true\n",
    )
    env_file.write_text(updated_by_operator, encoding="utf-8")
    assert configure_production_nutrition_label_scan(env_file, marker) is False
    assert env_file.read_text(encoding="utf-8") == updated_by_operator


def test_refuses_missing_environment_file_without_creating_marker(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    marker = tmp_path / "rollout.json"

    with pytest.raises(FileNotFoundError):
        configure_production_nutrition_label_scan(env_file, marker)

    assert not marker.exists()


def test_refuses_unrecognized_existing_marker_without_mutating_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    marker = tmp_path / "rollout.json"
    original = "NUTRITION_LABEL_SCAN_ENABLED=false\n"
    env_file.write_text(original, encoding="utf-8")
    marker.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match Task 128I"):
        configure_production_nutrition_label_scan(env_file, marker)

    assert env_file.read_text(encoding="utf-8") == original


def test_production_deploy_applies_rollout_configuration_before_compose() -> None:
    root = Path(__file__).resolve().parents[1]
    deploy = (root / "scripts" / "deploy_production.sh").read_text(encoding="utf-8")

    configure = (
        "python3 scripts/configure_production_nutrition_label_scan.py .env "
        '"$NUTRITION_LABEL_SCAN_ROLLOUT_MARKER"'
    )
    assert configure in deploy
    assert deploy.index(configure) < deploy.index("docker compose config --quiet")
