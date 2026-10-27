"""Create a deterministic third-party license/NOTICE bundle during image build."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from importlib import metadata
from pathlib import Path
from typing import Any

LOCK_LINE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s;#]+)$")
LOCK_HASH = re.compile(r"^--hash=sha256:[0-9a-f]{64}$")


def _normalise(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _parse_lock(path: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    previous_name: str | None = None
    previous_has_hash = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            line = line[:-1].rstrip()
        if line.startswith("--hash="):
            if previous_name is None or LOCK_HASH.fullmatch(line) is None:
                raise ValueError(f"lock contains an invalid hash line: {raw_line!r}")
            previous_has_hash = True
            continue
        if previous_name is not None and not previous_has_hash:
            raise ValueError(f"lock dependency has no hash: {previous_name}")
        match = LOCK_LINE.fullmatch(line)
        if match is None:
            raise ValueError(f"lock contains an unpinned or unsupported line: {raw_line!r}")
        name = _normalise(match.group("name"))
        if name in packages:
            raise ValueError(f"lock contains duplicate package: {name}")
        packages[name] = match.group("version")
        previous_name = name
        previous_has_hash = False
    if previous_name is not None and not previous_has_hash:
        raise ValueError(f"lock dependency has no hash: {previous_name}")
    return packages


def _safe_member(member: str) -> Path | None:
    path = Path(member)
    if path.is_absolute() or ".." in path.parts:
        return None
    return path


def _looks_like_license(path: Path) -> bool:
    name = path.name.casefold()
    return (
        "license" in name
        or "copying" in name
        or name.startswith("notice")
        or any(
            part.casefold() in {"license", "licenses", "notice", "notices"} for part in path.parts
        )
    )


def _copy_python_license_files(
    distribution: metadata.Distribution,
    target: Path,
    license_ids: list[str],
) -> int:
    package_dir = target / _normalise(distribution.metadata["Name"] or "unknown")
    package_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for member in sorted(distribution.files or [], key=str):
        relative = _safe_member(str(member))
        if relative is None or not _looks_like_license(relative):
            continue
        source = Path(distribution.locate_file(relative))
        if not source.is_file():
            continue
        destination = package_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied += 1
    declaration = package_dir / "PACKAGE-LICENSE-DECLARATION.txt"
    declaration.write_text(
        f"Package: {distribution.metadata['Name']}\n"
        f"Version: {distribution.version}\n"
        f"SPDX identifiers: {', '.join(license_ids)}\n",
        encoding="utf-8",
        newline="\n",
    )
    return copied + 1


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


def build_bundle(
    *,
    output: Path,
    lock_path: Path,
    source_manifest_path: Path,
    upstream_license_path: Path,
    apk_database_path: Path,
) -> None:
    inventory: dict[str, Any] = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    expected_packages = {
        _normalise(str(item["name"])): item for item in inventory["pythonPackages"]
    }
    locked_packages = _parse_lock(lock_path)
    if set(expected_packages) != set(locked_packages):
        raise ValueError("license inventory and dependency lock package sets differ")
    for name, item in expected_packages.items():
        if str(item["version"]) != locked_packages[name]:
            raise ValueError(f"license inventory version mismatch for {name}")

    if not upstream_license_path.is_file():
        raise ValueError(f"upstream license is missing: {upstream_license_path}")
    expected_license_sha = inventory["upstream"].get("licenseSha256")
    actual_license_sha = hashlib.sha256(upstream_license_path.read_bytes()).hexdigest()
    if expected_license_sha and expected_license_sha != actual_license_sha:
        raise ValueError("upstream license checksum does not match provenance")
    if not apk_database_path.is_file():
        raise ValueError(f"APK database is missing: {apk_database_path}")

    output.mkdir(parents=True, exist_ok=True)
    python_target = output / "python"
    python_target.mkdir(parents=True, exist_ok=True)
    installed = {
        _normalise(str(distribution.metadata["Name"])): distribution
        for distribution in metadata.distributions()
        if distribution.metadata.get("Name")
    }
    python_packages: list[dict[str, Any]] = []
    copied_files = 0
    for name in sorted(expected_packages):
        distribution = installed.get(name)
        if distribution is None:
            raise ValueError(f"locked distribution is not installed: {name}")
        if distribution.version != locked_packages[name]:
            raise ValueError(
                f"installed version mismatch for {name}: {distribution.version} != {locked_packages[name]}"
            )
        item = expected_packages[name]
        license_ids = [str(value) for value in item["licenses"]]
        copied_files += _copy_python_license_files(distribution, python_target, license_ids)
        python_packages.append(
            {
                "name": str(distribution.metadata["Name"]),
                "version": distribution.version,
                "purl": f"pkg:pypi/{name}@{distribution.version}",
                "licenses": license_ids,
            }
        )

    shutil.copyfile(upstream_license_path, output / "HERMES-LICENSE")
    shutil.copyfile(apk_database_path, output / "alpine-installed-packages.txt")
    readme = source_manifest_path.parent / "README.md"
    if readme.is_file():
        shutil.copyfile(readme, output / "README.md")

    bundle = {
        "schemaVersion": "task129-license-bundle-v1",
        "upstream": inventory["upstream"],
        "base": inventory["base"],
        "pythonPackages": python_packages,
        "alpinePackages": _parse_apk_database(apk_database_path),
        "files": {
            "notice": "NOTICE",
            "pythonLicenseFiles": copied_files,
            "upstreamLicense": "HERMES-LICENSE",
            "apkDatabase": "alpine-installed-packages.txt",
        },
    }
    notice_lines = [
        "Task 129 bounded Hermes editorial worker license/NOTICE bundle",
        "",
        (
            "Upstream: "
            f"{inventory['upstream']['name']} {inventory['upstream']['version']} "
            f"({inventory['upstream']['commit']})"
        ),
        "Upstream license: HERMES-LICENSE",
        "",
        "Python distributions (exact lock):",
    ]
    notice_lines.extend(
        f"- {item['name']} {item['version']}: {', '.join(item['licenses'])}"
        for item in python_packages
    )
    notice_lines.extend(
        [
            "",
            "Alpine runtime package/license inventory: alpine-installed-packages.txt",
            "The APK license field is retained verbatim in package-license-inventory.json.",
        ]
    )
    (output / "NOTICE").write_text("\n".join(notice_lines) + "\n", encoding="utf-8", newline="\n")
    (output / "package-license-inventory.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--upstream-license", type=Path, required=True)
    parser.add_argument("--apk-database", type=Path, required=True)
    args = parser.parse_args()
    build_bundle(
        output=args.output,
        lock_path=args.lock,
        source_manifest_path=args.source_manifest,
        upstream_license_path=args.upstream_license,
        apk_database_path=args.apk_database,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
