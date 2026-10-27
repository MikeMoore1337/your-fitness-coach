from pathlib import Path

import pytest
from scripts.configure_production_nutrition_label_vision import (
    PRODUCTION_NUTRITION_VISION_FLAGS,
    configure_production_nutrition_label_vision,
)


def _write_env(path: Path, groq_key: str = "gsk_keep-this-key") -> str:
    content = (
        "APP_ENV=prod\n"
        "SECRET_KEY=keep-this-secret\n"
        f"GROQ_API_KEY={groq_key}\n"
        "NUTRITION_LABEL_VISION_ENABLED=false\n"
        "NUTRITION_LABEL_VISION_PROVIDER=disabled\n"
        "DATABASE_URL=keep-this-value\n"
    )
    path.write_text(content, encoding="utf-8")
    return content


def test_requires_explicit_zdr_and_preview_acceptance_without_mutating_file(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    original = _write_env(env_file)

    with pytest.raises(ValueError, match="ZDR"):
        configure_production_nutrition_label_vision(
            env_file,
            proxy_url="socks5://host.docker.internal:1081",
            zdr_verified=False,
            allow_preview=True,
        )
    assert env_file.read_text(encoding="utf-8") == original

    with pytest.raises(ValueError, match="Preview"):
        configure_production_nutrition_label_vision(
            env_file,
            proxy_url="socks5://host.docker.internal:1081",
            zdr_verified=True,
            allow_preview=False,
        )
    assert env_file.read_text(encoding="utf-8") == original


def test_enables_vision_idempotently_and_preserves_secrets(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file)

    configure_production_nutrition_label_vision(
        env_file,
        proxy_url="socks5://host.docker.internal:1081",
        zdr_verified=True,
        allow_preview=True,
    )
    first = env_file.read_text(encoding="utf-8")
    configure_production_nutrition_label_vision(
        env_file,
        proxy_url="socks5://host.docker.internal:1081",
        zdr_verified=True,
        allow_preview=True,
    )

    assert env_file.read_text(encoding="utf-8") == first
    assert "GROQ_API_KEY=gsk_keep-this-key\n" in first
    assert "SECRET_KEY=keep-this-secret\n" in first
    assert "DATABASE_URL=keep-this-value\n" in first
    assert "NUTRITION_LABEL_VISION_PROXY_URL=socks5://host.docker.internal:1081\n" in first
    for key, value in PRODUCTION_NUTRITION_VISION_FLAGS.items():
        assert first.count(f"{key}={value}\n") == 1
    assert (
        int(PRODUCTION_NUTRITION_VISION_FLAGS["NUTRITION_LABEL_VISION_MAX_OUTPUT_TOKENS"]) <= 1000
    )


@pytest.mark.parametrize("value", ["", "change-me", "replace-me", "your_api_key"])
def test_refuses_missing_or_placeholder_groq_key(tmp_path: Path, value: str) -> None:
    env_file = tmp_path / ".env"
    original = _write_env(env_file, value)

    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        configure_production_nutrition_label_vision(
            env_file,
            proxy_url="socks5://host.docker.internal:1081",
            zdr_verified=True,
            allow_preview=True,
        )

    assert env_file.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    "proxy_url",
    [
        "",
        "ftp://proxy.example:1080",
        "socks5://user:secret@proxy.example:1080",
        "https://proxy.example/path",
        "https://proxy.example?token=secret",
    ],
)
def test_refuses_unsafe_proxy_url(tmp_path: Path, proxy_url: str) -> None:
    env_file = tmp_path / ".env"
    original = _write_env(env_file)

    with pytest.raises(ValueError, match="proxy"):
        configure_production_nutrition_label_vision(
            env_file,
            proxy_url=proxy_url,
            zdr_verified=True,
            allow_preview=True,
        )

    assert env_file.read_text(encoding="utf-8") == original
