from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PRODUCTION_NUTRITION_LABEL_SCAN_FLAGS = {
    "NUTRITION_LABEL_SCAN_ENABLED": "true",
    "NUTRITION_LABEL_SCAN_KILL_SWITCH": "false",
}


def _replace_atomically(path: Path, content: str, mode: int) -> None:
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


def configure_production_nutrition_label_scan(
    env_path: Path,
    rollout_marker_path: Path,
) -> bool:
    if not env_path.is_file():
        raise FileNotFoundError(f"Environment file does not exist: {env_path}")

    marker_contract = {
        "task_id": "128I",
        "flags": PRODUCTION_NUTRITION_LABEL_SCAN_FLAGS,
    }
    if rollout_marker_path.exists():
        try:
            existing_marker = json.loads(rollout_marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Nutrition Label rollout marker is invalid") from error
        if existing_marker != marker_contract:
            raise ValueError("Nutrition Label rollout marker does not match Task 128I")
        return False

    original = env_path.read_text(encoding="utf-8")
    trailing_newline = original.endswith("\n")
    seen: set[str] = set()
    updated_lines: list[str] = []
    for line in original.splitlines():
        key, separator, _value = line.partition("=")
        if separator and key in PRODUCTION_NUTRITION_LABEL_SCAN_FLAGS:
            if key not in seen:
                updated_lines.append(f"{key}={PRODUCTION_NUTRITION_LABEL_SCAN_FLAGS[key]}")
                seen.add(key)
            continue
        updated_lines.append(line)

    for key, value in PRODUCTION_NUTRITION_LABEL_SCAN_FLAGS.items():
        if key not in seen:
            updated_lines.append(f"{key}={value}")

    env_mode = env_path.stat().st_mode
    _replace_atomically(
        env_path,
        "\n".join(updated_lines) + ("\n" if trailing_newline else ""),
        env_mode,
    )

    rollout_marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_contents = json.dumps(marker_contract, sort_keys=True) + "\n"
    _replace_atomically(rollout_marker_path, marker_contents, 0o600)
    return True


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: configure_production_nutrition_label_scan.py ENV_FILE ROLLOUT_MARKER"
        )
    changed = configure_production_nutrition_label_scan(Path(sys.argv[1]), Path(sys.argv[2]))
    result = "enabled" if changed else "already configured; host values preserved"
    print(f"Production Nutrition Label scanning: {result}")


if __name__ == "__main__":
    main()
