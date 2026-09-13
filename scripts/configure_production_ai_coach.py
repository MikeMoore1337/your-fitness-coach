from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PRODUCTION_AI_COACH_FLAGS = {
    "AI_COACH_ENABLED": "true",
    "AI_COACH_KILL_SWITCH": "false",
    # Kept compatible with older bundles; the current bundle does not use this as an access gate.
    "AI_COACH_UI_ENABLED": "true",
    "AI_COACH_INTERNAL_USER_IDS": "",
    "AI_COACH_PROVIDER": "groq",
    "AI_COACH_ENDPOINT": "https://api.groq.com/openai/v1/chat/completions",
    "AI_COACH_MODEL": "openai/gpt-oss-120b",
    "AI_COACH_COST_POLICY": "free_only",
    "AI_COACH_COST_CLASS": "free",
    "AI_COACH_DATA_POLICY": "verified_generic_only",
    "AI_COACH_PERSONAL_ENABLED": "true",
    "AI_COACH_PERSONAL_DATA_POLICY": "verified_personal_user",
    "AI_COACH_STRUCTURED_OUTPUT": "true",
    "AI_COACH_POLICY_REVISION": "ai-coach-production-v1",
}

_PLACEHOLDER_SECRETS = {
    "",
    "change-me",
    "changeme",
    "replace-me",
    "replace_me",
    "your-secret-here",
    "your_api_key",
    "your-api-key",
}


def _last_env_value(lines: list[str], key: str) -> str:
    values = [
        value.strip()
        for line in lines
        for line_key, separator, value in [line.partition("=")]
        if separator and line_key == key
    ]
    return values[-1] if values else ""


def _is_placeholder_secret(value: str) -> bool:
    normalized = value.strip().strip('"').strip("'").strip().lower()
    return normalized in _PLACEHOLDER_SECRETS or normalized.startswith("your_")


def _require_groq_api_key(lines: list[str]) -> None:
    value = _last_env_value(lines, "GROQ_API_KEY")
    if _is_placeholder_secret(value):
        raise ValueError(
            "Production AI Coach requires a non-placeholder GROQ_API_KEY in the host .env"
        )


def configure_production_ai_coach(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Environment file does not exist: {path}")

    original = path.read_text(encoding="utf-8")
    trailing_newline = original.endswith("\n")
    lines = original.splitlines()
    _require_groq_api_key(lines)

    seen: set[str] = set()
    updated_lines: list[str] = []
    for line in lines:
        key, separator, _value = line.partition("=")
        if separator and key in PRODUCTION_AI_COACH_FLAGS:
            if key not in seen:
                updated_lines.append(f"{key}={PRODUCTION_AI_COACH_FLAGS[key]}")
                seen.add(key)
            continue
        updated_lines.append(line)

    for key, value in PRODUCTION_AI_COACH_FLAGS.items():
        if key not in seen:
            updated_lines.append(f"{key}={value}")

    content = "\n".join(updated_lines) + ("\n" if trailing_newline else "")
    mode = path.stat().st_mode
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_name = temporary.name
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: configure_production_ai_coach.py ENV_FILE")
    configure_production_ai_coach(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
