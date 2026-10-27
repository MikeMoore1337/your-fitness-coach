"""Запуск mypy для пакета fitminiapp_api из каталога backend."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    backend = root / "backend"
    cfg = root / "pyproject.toml"
    cache_dir = root / ".artifacts" / "runtime" / "cache" / "mypy"
    env = {
        **os.environ,
        "MYPY_CACHE_DIR": str(cache_dir),
        "PYTHONPATH": str(backend),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        "fitminiapp_api",
        "--config-file",
        str(cfg),
        "--cache-dir",
        str(cache_dir),
    ]
    return subprocess.call(cmd, cwd=backend, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
