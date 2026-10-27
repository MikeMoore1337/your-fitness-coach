"""Build deterministic license/NOTICE evidence for the stdlib-only discovery image."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def _parse_apk_database(path: Path) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    for block in path.read_text(encoding="utf-8").split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if len(line) >= 2 and line[1] == ":" and line[0] in {"P", "V", "A", "L"}:
                fields[line[0]] = line[2:]
        if fields.get("P"):
            packages.append(
                {
                    "name": fields["P"],
                    "version": fields.get("V", ""),
                    "architecture": fields.get("A", ""),
                    "license": fields.get("L", "unknown"),
                }
            )
    return sorted(packages, key=lambda item: (item["name"], item["version"]))


def build_bundle(*, output: Path, manifest_path: Path, apk_database_path: Path) -> None:
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("pythonPackages") != []:
        raise ValueError("discovery image must remain third-party Python dependency free")
    if not apk_database_path.is_file():
        raise ValueError("APK database is missing")
    python_license = Path("/usr/local/lib/python3.13/LICENSE.txt")
    if not python_license.is_file():
        raise ValueError("Python PSF license is missing")
    output.mkdir(parents=True, exist_ok=True)
    python_target = output / "python" / "Python"
    python_target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(python_license, python_target / "LICENSE.txt")
    apk_packages = _parse_apk_database(apk_database_path)
    shutil.copyfile(apk_database_path, output / "alpine-installed-packages.txt")
    bundle = {
        "schemaVersion": "task129-discovery-license-bundle-v1",
        "base": manifest["base"],
        "pythonRuntime": manifest["pythonRuntime"],
        "pythonPackages": [],
        "alpinePackages": apk_packages,
        "files": {
            "notice": "NOTICE",
            "pythonRuntimeLicense": "python/Python/LICENSE.txt",
            "apkDatabase": "alpine-installed-packages.txt",
        },
    }
    notice = [
        "Task 129 bounded Hermes discovery runner license/NOTICE bundle",
        "",
        f"Base image: {manifest['base']['image']}@{manifest['base']['digest']}",
        "Python standard library/runtime: PSF-2.0 (python/Python/LICENSE.txt)",
        "",
        "No third-party Python runtime dependencies are installed.",
        "Alpine runtime package/license inventory: alpine-installed-packages.txt",
        "The APK license field is retained verbatim in package-license-inventory.json.",
    ]
    (output / "NOTICE").write_text("\n".join(notice) + "\n", encoding="utf-8", newline="\n")
    (output / "package-license-inventory.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--apk-database", type=Path, required=True)
    args = parser.parse_args()
    build_bundle(
        output=args.output,
        manifest_path=args.manifest,
        apk_database_path=args.apk_database,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
