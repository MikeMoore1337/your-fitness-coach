#!/usr/bin/env python3
"""Forced-command entrypoint installed outside the application checkout."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


def _run() -> int:
    wrapper_dir = Path(__file__).resolve().parent
    candidates = (wrapper_dir, wrapper_dir.parents[1] / "scripts")
    for candidate in candidates:
        if (candidate / "allure_report_origin.py").is_file():
            sys.path.insert(0, str(candidate))
            return int(import_module("allure_report_origin").main())
    raise RuntimeError("allure origin module is not installed")


if __name__ == "__main__":
    raise SystemExit(_run())
