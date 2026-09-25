"""Deprecated legacy media-manifest builder.

The old builder targeted retired schema 2 and could describe generated media.
It must not write the active schema-3 manifest. Use the authoritative catalogue
validator for the checked-in Gym visual manifest instead.
"""

from __future__ import annotations

import sys

DEPRECATION_MESSAGE = (
    "Deprecated: this legacy builder targets retired schema 2 and is fail-closed. "
    "It must not write manifest.json. The authoritative schema-3 manifest is "
    "backend/assets/exercise-guides/manifest.json; validate it with "
    "scripts/validate_exercise_catalog.py."
)


def main() -> int:
    print(DEPRECATION_MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
