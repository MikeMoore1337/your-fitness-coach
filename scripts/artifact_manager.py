"""Manage repository-local task artifacts with fail-closed cleanup semantics.

The manager deliberately uses only the Python standard library.  It treats the
artifact root as a capability boundary: every mutation is resolved below the
exact root, reparse points are refused, and generic cleanup never enters
controller-managed worktrees or operational data.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import stat
import struct
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
TASK_ID_RE = re.compile(r"^[0-9]+[A-Z]?$", re.IGNORECASE)
DISPOSITIONS = ("DELETE", "MOVE", "KEEP", "REVIEW")
CLASSIFICATIONS = ("temporary", "evidence", "deliverables", "logs")
CANONICAL_TOP_LEVEL = ("worktrees", "tasks", "runtime", "shared", "operations")
LEGACY_RUNTIME_TOP_LEVEL = {"cache", "tmp", "tests"}
LEGACY_PROTECTED_TOP_LEVEL = {
    "backups",
    "controller-recovery",
    "deployments",
    "production-backups",
    "recovery",
}
LEGACY_EVIDENCE_TOP_LEVEL = {
    "audits",
    "brand",
    "codex-audits",
    "codex-research",
    "design-alternatives",
    "design-audit",
    "design-audits",
    "design-briefs",
    "design-exploration",
    "design-qa",
    "design-system",
    "design-v2",
    "incoming",
    "legal-audit",
    "logs",
    "notes",
    "pdf",
    "playwright-mcp",
    "qa",
    "release-evidence",
    "reports",
    "screenshots",
    "security",
    "tools",
    "ui",
    "ui-audit",
    "ui-redesign",
    "videos",
    "working-notes",
}
DEFAULT_RETENTION = {
    "temporary": "delete-after-terminal-success",
    "evidence": "retain-for-review-and-investigation",
    "deliverables": "retain-until-exact-owner-disposition",
    "logs": "limited-retention; delete-after-closeout-when-not-needed",
}
TERMINAL_STATES = {"dev-ci-success", "finished", "terminal-success", "success"}
# A production-success lease is still owned by the controller until ``finish`` records the
# final history state.  It is nevertheless safe for task-scoped temporary-artifact cleanup.
CONTROLLER_TERMINAL_LEASE_STATES = TERMINAL_STATES | {"production-success"}
CONTROLLER_STATE_NAME = "codex-task-sessions-v1"
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_ATTRIBUTE_DIRECTORY = 0x10
WINDOWS_LX_SYMLINK_TAG = 0xA000001D
WINDOWS_LX_SYMLINK_VERSION = 2
WINDOWS_FSCTL_GET_REPARSE_POINT = 0x000900A8
WINDOWS_FILE_READ_ATTRIBUTES = 0x80
WINDOWS_FILE_SHARE_ALL = 0x7
WINDOWS_OPEN_EXISTING = 3
WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
WINDOWS_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000


class ArtifactError(RuntimeError):
    """A safe, actionable artifact-manager refusal."""


class ArtifactSafetyError(ArtifactError):
    """A refusal caused by a current safety boundary or state drift."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_task_id(value: str) -> str:
    task_id = str(value).strip().upper()
    if TASK_ID_RE.fullmatch(task_id) is None:
        raise ArtifactError(f"Invalid task ID: {value!r}")
    return task_id


def _path_text(path: Path) -> str:
    return path.as_posix()


def _is_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def _resolved(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError as error:
        raise ArtifactSafetyError(f"Cannot resolve artifact path {path}: {error}") from error


def _safe_relative(base: Path, candidate: Path | str, *, allow_base: bool = False) -> Path:
    """Return a lexical path below *base* after rejecting links and traversal."""

    base_path = _resolved(base)
    raw = Path(os.fspath(candidate))
    if raw.is_absolute():
        lexical = Path(os.path.abspath(os.fspath(raw)))
    else:
        lexical = Path(os.path.abspath(os.fspath(base_path / raw)))
    try:
        relative = lexical.relative_to(base_path)
    except ValueError as error:
        raise ArtifactSafetyError(
            f"Artifact path escapes exact root: {candidate!s} (root={base_path})"
        ) from error
    if not allow_base and not relative.parts:
        raise ArtifactSafetyError(f"Artifact target must not be the root: {base_path}")

    current = base_path
    if _is_reparse(current):
        raise ArtifactSafetyError(f"Artifact root is a reparse point: {base_path}")
    for part in relative.parts:
        current = current / part
        if (current.exists() or current.is_symlink()) and _is_reparse(current):
            raise ArtifactSafetyError(f"Reparse point is not allowed in artifact path: {current}")
    resolved = _resolved(lexical)
    try:
        resolved.relative_to(base_path)
    except ValueError as error:
        raise ArtifactSafetyError(
            f"Resolved artifact path escapes exact root: {candidate!s} (root={base_path})"
        ) from error
    return lexical


def _safe_relative_name(value: str | Path) -> Path:
    raw = Path(os.fspath(value))
    if raw.is_absolute() or not raw.parts or any(part in {"", ".", ".."} for part in raw.parts):
        raise ArtifactError(f"Artifact relative path is invalid: {value!s}")
    return Path(*raw.parts)


def _atomic_write_json(path: Path, payload: Mapping[str, Any] | Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArtifactError(f"Cannot read artifact JSON {path}: {error}") from error


def _file_fingerprint(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ArtifactSafetyError(f"Cannot inspect artifact target {path}: {error}") from error
    kind = "directory" if stat.S_ISDIR(metadata.st_mode) else "file"
    return {
        "kind": kind,
        "size_bytes": int(metadata.st_size if kind == "file" else 0),
        "mtime_ns": int(metadata.st_mtime_ns),
    }


def _metadata_is_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT
    )


def _decode_lx_symlink_reparse_data(data: bytes) -> str:
    if len(data) < 12:
        raise ArtifactSafetyError("LX symlink reparse data is truncated")
    tag, data_length, _reserved = struct.unpack_from("<IHH", data)
    if tag != WINDOWS_LX_SYMLINK_TAG:
        raise ArtifactSafetyError(f"Unsupported reparse tag: 0x{tag:08x}")
    if data_length != len(data) - 8 or data_length < 4:
        raise ArtifactSafetyError("LX symlink reparse data length is invalid")
    version = struct.unpack_from("<I", data, 8)[0]
    if version != WINDOWS_LX_SYMLINK_VERSION:
        raise ArtifactSafetyError(f"Unsupported LX symlink version: {version}")
    target_bytes = data[12:]
    if not target_bytes or b"\x00" in target_bytes:
        raise ArtifactSafetyError("LX symlink target is empty or contains NUL")
    try:
        return target_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArtifactSafetyError("LX symlink target is not valid UTF-8") from error


def _read_windows_lx_symlink_reparse_data(path: Path) -> bytes:
    if os.name != "nt":
        raise ArtifactSafetyError("Windows reparse data is unavailable on this platform")
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    device_io_control = kernel32.DeviceIoControl
    device_io_control.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    device_io_control.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = create_file(
        str(path),
        WINDOWS_FILE_READ_ATTRIBUTES,
        WINDOWS_FILE_SHARE_ALL,
        None,
        WINDOWS_OPEN_EXISTING,
        WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT | WINDOWS_FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_string_buffer(16 * 1024)
        bytes_returned = wintypes.DWORD()
        succeeded = device_io_control(
            handle,
            WINDOWS_FSCTL_GET_REPARSE_POINT,
            None,
            0,
            buffer,
            len(buffer),
            ctypes.byref(bytes_returned),
            None,
        )
        if not succeeded:
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw[: bytes_returned.value]
    finally:
        close_handle(handle)


def _read_reparse_target(path: Path) -> str:
    try:
        target = os.readlink(path)
    except (OSError, ValueError) as error:
        if os.name != "nt":
            raise ArtifactSafetyError(f"Cannot inspect reparse target: {error}") from error
        try:
            target = _decode_lx_symlink_reparse_data(_read_windows_lx_symlink_reparse_data(path))
        except (OSError, ArtifactError) as reparse_error:
            raise ArtifactSafetyError(
                f"Cannot inspect supported reparse target: {reparse_error}"
            ) from error
    if os.name == "nt":
        if target.startswith("\\??\\UNC\\") or target.startswith("\\\\?\\UNC\\"):
            target = "\\\\" + target[8:]
        elif target.startswith("\\??\\") or target.startswith("\\\\?\\"):
            candidate = target[4:]
            if len(candidate) < 3 or candidate[1:3] != ":\\":
                raise ArtifactSafetyError("Unsupported Windows reparse target namespace")
            target = target[4:]
    if not target or "\x00" in target:
        raise ArtifactSafetyError("Reparse target is empty or contains NUL")
    return target


def _contained_temporary_target(
    temporary_root: Path, entry: Path, target_text: str
) -> tuple[Path, Path, str]:
    root = Path(os.path.abspath(os.fspath(temporary_root)))
    entry_path = Path(os.path.abspath(os.fspath(entry)))
    try:
        root_metadata = root.lstat()
    except OSError as error:
        raise ArtifactSafetyError(f"Cannot inspect task temporary root: {error}") from error
    if _metadata_is_reparse(root_metadata) or not stat.S_ISDIR(root_metadata.st_mode):
        raise ArtifactSafetyError("Task temporary root is not a plain directory")
    try:
        entry_path.relative_to(root)
    except ValueError as error:
        raise ArtifactSafetyError("Reparse entry is outside task temporary") from error

    raw_target = Path(target_text)
    if raw_target.drive and not raw_target.is_absolute():
        raise ArtifactSafetyError("Drive-relative reparse target is ambiguous")
    if raw_target.is_absolute():
        if os.name == "nt" and not raw_target.drive:
            raise ArtifactSafetyError("Root-relative Windows reparse target is ambiguous")
        if ".." in raw_target.parts:
            raise ArtifactSafetyError("Absolute reparse target contains parent traversal")
        if os.name == "nt" and any(":" in part for part in raw_target.parts[1:]):
            raise ArtifactSafetyError("Alternate data stream target is not allowed")
        target_path = Path(os.path.abspath(os.fspath(raw_target)))
        try:
            relative = target_path.relative_to(root)
        except ValueError as error:
            raise ArtifactSafetyError("Reparse target escapes task temporary") from error
    else:
        stack = list(entry_path.parent.relative_to(root).parts)
        for part in raw_target.parts:
            if part in {"", "."}:
                continue
            if part == "..":
                if not stack:
                    raise ArtifactSafetyError("Relative reparse target escapes task temporary")
                stack.pop()
            else:
                if os.name == "nt" and ":" in part:
                    raise ArtifactSafetyError("Alternate data stream target is not allowed")
                stack.append(part)
        relative = Path(*stack)
        target_path = root / relative

    if target_path == entry_path:
        raise ArtifactSafetyError("Reparse entry targets itself")
    current = root
    try:
        target_metadata = current.lstat()
        if _metadata_is_reparse(target_metadata):
            raise ArtifactSafetyError("Task temporary root is a reparse point")
        for index, part in enumerate(relative.parts):
            current = current / part
            target_metadata = current.lstat()
            if _metadata_is_reparse(target_metadata):
                raise ArtifactSafetyError("Reparse target traverses another reparse point")
            if index < len(relative.parts) - 1 and not stat.S_ISDIR(target_metadata.st_mode):
                raise ArtifactSafetyError("Reparse target parent is not a directory")
    except OSError as error:
        raise ArtifactSafetyError(f"Cannot inspect reparse target: {error}") from error

    if stat.S_ISDIR(target_metadata.st_mode):
        target_kind = "directory"
    elif stat.S_ISREG(target_metadata.st_mode):
        target_kind = "file"
    else:
        raise ArtifactSafetyError("Reparse target is not a regular file or directory")
    return target_path, relative, target_kind


def _temporary_entry_path(temporary_root: Path, relative: Path) -> Path:
    relative_name = _safe_relative_name(relative)
    try:
        root_metadata = temporary_root.lstat()
    except OSError as error:
        raise ArtifactSafetyError(f"Cannot inspect task temporary root: {error}") from error
    if _metadata_is_reparse(root_metadata) or not stat.S_ISDIR(root_metadata.st_mode):
        raise ArtifactSafetyError("Task temporary root is not a plain directory")
    parent = (
        temporary_root
        if not relative_name.parent.parts
        else _safe_relative(temporary_root, relative_name.parent)
    )
    entry = parent / relative_name.name
    try:
        entry.relative_to(temporary_root)
    except ValueError as error:
        raise ArtifactSafetyError("Task temporary entry escapes its exact root") from error
    return entry


def _reparse_fingerprint(path: Path, temporary_root: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ArtifactSafetyError(f"Cannot inspect reparse entry: {error}") from error
    if not _metadata_is_reparse(metadata):
        raise ArtifactSafetyError("Task cleanup entry is no longer a reparse point")
    target_text = _read_reparse_target(path)
    _target_path, target_relative, target_kind = _contained_temporary_target(
        temporary_root, path, target_text
    )
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    return {
        "kind": "reparse",
        "device": int(metadata.st_dev),
        "inode": int(metadata.st_ino),
        "mode": int(metadata.st_mode),
        "size_bytes": int(metadata.st_size),
        "mtime_ns": int(metadata.st_mtime_ns),
        "ctime_ns": int(metadata.st_ctime_ns),
        "attributes": attributes,
        "directory_entry": bool(
            stat.S_ISDIR(metadata.st_mode)
            or attributes & FILE_ATTRIBUTE_DIRECTORY
            or target_kind == "directory"
        ),
        "target": target_text,
        "target_relative": target_relative.as_posix(),
        "target_kind": target_kind,
        "containment": "task-temporary",
    }


def _remove_reparse_entry(path: Path, fingerprint: Mapping[str, Any]) -> None:
    if os.name == "nt" and fingerprint["directory_entry"]:
        os.rmdir(path)
    else:
        path.unlink()


def _iter_entries(root: Path) -> Iterable[dict[str, Any]]:
    """Walk without following symlinks, junctions, or other reparse points."""

    if not root.exists():
        return
    pending: list[tuple[Path, Path]] = [(root, Path())]
    while pending:
        current, current_relative = pending.pop()
        try:
            children = sorted(
                current.iterdir(), key=lambda item: item.name.casefold(), reverse=True
            )
        except OSError as error:
            yield {
                "path": current,
                "relative": current_relative,
                "kind": "inaccessible",
                "error": str(error),
            }
            continue
        for child in children:
            relative = current_relative / child.name
            if _is_reparse(child):
                yield {"path": child, "relative": relative, "kind": "reparse"}
                continue
            try:
                metadata = child.lstat()
            except OSError as error:
                yield {
                    "path": child,
                    "relative": relative,
                    "kind": "inaccessible",
                    "error": str(error),
                }
                continue
            if stat.S_ISDIR(metadata.st_mode):
                yield {"path": child, "relative": relative, "kind": "directory"}
                pending.append((child, relative))
            else:
                yield {
                    "path": child,
                    "relative": relative,
                    "kind": "file",
                    "size_bytes": int(metadata.st_size),
                    "mtime_ns": int(metadata.st_mtime_ns),
                }


def _hash_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _is_dynamic_legacy_top_level(name: str) -> bool:
    return name.startswith("task-") or name.startswith("ci-run-")


def _is_legacy_top_level(name: str) -> bool:
    return (
        name in LEGACY_RUNTIME_TOP_LEVEL
        or name in LEGACY_PROTECTED_TOP_LEVEL
        or name in LEGACY_EVIDENCE_TOP_LEVEL
        or _is_dynamic_legacy_top_level(name)
    )


class ArtifactManager:
    """Allocate, inspect, and safely clean repository-local artifacts."""

    def __init__(
        self,
        root: Path,
        *,
        repo_root: Path | None = None,
        controller_state_dir: Path | None = None,
        clock: Any = None,
    ) -> None:
        raw_root = Path(root).absolute()
        if raw_root.exists() and _is_reparse(raw_root):
            raise ArtifactSafetyError(f"Artifact root is a reparse point: {raw_root}")
        self.root = _resolved(raw_root)
        self.repo_root = _resolved(repo_root or self.root.parent)
        self.controller_state_dir = (
            _resolved(controller_state_dir) if controller_state_dir is not None else None
        )
        self.clock = clock or utc_now

    @property
    def tasks_root(self) -> Path:
        return self.root / "tasks"

    def task_root(self, task_id: str) -> Path:
        normalized = normalize_task_id(task_id)
        return _safe_relative(self.root, Path("tasks") / normalized)

    def _task_manifest_path(self, task_id: str) -> Path:
        return _safe_relative(
            self.root, Path("tasks") / normalize_task_id(task_id) / "manifest.json"
        )

    def ensure_layout(self, task_id: str | None = None) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for name in CANONICAL_TOP_LEVEL:
            _safe_relative(self.root, name).mkdir(exist_ok=True)
        for name in ("cache", "tmp", "tests"):
            _safe_relative(self.root, Path("runtime") / name).mkdir(parents=True, exist_ok=True)
        for name in ("backups", "deployments", "recovery"):
            _safe_relative(self.root, Path("operations") / name).mkdir(parents=True, exist_ok=True)
        if task_id is not None:
            normalized = normalize_task_id(task_id)
            task_root = self.task_root(normalized)
            for name in ("temporary", "evidence", "deliverables", "logs"):
                _safe_relative(self.root, task_root / name).mkdir(parents=True, exist_ok=True)
            manifest = self._task_manifest_path(normalized)
            if not manifest.exists():
                _atomic_write_json(manifest, self._new_manifest(normalized))

    def _new_manifest(self, task_id: str) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "classification": "task-artifact-manifest",
            "task_id": normalize_task_id(task_id),
            "created_at": self.clock(),
            "updated_at": self.clock(),
            "provenance": {
                "created_by": "scripts/artifact_manager.py",
                "command": "ensure-task-layout",
            },
            "retention": dict(DEFAULT_RETENTION),
            "entries": [],
        }

    def _load_manifest(self, task_id: str) -> dict[str, Any] | None:
        path = self._task_manifest_path(task_id)
        if not path.exists():
            return None
        if _is_reparse(path):
            raise ArtifactSafetyError(f"Task manifest is a reparse point: {path}")
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise ArtifactError(f"Task manifest must be a JSON object: {path}")
        return payload

    def allocate(
        self,
        task_id: str,
        classification: str,
        relative_path: str | Path,
        *,
        purpose: str,
        command: str,
        owner: str = "task-worker",
        retention: str | None = None,
        create: bool = False,
    ) -> Path:
        normalized = normalize_task_id(task_id)
        classification = str(classification).strip().lower()
        if classification not in CLASSIFICATIONS:
            raise ArtifactError(
                f"Unknown artifact classification {classification!r}; expected one of {CLASSIFICATIONS}"
            )
        relative = _safe_relative_name(relative_path)
        if relative.parts[0] != classification:
            raise ArtifactError(
                f"Task artifact path must begin with {classification}/, got {relative.as_posix()}"
            )
        self.ensure_layout(normalized)
        task_root = self.task_root(normalized)
        target = _safe_relative(task_root, relative)
        manifest = self._load_manifest(normalized) or self._new_manifest(normalized)
        entries = manifest.setdefault("entries", [])
        if not isinstance(entries, list):
            raise ArtifactError(
                f"Task manifest entries must be a list: {self._task_manifest_path(normalized)}"
            )
        new_entry = {
            "path": relative.as_posix(),
            "classification": classification,
            "purpose": str(purpose).strip() or "unspecified",
            "owner": str(owner).strip() or "task-worker",
            "created_at": self.clock(),
            "retention": retention or DEFAULT_RETENTION[classification],
            "command": str(command).strip() or "unspecified",
        }
        matching = [
            item
            for item in entries
            if isinstance(item, dict) and item.get("path") == new_entry["path"]
        ]
        if matching:
            existing = matching[0]
            for key in ("classification", "owner", "purpose", "retention"):
                if existing.get(key) != new_entry[key]:
                    raise ArtifactError(
                        f"Task artifact allocation conflicts with manifest entry {relative.as_posix()}"
                    )
        else:
            entries.append(new_entry)
        manifest["schema_version"] = SCHEMA_VERSION
        manifest["task_id"] = normalized
        manifest["classification"] = "task-artifact-manifest"
        manifest["updated_at"] = self.clock()
        manifest["entries"] = sorted(entries, key=lambda item: str(item.get("path", "")))
        _atomic_write_json(self._task_manifest_path(normalized), manifest)
        if create:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def allocate_directory(
        self,
        task_id: str,
        classification: str,
        relative_path: str | Path,
        *,
        purpose: str,
        command: str,
        owner: str = "task-worker",
        retention: str | None = None,
    ) -> Path:
        return self.allocate(
            task_id,
            classification,
            relative_path,
            purpose=purpose,
            command=command,
            owner=owner,
            retention=retention,
            create=True,
        )

    def promote_file(
        self,
        source: Path,
        task_id: str,
        relative_destination: str | Path,
        *,
        purpose: str,
        command: str,
        owner: str = "task-worker",
    ) -> Path:
        normalized = normalize_task_id(task_id)
        source_path = _safe_relative(self.root, source)
        if not source_path.is_file() or _is_reparse(source_path):
            raise ArtifactSafetyError(f"Promotion source is not a regular file: {source_path}")
        destination_relative = _safe_relative_name(relative_destination)
        destination = self.allocate(
            normalized,
            "evidence",
            destination_relative,
            purpose=purpose,
            command=command,
            owner=owner,
            create=False,
        )
        if destination.exists():
            raise ArtifactError(f"Promotion destination already exists: {destination}")
        source_path.replace(destination)
        return destination

    def _manifest_validation(self, task_id: str) -> dict[str, Any]:
        normalized = normalize_task_id(task_id)
        task_root = self.task_root(normalized)
        errors: list[str] = []
        warnings: list[str] = []
        manifest = self._load_manifest(normalized)
        if manifest is None:
            files = [
                item
                for item in _iter_entries(task_root)
                if item["kind"] in {"file", "reparse", "inaccessible"}
                and item["relative"].name != "manifest.json"
            ]
            if files:
                errors.append(f"Task {normalized} has artifacts but no manifest.json")
            return {"task_id": normalized, "ok": not errors, "errors": errors, "warnings": warnings}
        if manifest.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"Task {normalized} manifest schema_version must be {SCHEMA_VERSION}")
        if manifest.get("task_id") != normalized:
            errors.append(f"Task {normalized} manifest task_id does not match")
        if manifest.get("classification") != "task-artifact-manifest":
            errors.append(f"Task {normalized} manifest classification is invalid")
        entries = manifest.get("entries")
        if not isinstance(entries, list):
            errors.append(f"Task {normalized} manifest entries must be a list")
            entries = []
        seen: set[str] = set()
        covered: list[tuple[Path, str]] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                errors.append(f"Task {normalized} manifest entry {index} is not an object")
                continue
            raw_path = entry.get("path")
            classification = entry.get("classification")
            if not isinstance(raw_path, str) or not raw_path:
                errors.append(f"Task {normalized} manifest entry {index} has no relative path")
                continue
            try:
                relative = _safe_relative_name(raw_path)
                _safe_relative(task_root, relative)
            except ArtifactError as error:
                errors.append(f"Task {normalized} manifest entry {index}: {error}")
                continue
            path_text = relative.as_posix()
            if path_text in seen:
                errors.append(f"Task {normalized} manifest contains duplicate path {path_text}")
            seen.add(path_text)
            if classification not in CLASSIFICATIONS:
                errors.append(
                    f"Task {normalized} manifest entry {path_text} has invalid classification"
                )
            elif relative.parts[0] != classification:
                errors.append(
                    f"Task {normalized} manifest entry {path_text} crosses classification boundary"
                )
            else:
                covered.append((relative, classification))
            for required in ("purpose", "owner", "created_at", "retention", "command"):
                if not isinstance(entry.get(required), str) or not entry[required].strip():
                    errors.append(
                        f"Task {normalized} manifest entry {path_text} is missing {required}"
                    )
        for item in _iter_entries(task_root):
            if item["kind"] not in {"file", "reparse", "inaccessible"}:
                continue
            relative = item["relative"]
            if relative.name == "manifest.json":
                continue
            if relative.parts and relative.parts[0] in {"evidence", "deliverables"}:
                if not any(
                    relative == declared or str(relative).startswith(f"{declared}{os.sep}")
                    for declared, _classification in covered
                ):
                    errors.append(
                        f"Task {normalized} durable artifact is not in manifest: {relative.as_posix()}"
                    )
            elif relative.parts and relative.parts[0] not in {"temporary", "logs"}:
                warnings.append(f"Task {normalized} has unclassified path: {relative.as_posix()}")
        return {
            "task_id": normalized,
            "ok": not errors,
            "errors": sorted(set(errors)),
            "warnings": sorted(set(warnings)),
        }

    def validate_source_paths(self, source_root: Path | None = None) -> dict[str, Any]:
        root = _resolved(source_root or self.repo_root)
        files: list[Path] = []
        for name in ("scripts", "tests", "frontend", "backend", "bot", ".github"):
            candidate = root / name
            if candidate.is_dir():
                files.extend(path for path in _iter_files(candidate))
        for name in ("AGENTS.md", "pyproject.toml", ".gitignore"):
            candidate = root / name
            if candidate.is_file():
                files.append(candidate)
        unknown: list[str] = []
        legacy: Counter[str] = Counter()
        pattern = re.compile(r"\.artifacts[\\/]([A-Za-z0-9_.-]+)")
        for path in sorted(set(files)):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):  # fmt: skip
                continue
            for match in pattern.finditer(text):
                top = match.group(1)
                if top in CANONICAL_TOP_LEVEL:
                    continue
                if _is_legacy_top_level(top):
                    legacy[top] += 1
                else:
                    unknown.append(f"{path.relative_to(root).as_posix()}:.artifacts/{top}")
        return {
            "ok": not unknown,
            "unknown": sorted(set(unknown)),
            "legacy": dict(sorted(legacy.items())),
        }

    def validate(
        self, *, task_id: str | None = None, source_root: Path | None = None
    ) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        if self.root.exists():
            for entry in self.root.iterdir():
                name = entry.name
                if _is_reparse(entry):
                    errors.append(f"Reparse point is not allowed in artifact root: {name}")
                    continue
                if name in CANONICAL_TOP_LEVEL or _is_legacy_top_level(name):
                    continue
                errors.append(f"Unclassified top-level artifact path: {name}")
        manifests: list[dict[str, Any]] = []
        if _is_reparse(self.tasks_root):
            errors.append("Reparse point is not allowed for artifact tasks/")
        elif self.tasks_root.is_dir():
            for task_path in sorted(
                self.tasks_root.iterdir(), key=lambda item: item.name.casefold()
            ):
                if not task_path.is_dir() or _is_reparse(task_path):
                    continue
                if task_id is not None and task_path.name.upper() != normalize_task_id(task_id):
                    continue
                if TASK_ID_RE.fullmatch(task_path.name) is None:
                    errors.append(f"Invalid task artifact directory name: {task_path.name}")
                    continue
                result = self._manifest_validation(task_path.name)
                manifests.append(result)
                errors.extend(result["errors"])
                warnings.extend(result["warnings"])
        source = self.validate_source_paths(source_root)
        errors.extend(f"Ad-hoc source artifact path: {item}" for item in source["unknown"])
        return {
            "ok": not errors,
            "root": str(self.root),
            "errors": sorted(set(errors)),
            "warnings": sorted(set(warnings)),
            "manifests": manifests,
            "source": source,
        }

    def _state_dir(self) -> Path | None:
        if self.controller_state_dir is not None:
            return self.controller_state_dir
        git_dir = self.repo_root / ".git"
        if git_dir.is_dir():
            return git_dir / CONTROLLER_STATE_NAME
        if git_dir.is_file():
            completed = subprocess.run(
                [
                    "git",
                    "-c",
                    f"safe.directory={self.repo_root.as_posix()}",
                    "rev-parse",
                    "--git-common-dir",
                ],
                cwd=self.repo_root,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if completed.returncode == 0 and completed.stdout.strip():
                return Path(completed.stdout.strip()).resolve() / CONTROLLER_STATE_NAME
        return None

    def _controller_guard(self, *, task_id: str | None = None) -> list[str]:
        state_dir = self._state_dir()
        if state_dir is None or not state_dir.exists():
            return []
        issues: list[str] = []
        lock = state_dir / "state.lock"
        if lock.exists():
            issues.append(f"controller state lock exists: {lock.name}")
        leases = state_dir / "leases"
        active_task_ids: list[str] = []
        if leases.is_dir():
            for path in sorted(leases.glob("*.json")):
                payload = _read_json(path)
                if not isinstance(payload, dict):
                    issues.append(f"controller lease is not an object: {path.name}")
                    continue
                mode = str(payload.get("mode", ""))
                lease_task = str(payload.get("task_id", ""))
                if mode in {"integration", "release"}:
                    issues.append(f"active incompatible controller lease: {path.name}")
                    continue
                if lease_task and lease_task != task_id:
                    active_task_ids.append(lease_task)
                elif (
                    lease_task == task_id
                    and str(payload.get("lifecycle_state", ""))
                    not in CONTROLLER_TERMINAL_LEASE_STATES
                ):
                    issues.append(f"target task lease is not terminal: {path.name}")
        if task_id is None and active_task_ids:
            issues.append("active task leases protect shared artifact cleanup")
        history_path = state_dir / "history" / "task-132.json"
        if history_path.exists():
            history = _read_json(history_path)
            if isinstance(history, dict) and history.get("state") not in {
                "finished",
                "terminal-success",
            }:
                issues.append("Task 132 history is not terminally finished")
        consumers = self.root / "runtime" / "consumers"
        if consumers.is_dir():
            for marker in sorted(consumers.glob("*.json")):
                payload = _read_json(marker)
                pid = payload.get("pid") if isinstance(payload, dict) else None
                if not isinstance(pid, int) or pid <= 0:
                    issues.append(f"invalid runtime consumer marker: {marker.name}")
                elif _pid_alive(pid):
                    issues.append(f"active runtime process consumer: {marker.name}")
        return sorted(set(issues))

    def _worktree_inventory(self) -> list[dict[str, Any]]:
        completed = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={self.repo_root.as_posix()}",
                "worktree",
                "list",
                "--porcelain",
            ],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            return []
        result: list[dict[str, Any]] = []
        record: dict[str, str] = {}
        for line in [*completed.stdout.splitlines(), ""]:
            if line:
                key, _, value = line.partition(" ")
                record[key] = value
                continue
            if not record:
                continue
            result.append(
                {
                    "path": record.get("worktree", ""),
                    "head": record.get("HEAD", ""),
                    "branch": record.get("branch", "").removeprefix("refs/heads/"),
                    "detached": "detached" in record,
                }
            )
            record = {}
        return result

    def _task_terminal(self, task_id: str) -> bool:
        state_dir = self._state_dir()
        if state_dir is None:
            return False
        history_path = state_dir / "history" / f"task-{normalize_task_id(task_id)}.json"
        if not history_path.exists():
            return False
        payload = _read_json(history_path)
        return isinstance(payload, dict) and payload.get("state") in TERMINAL_STATES

    def _inventory_record(
        self,
        item: Mapping[str, Any],
        *,
        classification: str,
        disposition: str,
        reason: str,
    ) -> dict[str, Any]:
        relative = Path(item["relative"])
        kind = str(item["kind"])
        size = int(item.get("size_bytes", 0)) if kind == "file" else 0
        record: dict[str, Any] = {
            "path": relative.as_posix(),
            "category": classification,
            "classification": classification,
            "reason": reason,
            "size_bytes": size,
            "disposition": disposition,
            "kind": "reparse" if kind == "reparse" else kind,
        }
        if kind == "file":
            record["fingerprint"] = {
                "kind": "file",
                "size_bytes": size,
                "mtime_ns": int(item.get("mtime_ns", 0)),
            }
        if kind in {"reparse", "inaccessible"}:
            record["safety"] = "do-not-follow"
            if item.get("error"):
                record["error"] = str(item["error"])
        return record

    def _inventory(
        self, *, stale_runtime: bool = False, runtime_ttl: timedelta | None = None
    ) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        guard = self._controller_guard()
        now = datetime.now(UTC)
        entries: list[dict[str, Any]] = []
        for item in _iter_entries(self.root):
            relative = Path(item["relative"])
            if not relative.parts:
                continue
            top = relative.parts[0]
            if item["kind"] in {"reparse", "inaccessible"}:
                entries.append(
                    self._inventory_record(
                        item,
                        classification="unclassified",
                        disposition="REVIEW",
                        reason="reparse or inaccessible path requires exact owner review",
                    )
                )
                continue
            if item["kind"] != "file":
                continue
            classification = "protected"
            disposition = "KEEP"
            reason = "protected artifact area"
            if top == "worktrees":
                classification, reason = (
                    "protected",
                    "controller-managed worktree; never filesystem-delete",
                )
            elif top == "operations":
                classification, reason = (
                    "protected",
                    "backup/deployment/recovery evidence uses its own lifecycle",
                )
            elif top == "shared":
                classification, reason = (
                    "shared",
                    "explicitly reusable local asset; generic cleanup is not allowed",
                )
            elif top == "tasks" and len(relative.parts) >= 2:
                task_id = relative.parts[1]
                if TASK_ID_RE.fullmatch(task_id) is None:
                    classification, disposition, reason = (
                        "unclassified",
                        "REVIEW",
                        "invalid task directory name",
                    )
                elif len(relative.parts) >= 3 and relative.parts[2] == "temporary":
                    classification = "temporary"
                    if self._task_terminal(task_id) and not guard:
                        disposition, reason = (
                            "DELETE",
                            "exact task temporary data after terminal success",
                        )
                    else:
                        disposition, reason = (
                            "KEEP",
                            "active or unproven task state protects temporary data",
                        )
                elif len(relative.parts) >= 3 and relative.parts[2] in {
                    "evidence",
                    "deliverables",
                    "logs",
                }:
                    classification = relative.parts[2]
                    disposition = "KEEP"
                    reason = "task-scoped durable or limited-retention evidence"
                elif relative.parts[2] == "manifest.json":
                    classification, disposition, reason = (
                        "metadata",
                        "KEEP",
                        "task manifest is the retention source of truth",
                    )
                else:
                    classification, disposition, reason = (
                        "unclassified",
                        "REVIEW",
                        "unknown task artifact class",
                    )
            elif top == "runtime":
                classification = "temporary"
                disposition = "KEEP"
                reason = "runtime data is cleaned only by bounded stale-runtime policy"
                if stale_runtime and runtime_ttl is not None and not guard:
                    try:
                        age = now - datetime.fromtimestamp(item["mtime_ns"] / 1_000_000_000, tz=UTC)
                    except (KeyError, ValueError, OSError):  # fmt: skip
                        age = timedelta(0)
                    if age >= runtime_ttl:
                        disposition, reason = "DELETE", "bounded stale runtime candidate"
            elif top in LEGACY_RUNTIME_TOP_LEVEL:
                classification = "temporary"
                if guard:
                    disposition, reason = (
                        "KEEP",
                        "shared legacy runtime cleanup blocked by active state",
                    )
                else:
                    disposition, reason = (
                        "DELETE",
                        "legacy reproducible cache/test/temp data; migrate producers to runtime",
                    )
            elif top in LEGACY_PROTECTED_TOP_LEVEL:
                classification, disposition, reason = (
                    "protected",
                    "KEEP",
                    "operational/recovery data is protected",
                )
            elif top in LEGACY_EVIDENCE_TOP_LEVEL or _is_dynamic_legacy_top_level(top):
                classification, disposition, reason = (
                    "evidence",
                    "REVIEW",
                    "legacy evidence path needs durable-reference review",
                )
            else:
                classification, disposition, reason = (
                    "unclassified",
                    "REVIEW",
                    "new ad-hoc top-level artifact path",
                )
            entries.append(
                self._inventory_record(
                    item,
                    classification=classification,
                    disposition=disposition,
                    reason=reason,
                )
            )
        return sorted(entries, key=lambda item: str(item["path"]).casefold())

    @staticmethod
    def _summary(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        counts: Counter[str] = Counter()
        bytes_by_disposition: Counter[str] = Counter()
        class_counts: Counter[str] = Counter()
        for entry in entries:
            disposition = str(entry.get("disposition", "REVIEW"))
            counts[disposition] += 1
            bytes_by_disposition[disposition] += int(entry.get("size_bytes", 0))
            class_counts[str(entry.get("classification", "unclassified"))] += 1
        return {
            "counts": {name: counts[name] for name in DISPOSITIONS},
            "bytes": {name: bytes_by_disposition[name] for name in DISPOSITIONS},
            "class_counts": dict(sorted(class_counts.items())),
            "total_count": sum(counts.values()),
            "total_bytes": sum(bytes_by_disposition.values()),
        }

    def audit(
        self, *, stale_runtime: bool = False, runtime_ttl: timedelta | None = None
    ) -> dict[str, Any]:
        entries = self._inventory(stale_runtime=stale_runtime, runtime_ttl=runtime_ttl)
        validation = self.validate()
        return {
            "schema_version": SCHEMA_VERSION,
            "operation": "audit",
            "root": str(self.root),
            "generated_at": self.clock(),
            "entries": entries,
            "summary": self._summary(entries),
            "safety": {"issues": self._controller_guard(), "worktrees": self._worktree_inventory()},
            "validation": validation,
        }

    def dry_run(
        self, *, stale_runtime: bool = False, runtime_ttl: timedelta | None = None
    ) -> dict[str, Any]:
        audit = self.audit(stale_runtime=stale_runtime, runtime_ttl=runtime_ttl)
        body = {
            "schema_version": SCHEMA_VERSION,
            "operation": "dry-run",
            "root": str(self.root),
            "generated_at": self.clock(),
            "entries": audit["entries"],
            "summary": audit["summary"],
            "safety": audit["safety"],
            "validation": audit["validation"],
        }
        body["plan_sha256"] = _hash_payload(body)
        return body

    def _verify_plan(
        self, plan: Mapping[str, Any], approved_plan_sha256: str | None
    ) -> list[dict[str, Any]]:
        expected = plan.get("plan_sha256")
        body = {key: value for key, value in plan.items() if key != "plan_sha256"}
        actual = _hash_payload(body)
        if not isinstance(expected, str) or expected != actual:
            raise ArtifactSafetyError("Artifact cleanup plan hash is invalid or was modified")
        if approved_plan_sha256 != expected:
            raise ArtifactSafetyError("Exact owner-approved plan SHA256 is required before apply")
        if _resolved(Path(str(plan.get("root", "")))) != self.root:
            raise ArtifactSafetyError(
                "Artifact cleanup plan root does not match the exact manager root"
            )
        entries = plan.get("entries")
        if not isinstance(entries, list):
            raise ArtifactError("Artifact cleanup plan entries must be a list")
        return [entry for entry in entries if isinstance(entry, dict)]

    def _plan_marker(self, plan_sha256: str) -> Path:
        if re.fullmatch(r"[0-9a-f]{64}", plan_sha256) is None:
            raise ArtifactSafetyError("Cleanup plan SHA256 is malformed")
        return _safe_relative(
            self.root,
            Path("operations") / "recovery" / "cleanup-plans" / f"{plan_sha256}.json",
        )

    def apply_plan(
        self, plan: Mapping[str, Any], *, approved_plan_sha256: str | None
    ) -> dict[str, Any]:
        entries = self._verify_plan(plan, approved_plan_sha256)
        guard = self._controller_guard()
        if guard:
            raise ArtifactSafetyError("Cleanup blocked: " + "; ".join(guard))
        marker = self._plan_marker(str(plan["plan_sha256"]))
        previously_applied = marker.exists()
        mutations = [entry for entry in entries if entry.get("disposition") in {"DELETE", "MOVE"}]
        preflight: list[tuple[dict[str, Any], Path]] = []
        for entry in mutations:
            raw_path = entry.get("path")
            if not isinstance(raw_path, str):
                raise ArtifactSafetyError("Cleanup plan contains an entry without a relative path")
            target = _safe_relative(self.root, _safe_relative_name(raw_path))
            if not target.exists():
                if previously_applied:
                    continue
                raise ArtifactSafetyError(f"Cleanup plan drift detected at {raw_path}")
            if _is_reparse(target):
                raise ArtifactSafetyError(f"Cleanup refuses reparse target: {raw_path}")
            current = _file_fingerprint(target)
            expected = entry.get("fingerprint")
            if isinstance(expected, dict) and current != expected:
                raise ArtifactSafetyError(f"Cleanup plan drift detected at {raw_path}")
            preflight.append((entry, target))
        removed: list[str] = []
        moved: list[dict[str, str]] = []
        errors: list[dict[str, str]] = []
        before_bytes = _tree_file_bytes(self.root)
        for entry, target in preflight:
            relative = str(entry["path"])
            try:
                if entry.get("disposition") == "DELETE":
                    target.unlink()
                    removed.append(relative)
                else:
                    destination_raw = entry.get("destination")
                    if not isinstance(destination_raw, str):
                        raise ArtifactSafetyError(
                            f"MOVE entry has no exact destination: {relative}"
                        )
                    destination = _safe_relative(self.root, _safe_relative_name(destination_raw))
                    if destination.exists() or _is_reparse(destination.parent):
                        raise ArtifactSafetyError(
                            f"MOVE destination is not empty/safe: {destination_raw}"
                        )
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    target.replace(destination)
                    moved.append({"source": relative, "destination": destination_raw})
            except (OSError, ArtifactError) as error:
                errors.append({"path": relative, "reason": str(error)})
                break
        marker_error: dict[str, str] | None = None
        if not errors:
            try:
                _atomic_write_json(
                    marker,
                    {
                        "schema_version": SCHEMA_VERSION,
                        "plan_sha256": plan["plan_sha256"],
                        "operation": plan.get("operation", "unknown"),
                        "applied_at": utc_now(),
                    },
                )
            except OSError as error:
                marker_error = {
                    "path": marker.relative_to(self.root).as_posix(),
                    "reason": str(error),
                }
        after_bytes = _tree_file_bytes(self.root)
        result = {
            "schema_version": SCHEMA_VERSION,
            "operation": "apply-plan",
            "root": str(self.root),
            "plan_sha256": plan["plan_sha256"],
            "status": "completed" if not errors and marker_error is None else "partial-failure",
            "removed": removed,
            "moved": moved,
            "cleanup_errors": [*errors, *([marker_error] if marker_error else [])],
            "removed_count": len(removed),
            "removed_bytes": sum(
                int(entry.get("size_bytes", 0))
                for entry in mutations
                if entry.get("path") in removed
            ),
            "before_bytes": before_bytes,
            "after_bytes": after_bytes,
            "freed_bytes": max(0, before_bytes - after_bytes),
        }
        return result

    def cleanup_task(
        self,
        task_id: str,
        *,
        terminal_state: str,
        apply: bool = True,
        include_prefixes: Sequence[str] = (),
        exclude_prefixes: Sequence[str] = (),
    ) -> dict[str, Any]:
        normalized = normalize_task_id(task_id)
        if terminal_state not in TERMINAL_STATES:
            raise ArtifactSafetyError(
                f"Task {normalized} cleanup requires a terminal success state"
            )
        guard = self._controller_guard(task_id=normalized)
        task_root = self.task_root(normalized)
        temporary_root = _safe_relative(task_root, "temporary")
        try:
            temporary_metadata = temporary_root.lstat()
        except FileNotFoundError:
            return self._cleanup_result(normalized, "noop", [], [], [], 0, 0, [])
        except OSError as error:
            return self._cleanup_result(
                normalized,
                "blocked",
                [],
                [],
                [{"path": "temporary", "reason": f"Cannot inspect task temporary root: {error}"}],
                0,
                0,
                [],
            )
        if _metadata_is_reparse(temporary_metadata) or not stat.S_ISDIR(temporary_metadata.st_mode):
            return self._cleanup_result(
                normalized,
                "blocked",
                [],
                [],
                [{"path": "temporary", "reason": "Task temporary root is not a plain directory"}],
                0,
                0,
                [],
            )
        includes = self._normalize_scope_prefixes(include_prefixes, base="temporary")
        excludes = self._normalize_scope_prefixes(exclude_prefixes, base="temporary")
        candidates: list[dict[str, Any]] = []
        inventory_paths: list[str] = []
        safety_errors = list(guard)
        for item in _iter_entries(temporary_root):
            if item["kind"] not in {"file", "reparse", "inaccessible"}:
                continue
            relative_to_temporary = Path(item["relative"])
            if item["kind"] == "inaccessible" and not relative_to_temporary.parts:
                safety_errors.append(
                    f"cannot inventory task temporary: {item.get('error', 'inaccessible')}"
                )
                continue
            relative = Path("temporary") / relative_to_temporary
            selected = any(_path_is_under(relative, prefix) for prefix in includes)
            if item["kind"] == "inaccessible":
                selected = selected or any(_path_is_under(prefix, relative) for prefix in includes)
            if includes and not selected:
                continue
            if any(_path_is_under(relative, prefix) for prefix in excludes):
                continue
            path_text = (Path("tasks") / normalized / relative).as_posix()
            inventory_paths.append(path_text)
            if item["kind"] == "inaccessible":
                safety_errors.append(
                    f"unsafe task artifact path: {relative.as_posix()} ({item.get('error', 'inaccessible')})"
                )
                continue
            try:
                entry_relative = _safe_relative_name(relative_to_temporary)
                target = _temporary_entry_path(temporary_root, entry_relative)
                if target != item["path"]:
                    raise ArtifactSafetyError("Task cleanup inventory path changed")
                if item["kind"] == "file":
                    fingerprint = {
                        "kind": "file",
                        "size_bytes": int(item["size_bytes"]),
                        "mtime_ns": int(item["mtime_ns"]),
                    }
                    size_bytes = int(item["size_bytes"])
                else:
                    fingerprint = _reparse_fingerprint(target, temporary_root)
                    size_bytes = 0
                candidates.append(
                    {
                        "path": path_text,
                        "relative": entry_relative,
                        "kind": item["kind"],
                        "fingerprint": fingerprint,
                        "size_bytes": size_bytes,
                    }
                )
            except (OSError, ArtifactError) as error:
                safety_errors.append(f"unsafe task artifact path: {relative.as_posix()} ({error})")
        if safety_errors:
            return self._cleanup_result(
                normalized,
                "blocked",
                [],
                [],
                [{"path": "temporary", "reason": issue} for issue in sorted(set(safety_errors))],
                sum(int(item.get("size_bytes", 0)) for item in candidates),
                sum(int(item.get("size_bytes", 0)) for item in candidates),
                inventory_paths,
            )
        plan_entries = [
            {
                "path": item["path"],
                "category": "temporary",
                "classification": "temporary",
                "reason": "exact task-owned temporary data after terminal success",
                "size_bytes": int(item["size_bytes"]),
                "disposition": "DELETE",
                "kind": item["kind"],
                "fingerprint": item["fingerprint"],
            }
            for item in candidates
        ]
        before = sum(int(entry["size_bytes"]) for entry in plan_entries)
        if not apply:
            return self._cleanup_result(
                normalized,
                "dry-run",
                [],
                [],
                [],
                before,
                before,
                [str(entry["path"]) for entry in plan_entries],
            )
        removed: list[str] = []
        errors: list[dict[str, str]] = []
        removed_reparse_count = 0
        for entry in plan_entries:
            try:
                raw_path = _safe_relative_name(entry["path"])
                expected_prefix = ("tasks", normalized, "temporary")
                if raw_path.parts[:3] != expected_prefix or len(raw_path.parts) < 4:
                    raise ArtifactSafetyError("task cleanup plan escaped task temporary")
                relative = Path(*raw_path.parts[3:])
                if entry["kind"] == "reparse":
                    target = _temporary_entry_path(temporary_root, relative)
                    current = _reparse_fingerprint(target, temporary_root)
                    if current != entry["fingerprint"]:
                        raise ArtifactSafetyError(
                            "task cleanup reparse entry changed after inventory"
                        )
                    _remove_reparse_entry(target, current)
                    removed_reparse_count += 1
                else:
                    target = _safe_relative(self.root, raw_path)
                    if not target.exists():
                        raise ArtifactSafetyError("task cleanup target disappeared after inventory")
                    if _is_reparse(target):
                        raise ArtifactSafetyError("task cleanup target became a reparse point")
                    current = _file_fingerprint(target)
                    if current != entry["fingerprint"]:
                        raise ArtifactSafetyError("task cleanup target changed after inventory")
                    target.unlink()
                removed.append(str(entry["path"]))
            except (OSError, ArtifactError) as error:
                errors.append({"path": str(entry["path"]), "reason": str(error)})
                break
        if not errors:
            self._remove_empty_task_directories(task_root, includes, excludes)
        after = sum(
            int(entry["size_bytes"]) for entry in plan_entries if entry["path"] not in removed
        )
        result = self._cleanup_result(
            normalized,
            "completed" if not errors else "partial-failure",
            removed,
            [],
            errors,
            before,
            after,
            [str(entry["path"]) for entry in plan_entries if entry["path"] not in removed],
            removed_reparse_count=removed_reparse_count,
        )
        return result

    @staticmethod
    def _cleanup_result(
        task_id: str,
        status: str,
        removed: Sequence[str],
        preserved: Sequence[str],
        errors: Sequence[Mapping[str, str]],
        before_bytes: int,
        after_bytes: int,
        remaining: Sequence[str],
        *,
        removed_reparse_count: int = 0,
    ) -> dict[str, Any]:
        removed_bytes = max(0, before_bytes - after_bytes)
        return {
            "schema_version": SCHEMA_VERSION,
            "operation": "cleanup-task",
            "task_id": task_id,
            "status": status,
            "removed": list(removed),
            "preserved": list(preserved) + list(remaining),
            "cleanup_errors": [dict(item) for item in errors],
            "removed_count": len(removed),
            "removed_reparse_count": removed_reparse_count,
            "preserved_count": len(preserved) + len(remaining),
            "removed_bytes": removed_bytes,
            "before_bytes": before_bytes,
            "after_bytes": after_bytes,
            "freed_bytes": removed_bytes,
        }

    @staticmethod
    def _normalize_scope_prefixes(prefixes: Sequence[str], *, base: str) -> list[Path]:
        result: list[Path] = []
        for value in prefixes:
            relative = _safe_relative_name(value)
            if relative.parts[0] == base:
                result.append(relative)
            else:
                result.append(Path(base) / relative)
        return result

    @staticmethod
    def _remove_empty_task_directories(
        task_root: Path, includes: Sequence[Path], excludes: Sequence[Path]
    ) -> None:
        temporary = task_root / "temporary"
        if not temporary.exists():
            return
        directories = [item for item in _iter_entries(temporary) if item["kind"] == "directory"]
        for item in sorted(
            directories, key=lambda value: len(value["relative"].parts), reverse=True
        ):
            relative = Path("temporary") / item["relative"]
            if includes and not any(_path_is_under(relative, prefix) for prefix in includes):
                continue
            if any(_path_is_under(relative, prefix) for prefix in excludes):
                continue
            with suppress(OSError):
                item["path"].rmdir()

    def cleanup_runtime(
        self,
        *,
        ttl: timedelta,
        max_entries: int = 1000,
        max_bytes: int = 512 * 1024 * 1024,
        apply: bool = False,
        approved_plan_sha256: str | None = None,
        plan: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if max_entries < 1 or max_bytes < 1:
            raise ArtifactError("Runtime cleanup bounds must be positive")
        guard = self._controller_guard()
        if guard:
            return {
                "schema_version": SCHEMA_VERSION,
                "operation": "cleanup-runtime",
                "status": "blocked",
                "cleanup_errors": [{"path": "runtime", "reason": issue} for issue in guard],
                "removed": [],
                "removed_count": 0,
                "removed_bytes": 0,
            }
        if plan is not None:
            if not apply:
                return dict(plan)
            entries = plan.get("entries")
            if not isinstance(entries, list):
                raise ArtifactError("Runtime cleanup plan entries must be a list")
            for entry in entries:
                if not isinstance(entry, Mapping) or entry.get("disposition") not in {
                    "DELETE",
                    "MOVE",
                }:
                    continue
                raw_path = entry.get("path")
                if not isinstance(raw_path, str):
                    raise ArtifactSafetyError(
                        "Runtime cleanup plan contains an entry without a relative path"
                    )
                relative = _safe_relative_name(raw_path)
                if relative.parts[:2] not in {
                    ("runtime", "cache"),
                    ("runtime", "tmp"),
                    ("runtime", "tests"),
                }:
                    raise ArtifactSafetyError(
                        f"Runtime cleanup plan escapes runtime areas: {raw_path}"
                    )
            result = self.apply_plan(plan, approved_plan_sha256=approved_plan_sha256)
            result["operation"] = "cleanup-runtime"
            return result
        cutoff = datetime.now(UTC) - ttl
        candidates: list[dict[str, Any]] = []
        for base_name in ("cache", "tmp", "tests"):
            base = self.root / "runtime" / base_name
            for item in _iter_entries(base):
                if item["kind"] != "file":
                    continue
                if Path(item["relative"]).parts[:1] == ("consumers",):
                    continue
                modified = datetime.fromtimestamp(item["mtime_ns"] / 1_000_000_000, tz=UTC)
                if modified <= cutoff:
                    candidate = dict(item)
                    candidate["relative"] = Path("runtime") / base_name / item["relative"]
                    candidates.append(candidate)
        candidates.sort(key=lambda item: (int(item["mtime_ns"]), str(item["relative"]).casefold()))
        selected: list[dict[str, Any]] = []
        selected_bytes = 0
        for item in candidates:
            if len(selected) >= max_entries:
                break
            size = int(item.get("size_bytes", 0))
            if selected and selected_bytes + size > max_bytes:
                break
            selected.append(item)
            selected_bytes += size
        entries = [
            {
                "path": Path(item["relative"]).as_posix(),
                "category": "temporary",
                "classification": "temporary",
                "reason": "bounded stale runtime candidate",
                "size_bytes": int(item["size_bytes"]),
                "disposition": "DELETE",
                "kind": "file",
                "fingerprint": {
                    "kind": "file",
                    "size_bytes": int(item["size_bytes"]),
                    "mtime_ns": int(item["mtime_ns"]),
                },
            }
            for item in selected
        ]
        plan = self._plan_from_entries("cleanup-runtime", entries)
        if not apply:
            return plan
        result = self.apply_plan(plan, approved_plan_sha256=approved_plan_sha256)
        result["operation"] = "cleanup-runtime"
        return result

    def _plan_from_entries(
        self, operation: str, entries: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        entries_list = [dict(entry) for entry in entries]
        body = {
            "schema_version": SCHEMA_VERSION,
            "operation": operation,
            "root": str(self.root),
            "generated_at": self.clock(),
            "entries": entries_list,
            "summary": ArtifactManager._summary(entries_list),
            "safety": {"issues": [], "worktrees": []},
        }
        body["plan_sha256"] = _hash_payload(body)
        return body


def _iter_files(root: Path) -> Iterable[Path]:
    for item in _iter_entries(root):
        if item["kind"] == "file":
            yield item["path"]


def _tree_file_bytes(root: Path) -> int:
    return sum(
        int(item.get("size_bytes", 0)) for item in _iter_entries(root) if item["kind"] == "file"
    )


def _path_is_under(path: Path, prefix: Path) -> bool:
    path_parts = tuple(path.parts)
    prefix_parts = tuple(prefix.parts)
    return path_parts[: len(prefix_parts)] == prefix_parts


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _parse_duration(value: str) -> timedelta:
    match = re.fullmatch(r"(?P<number>[0-9]+(?:\.[0-9]+)?)(?P<unit>[smhd])", value.strip().lower())
    if match is None:
        raise ArtifactError("Duration must look like 30m, 12h, 7d, or 60s")
    number = float(match.group("number"))
    unit = match.group("unit")
    seconds = number * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return timedelta(seconds=seconds)


def _human_result(payload: Mapping[str, Any]) -> str:
    lines = [
        f"operation: {payload.get('operation', 'unknown')}",
        f"root: {payload.get('root', '<not recorded>')}",
    ]
    for key in ("task_id", "path", "delivery_path"):
        if key in payload:
            lines.append(f"{key}: {payload[key]}")
    if payload.get("plan_sha256"):
        lines.append(f"plan_sha256: {payload['plan_sha256']}")
    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        counts = summary.get("counts", {})
        bytes_by = summary.get("bytes", {})
        for name in DISPOSITIONS:
            lines.append(f"{name}: {counts.get(name, 0)} files / {bytes_by.get(name, 0)} bytes")
    for key in (
        "status",
        "removed_count",
        "removed_reparse_count",
        "removed_bytes",
        "before_bytes",
        "after_bytes",
        "freed_bytes",
    ):
        if key in payload:
            lines.append(f"{key}: {payload[key]}")
    errors = payload.get("cleanup_errors")
    if errors:
        lines.append(f"cleanup_errors: {len(errors)}")
        for item in list(errors)[:20]:
            if isinstance(item, Mapping):
                lines.append(
                    f"- {item.get('path', '<unknown>')}: {item.get('reason', '<unknown>')}"
                )
    return "\n".join(lines)


def _write_output(
    manager: ArtifactManager, output: Path | None, payload: Mapping[str, Any]
) -> None:
    if output is None:
        return
    target = _safe_relative(manager.root, output)
    _atomic_write_json(target, payload)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1] / ".artifacts"
    )
    parser.add_argument("--repo-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("audit", "dry-run"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--json", action="store_true")
        subparser.add_argument("--output", type=Path)
        subparser.add_argument("--stale-runtime", action="store_true")
        subparser.add_argument("--runtime-ttl", default="7d")

    validate = subparsers.add_parser("validate")
    validate.add_argument("--task-id")
    validate.add_argument("--source-root", type=Path)
    validate.add_argument("--json", action="store_true")
    validate.add_argument("--output", type=Path)

    allocate = subparsers.add_parser("allocate")
    allocate.add_argument("task_id")
    allocate.add_argument("classification", choices=CLASSIFICATIONS)
    allocate.add_argument("relative_path")
    allocate.add_argument("--purpose", required=True)
    allocate.add_argument("--command", dest="provenance_command", required=True)
    allocate.add_argument("--owner", default="task-worker")
    allocate.add_argument("--directory", action="store_true")

    cleanup = subparsers.add_parser("cleanup-task")
    cleanup.add_argument("task_id")
    cleanup.add_argument("--terminal-state", required=True)
    cleanup.add_argument("--dry-run", action="store_true")
    cleanup.add_argument("--include", action="append", default=[])
    cleanup.add_argument("--exclude", action="append", default=[])
    cleanup.add_argument("--json", action="store_true")
    cleanup.add_argument("--output", type=Path)

    runtime = subparsers.add_parser("cleanup-runtime")
    runtime.add_argument("--ttl", default="7d")
    runtime.add_argument("--max-entries", type=int, default=1000)
    runtime.add_argument("--max-bytes", type=int, default=512 * 1024 * 1024)
    runtime.add_argument("--apply", action="store_true")
    runtime.add_argument("--plan", type=Path)
    runtime.add_argument("--approved-plan-sha256")
    runtime.add_argument("--json", action="store_true")
    runtime.add_argument("--output", type=Path)

    apply = subparsers.add_parser("apply-plan")
    apply.add_argument("plan", type=Path)
    apply.add_argument("--approved-plan-sha256", required=True)
    apply.add_argument("--json", action="store_true")
    apply.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manager = ArtifactManager(args.root, repo_root=args.repo_root)
    try:
        if args.command == "audit":
            payload = manager.audit(
                stale_runtime=args.stale_runtime,
                runtime_ttl=_parse_duration(args.runtime_ttl),
            )
        elif args.command == "dry-run":
            payload = manager.dry_run(
                stale_runtime=args.stale_runtime,
                runtime_ttl=_parse_duration(args.runtime_ttl),
            )
        elif args.command == "validate":
            payload = manager.validate(task_id=args.task_id, source_root=args.source_root)
        elif args.command == "allocate":
            if args.directory:
                target = manager.allocate_directory(
                    args.task_id,
                    args.classification,
                    args.relative_path,
                    purpose=args.purpose,
                    command=args.provenance_command,
                    owner=args.owner,
                )
            else:
                target = manager.allocate(
                    args.task_id,
                    args.classification,
                    args.relative_path,
                    purpose=args.purpose,
                    command=args.provenance_command,
                    owner=args.owner,
                )
            payload = {
                "operation": "allocate",
                "path": str(target),
                "task_id": normalize_task_id(args.task_id),
            }
        elif args.command == "cleanup-task":
            payload = manager.cleanup_task(
                args.task_id,
                terminal_state=args.terminal_state,
                apply=not args.dry_run,
                include_prefixes=args.include,
                exclude_prefixes=args.exclude,
            )
        elif args.command == "cleanup-runtime":
            runtime_plan = None
            if args.plan is not None:
                runtime_plan = _read_json(_resolved(args.plan))
                if not isinstance(runtime_plan, dict):
                    raise ArtifactError("Runtime cleanup plan must be a JSON object")
            payload = manager.cleanup_runtime(
                ttl=_parse_duration(args.ttl),
                max_entries=args.max_entries,
                max_bytes=args.max_bytes,
                apply=args.apply,
                approved_plan_sha256=args.approved_plan_sha256,
                plan=runtime_plan,
            )
        elif args.command == "apply-plan":
            plan = _read_json(_resolved(args.plan))
            if not isinstance(plan, dict):
                raise ArtifactError("Artifact plan must be a JSON object")
            payload = manager.apply_plan(plan, approved_plan_sha256=args.approved_plan_sha256)
        else:
            raise ArtifactError(f"Unknown artifact-manager command: {args.command}")
        _write_output(manager, getattr(args, "output", None), payload)
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(_human_result(payload))
        if payload.get("status") in {"blocked", "partial-failure"} or payload.get("ok") is False:
            return 1
        return 0
    except (ArtifactError, OSError) as error:
        print(f"artifact-manager: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
