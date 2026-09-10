"""Archive a completed or owner-superseded backlog task and sync manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

try:
    from scripts.task_session import TaskSessionError, archive_guard
except ModuleNotFoundError:
    from task_session import TaskSessionError, archive_guard

TEXT_SUFFIXES = {".json", ".md"}


class ArchiveError(RuntimeError):
    """Raised when a backlog cannot be archived safely."""


def _repository_root(path: Path) -> Path:
    resolved = path.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    raise ArchiveError(f"Repository root was not found for {resolved}")


def _canonical_bytes(path: Path) -> bytes:
    if path.suffix.lower() in TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        return text.encode("utf-8")
    return path.read_bytes()


def _manifest_roots(backlog_root: Path) -> list[Path]:
    repository_root = _repository_root(backlog_root)
    roots: list[Path] = []
    candidate = backlog_root.resolve()
    while candidate != repository_root:
        if (candidate / "MANIFEST.json").is_file():
            roots.append(candidate)
        candidate = candidate.parent
    if not roots:
        raise ArchiveError(f"No MANIFEST.json found for {backlog_root}")
    return roots


def _actual_manifest_paths(root: Path) -> dict[str, Path]:
    manifest_path = root / "MANIFEST.json"
    actual: dict[str, Path] = {}
    for path in root.rglob("*"):
        if not path.is_file() or path == manifest_path:
            continue
        relative_path = path.relative_to(root)
        if ".artifacts" in relative_path.parts:
            continue
        actual[relative_path.as_posix()] = path
    return actual


def _entry(relative_path: str, path: Path) -> dict[str, object]:
    content = _canonical_bytes(path)
    return {
        "path": relative_path,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.archive-task.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def rebuild_manifest(root: Path) -> None:
    """Rebuild checksums while preserving existing manifest entry order."""

    manifest_path = root / "MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArchiveError(f"Cannot read {manifest_path}: {error}") from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ArchiveError(f"Invalid files inventory in {manifest_path}")

    actual = _actual_manifest_paths(root)
    ordered_paths: list[str] = []
    for existing in manifest["files"]:
        if not isinstance(existing, dict):
            continue
        relative_path = existing.get("path")
        if isinstance(relative_path, str) and relative_path in actual:
            ordered_paths.append(relative_path)
    ordered_paths.extend(sorted(set(actual) - set(ordered_paths)))

    manifest["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    manifest["validation_errors"] = []
    manifest["files"] = [
        _entry(relative_path, actual[relative_path]) for relative_path in ordered_paths
    ]
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    _atomic_write_text(manifest_path, serialized)


def rebuild_manifests(backlog_root: Path) -> list[Path]:
    """Rebuild the backlog manifest and any manifest-owning parent backlog."""

    roots = _manifest_roots(backlog_root)
    for root in roots:
        rebuild_manifest(root)
    return roots


def validate_manifest(root: Path) -> list[str]:
    manifest_path = root / "MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"Cannot read {manifest_path}: {error}"]
    entries = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(entries, list):
        return [f"Invalid files inventory in {manifest_path}"]

    actual = _actual_manifest_paths(root)
    errors: list[str] = []
    listed_paths: list[str] = []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            errors.append(f"Invalid entry in {manifest_path}: {item!r}")
            continue
        relative_path = item["path"]
        listed_paths.append(relative_path)
        path = actual.get(relative_path)
        if path is None:
            errors.append(f"Missing file: {root / relative_path}")
            continue
        expected = _entry(relative_path, path)
        if item.get("bytes") != expected["bytes"] or item.get("sha256") != expected["sha256"]:
            errors.append(f"Checksum drift: {root / relative_path}")

    duplicates = sorted({path for path in listed_paths if listed_paths.count(path) > 1})
    errors.extend(f"Duplicate manifest path: {path}" for path in duplicates)
    errors.extend(
        f"Unlisted file: {root / path}" for path in sorted(set(actual) - set(listed_paths))
    )
    return errors


def validate_manifests(backlog_root: Path) -> list[str]:
    errors: list[str] = []
    for root in _manifest_roots(backlog_root):
        errors.extend(validate_manifest(root))
    return errors


def _updated_task_index(index_text: str, task_name: str) -> str:
    source_target = f"]({task_name})"
    matching_lines = [line for line in index_text.splitlines() if source_target in line]
    if len(matching_lines) != 1:
        raise ArchiveError(
            f"Expected one tasks/README.md link to {task_name}, found {len(matching_lines)}"
        )

    original_line = matching_lines[0]
    updated_line = original_line.replace(source_target, f"](done/{task_name})")
    updated_line = re.sub(r"^(\s*-\s*)\[\s\]", r"\1[x]", updated_line, count=1)
    return index_text.replace(original_line, updated_line, 1)


def archive_task(backlog_root: Path, task_name: str) -> Path:
    """Move one task to tasks/done and synchronize indexes and manifests."""

    backlog_root = backlog_root.resolve()
    task_path = Path(task_name)
    if task_path.name != task_name or task_path.suffix.lower() != ".md" or task_name == "README.md":
        raise ArchiveError("--task must be one Markdown filename without directory components")

    tasks_root = backlog_root / "tasks"
    source = tasks_root / task_name
    destination = tasks_root / "done" / task_name
    index_path = tasks_root / "README.md"
    if not source.is_file():
        raise ArchiveError(f"Task source does not exist: {source}")
    if destination.exists():
        raise ArchiveError(f"Archive destination already exists: {destination}")
    if not index_path.is_file():
        raise ArchiveError(f"Task index does not exist: {index_path}")

    task_match = re.match(r"^(?P<task_id>[0-9]+[A-Z]?)-", task_name)
    if task_match is None:
        raise ArchiveError("Task filename does not contain a canonical task ID")
    try:
        archive_guard(backlog_root, task_match.group("task_id"))
    except TaskSessionError as error:
        raise ArchiveError(str(error)) from error

    original_index = index_path.read_text(encoding="utf-8")
    updated_index = _updated_task_index(original_index, task_name)
    manifest_roots = _manifest_roots(backlog_root)
    manifest_backups = {
        root / "MANIFEST.json": (root / "MANIFEST.json").read_bytes() for root in manifest_roots
    }

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        source.replace(destination)
        _atomic_write_text(index_path, updated_index)
        for root in manifest_roots:
            rebuild_manifest(root)
        errors = validate_manifests(backlog_root)
        if errors:
            raise ArchiveError("; ".join(errors))
    except Exception:
        if destination.exists() and not source.exists():
            destination.replace(source)
        _atomic_write_text(index_path, original_index)
        for manifest_path, content in manifest_backups.items():
            manifest_path.write_bytes(content)
        raise
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    archive = subparsers.add_parser("archive", help="archive one completed or superseded task")
    archive.add_argument("--backlog", required=True, type=Path)
    archive.add_argument("--task", required=True)

    check = subparsers.add_parser("check", help="validate backlog and parent manifests")
    check.add_argument("--backlog", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "archive":
            destination = archive_task(args.backlog, args.task)
            print(f"archived: {destination}")
            return 0
        errors = validate_manifests(args.backlog.resolve())
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        print(f"manifest checks passed: {args.backlog.resolve()}")
        return 0
    except ArchiveError as error:
        print(f"archive error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
