from pathlib import Path

import pytest
from scripts.configure_production_ai_coach import (
    PRODUCTION_AI_COACH_FLAGS,
    configure_production_ai_coach,
)


def test_enables_ai_coach_without_changing_groq_key_or_unrelated_values(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SECRET_KEY=keep-this-secret\n"
        "GROQ_API_KEY=gsk_keep-this-key\n"
        "AI_COACH_ENABLED=false\n"
        "AI_COACH_PROVIDER=disabled\n"
        "AI_COACH_INTERNAL_USER_IDS=123,456\n"
        "POSTGRES_PASSWORD=also-keep-this\n",
        encoding="utf-8",
    )

    configure_production_ai_coach(env_file)

    content = env_file.read_text(encoding="utf-8")
    assert "GROQ_API_KEY=gsk_keep-this-key\n" in content
    assert "SECRET_KEY=keep-this-secret\n" in content
    assert "POSTGRES_PASSWORD=also-keep-this\n" in content
    for key, value in PRODUCTION_AI_COACH_FLAGS.items():
        assert content.count(f"{key}={value}\n") == 1


def test_adds_missing_flags_once_removes_duplicates_and_is_idempotent(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=prod\n"
        "GROQ_API_KEY=gsk_keep-this-key\n"
        "AI_COACH_PROVIDER=disabled\n"
        "AI_COACH_PROVIDER=groq\n"
        "AI_COACH_ENABLED=false\n",
        encoding="utf-8",
    )

    configure_production_ai_coach(env_file)
    first = env_file.read_text(encoding="utf-8")
    configure_production_ai_coach(env_file)

    assert env_file.read_text(encoding="utf-8") == first
    for key, value in PRODUCTION_AI_COACH_FLAGS.items():
        assert first.count(f"{key}={value}\n") == 1


@pytest.mark.parametrize("value", ["", "change-me", "replace-me", "your_api_key"])
def test_refuses_missing_or_placeholder_groq_key_without_mutating_file(
    tmp_path: Path,
    value: str,
) -> None:
    env_file = tmp_path / ".env"
    original = f"APP_ENV=prod\nGROQ_API_KEY={value}\nAI_COACH_ENABLED=false\n"
    env_file.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        configure_production_ai_coach(env_file)

    assert env_file.read_text(encoding="utf-8") == original


def test_refuses_when_last_duplicate_groq_key_is_blank(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    original = "GROQ_API_KEY=gsk_valid\nGROQ_API_KEY=\n"
    env_file.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        configure_production_ai_coach(env_file)

    assert env_file.read_text(encoding="utf-8") == original


def test_production_deploy_enables_ai_coach_before_compose_validation() -> None:
    root = Path(__file__).resolve().parents[1]
    deploy = (root / "scripts" / "deploy_production.sh").read_text(encoding="utf-8")

    configure = "python3 scripts/configure_production_ai_coach.py .env"
    assert configure in deploy
    assert deploy.index(configure) < deploy.index("docker compose config --quiet")
