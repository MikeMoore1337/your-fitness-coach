#!/usr/bin/env python3
"""Create separate YFC local/dev secrets without reading production .env."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = {
    "__GENERATE_DB_PASSWORD__": 24,
    "__GENERATE_SECRET_KEY__": 32,
    "__GENERATE_INTERNAL_TOKEN__": 32,
}


def bootstrap_dev_env(template: Path, destination: Path) -> None:
    content = template.read_text(encoding="utf-8")
    for placeholder, size in TOKENS.items():
        if content.count(placeholder) != 1:
            raise ValueError(f"DEV template must contain exactly one {placeholder}")
        content = content.replace(placeholder, secrets.token_urlsafe(size))
    # Exclusive create: existing configuration and secrets are never overwritten.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def main() -> None:
    destination = ROOT / ".env.dev"
    bootstrap_dev_env(ROOT / ".env.dev.example", destination)
    print("Created .env.dev with dedicated DEV secrets. No production files were read.")


if __name__ == "__main__":
    main()
