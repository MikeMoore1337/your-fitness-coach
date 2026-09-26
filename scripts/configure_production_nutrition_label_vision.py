from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

PRODUCTION_NUTRITION_VISION_FLAGS = {
    "NUTRITION_LABEL_VISION_ENABLED": "true",
    "NUTRITION_LABEL_VISION_KILL_SWITCH": "false",
    "NUTRITION_LABEL_VISION_PROVIDER": "groq",
    "NUTRITION_LABEL_VISION_ENDPOINT": "https://api.groq.com/openai/v1/chat/completions",
    "NUTRITION_LABEL_VISION_MODEL": "qwen/qwen3.8-27b",
    "NUTRITION_LABEL_VISION_ALLOW_PREVIEW": "true",
    "NUTRITION_LABEL_VISION_DATA_POLICY": "zdr_verified",
    "NUTRITION_LABEL_VISION_TIMEOUT_SECONDS": "8",
    "NUTRITION_LABEL_VISION_MAX_OUTPUT_TOKENS": "1536",
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


def _validate_proxy_url(value: str) -> str:
    normalized = value.strip()
    try:
        parsed = urlparse(normalized)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Vision proxy URL is invalid") from exc
    if (
        parsed.scheme not in {"http", "https", "socks5", "socks5h"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("Vision proxy URL must be credential-free HTTP(S) or SOCKS5")
    return normalized


def configure_production_nutrition_label_vision(
    env_path: Path,
    *,
    proxy_url: str,
    zdr_verified: bool,
    allow_preview: bool,
) -> None:
    if not env_path.is_file():
        raise FileNotFoundError(f"Environment file does not exist: {env_path}")
    if not zdr_verified:
        raise ValueError("ZDR must be explicitly verified before Vision activation")
    if not allow_preview:
        raise ValueError("Preview-model risk must be explicitly accepted before Vision activation")

    proxy = _validate_proxy_url(proxy_url)
    original = env_path.read_text(encoding="utf-8")
    trailing_newline = original.endswith("\n")
    lines = original.splitlines()

    if _is_placeholder_secret(_last_env_value(lines, "GROQ_API_KEY")):
        raise ValueError("Production Nutrition Vision requires a non-placeholder GROQ_API_KEY")

    values = {
        **PRODUCTION_NUTRITION_VISION_FLAGS,
        "NUTRITION_LABEL_VISION_PROXY_URL": proxy,
    }
    seen: set[str] = set()
    updated_lines: list[str] = []
    for line in lines:
        key, separator, _value = line.partition("=")
        if separator and key in values:
            if key not in seen:
                updated_lines.append(f"{key}={values[key]}")
                seen.add(key)
            continue
        updated_lines.append(line)

    for key, value in values.items():
        if key not in seen:
            updated_lines.append(f"{key}={value}")

    stat = env_path.stat()
    content = "\n".join(updated_lines) + ("\n" if trailing_newline else "")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=env_path.parent,
            prefix=f".{env_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_name = temporary.name
        os.chmod(temporary_name, stat.st_mode)
        try:
            os.chown(temporary_name, stat.st_uid, stat.st_gid)
        except PermissionError:
            pass
        os.replace(temporary_name, env_path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("env_file", type=Path)
    parser.add_argument("--proxy-url", required=True)
    parser.add_argument("--confirm-zdr", action="store_true")
    parser.add_argument("--allow-preview", action="store_true")
    args = parser.parse_args()

    configure_production_nutrition_label_vision(
        args.env_file,
        proxy_url=args.proxy_url,
        zdr_verified=args.confirm_zdr,
        allow_preview=args.allow_preview,
    )
    print("Production Nutrition Vision configuration enabled")


if __name__ == "__main__":
    main()
