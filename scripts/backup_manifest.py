"""Provider-neutral metadata for verified YFC backup archives.

The manifest contains only operational metadata.  It never contains database
contents, credentials, private keys, or user records.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_KIND = "yfc-backup-manifest"
INDEX_KIND = "yfc-backup-index"
INDEX_FILENAME = "index.json"
FORMAT_VERIFIED_STATUS = "format_verified_pg_restore_list"
CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATABASE_MAJOR = re.compile(r"^[0-9]{1,3}$")
_SCHEMA_REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# This is an explicit coverage contract, not a claim that every listed volume
# is currently backed up.  The runbook explains the required reconstruction or
# owner gate for each non-database item.
PERSISTENT_STATE_COVERAGE: dict[str, Any] = {
    "postgresql": "included",
    "postgresql_binary_columns": "included",
    "versioned_application_files": "reconstructed_from_git_and_immutable_image",
    "named_volumes": {
        "postgres_data": "included_by_postgresql_dump_not_volume_copy",
        "caddy_data": "reissued_or_rebuilt",
        "caddy_config": "reconstructed_from_compose_and_environment",
        "edge_config": "reconstructed_from_release_and_environment",
        "bot_polling_lock": "ephemeral_recreated_on_start",
    },
    "secrets_and_private_keys": "excluded_restore_separately",
    "untracked_host_mounts": "owner_inventory_required_before_phase_b",
}


class BackupManifestError(ValueError):
    """The backup metadata cannot be trusted or used safely."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 - deployment hosts can still run Python 3.10.


def format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise BackupManifestError("timestamp must include a timezone")
    return (
        value.astimezone(timezone.utc)  # noqa: UP017 - deployment hosts can still run Python 3.10.
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def parse_utc(
    value: object,
    *,
    field: str,
    now: datetime | None = None,
) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise BackupManifestError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BackupManifestError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise BackupManifestError(f"{field} must include a timezone")
    parsed_utc = parsed.astimezone(timezone.utc)  # noqa: UP017 - deployment hosts can still run Python 3.10.
    if now is not None:
        reference = now.astimezone(timezone.utc)  # noqa: UP017 - deployment hosts can still run Python 3.10.
        if parsed_utc > reference + CLOCK_SKEW_TOLERANCE:
            raise BackupManifestError(
                f"{field} is too far in the future; clock skew tolerance is "
                f"{int(CLOCK_SKEW_TOLERANCE.total_seconds())} seconds"
            )
    return parsed_utc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_name_for(archive_name: str) -> str:
    _require_filename(archive_name, field="archive_name")
    return f"{archive_name}.manifest.json"


def _require_filename(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_FILENAME.fullmatch(value):
        raise BackupManifestError(f"{field} must be a safe file name")
    return value


def _require_hash(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise BackupManifestError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _require_database_major(value: object) -> str:
    if not isinstance(value, str) or not _DATABASE_MAJOR.fullmatch(value.strip()):
        raise BackupManifestError("database_major must be a numeric major version")
    return value.strip()


def _require_schema_revision(value: object) -> str:
    if not isinstance(value, str) or not _SCHEMA_REVISION.fullmatch(value.strip()):
        raise BackupManifestError("schema_revision must be a safe non-empty revision")
    return value.strip()


def _application_identity() -> dict[str, str]:
    git_sha = os.environ.get("YFC_RELEASE_SHA", "unknown").strip() or "unknown"
    backend_digest = os.environ.get("YFC_BACKEND_IMAGE_DIGEST", "unknown").strip() or "unknown"
    bot_digest = os.environ.get("YFC_BOT_IMAGE_DIGEST", "unknown").strip() or "unknown"
    supplied = all(value != "unknown" for value in (git_sha, backend_digest, bot_digest))
    return {
        "status": "provided" if supplied else "not_provided",
        "git_sha": git_sha,
        "backend_image_digest": backend_digest,
        "bot_image_digest": bot_digest,
    }


def build_manifest(
    archive: Path,
    *,
    database_major: str,
    schema_revision: str,
    created_at: datetime | None = None,
    published_at: datetime | None = None,
) -> dict[str, Any]:
    archive = archive.resolve()
    if not archive.is_file():
        raise BackupManifestError(f"backup archive does not exist: {archive}")
    size = archive.stat().st_size
    if size <= 0:
        raise BackupManifestError("backup archive must not be empty")
    reference = utc_now()
    created = created_at or reference
    published = published_at or reference
    created_text = format_utc(created)
    published_text = format_utc(published)
    parse_utc(created_text, field="created_at_utc", now=reference)
    parse_utc(published_text, field="published_at_utc", now=reference)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "source": "vps",
        "archive_name": _require_filename(archive.name, field="archive_name"),
        "manifest_name": manifest_name_for(archive.name),
        "archive_size_bytes": size,
        "archive_sha256": sha256_file(archive),
        "created_at_utc": created_text,
        "published_at_utc": published_text,
        "database_major": _require_database_major(database_major),
        "schema_revision": _require_schema_revision(schema_revision),
        "verification_status": FORMAT_VERIFIED_STATUS,
        "restore_status": "not_run",
        "application_identity": _application_identity(),
        "coverage": deepcopy(PERSISTENT_STATE_COVERAGE),
    }


def _as_object(value: object, *, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BackupManifestError(f"{description} must be an object")
    return value


def validate_manifest(value: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    manifest = dict(value)
    reference = now or utc_now()
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise BackupManifestError("unsupported backup manifest schema")
    if manifest.get("kind") != MANIFEST_KIND:
        raise BackupManifestError("unexpected backup manifest kind")
    if manifest.get("source") != "vps":
        raise BackupManifestError("backup manifest source must be vps")
    archive_name = _require_filename(manifest.get("archive_name"), field="archive_name")
    if manifest.get("manifest_name") != manifest_name_for(archive_name):
        raise BackupManifestError("manifest_name does not match archive_name")
    size = manifest.get("archive_size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise BackupManifestError("archive_size_bytes must be a positive integer")
    _require_hash(manifest.get("archive_sha256"), field="archive_sha256")
    parse_utc(manifest.get("created_at_utc"), field="created_at_utc", now=reference)
    parse_utc(manifest.get("published_at_utc"), field="published_at_utc", now=reference)
    _require_database_major(manifest.get("database_major"))
    _require_schema_revision(manifest.get("schema_revision"))
    if manifest.get("verification_status") != FORMAT_VERIFIED_STATUS:
        raise BackupManifestError("backup is not marked as format-verified by pg_restore --list")
    if manifest.get("restore_status") != "not_run":
        raise BackupManifestError("restore_status must remain not_run until Phase C")
    identity = _as_object(manifest.get("application_identity"), description="application_identity")
    if identity.get("status") not in {"provided", "not_provided"}:
        raise BackupManifestError("application_identity status is invalid")
    for key in ("git_sha", "backend_image_digest", "bot_image_digest"):
        if not isinstance(identity.get(key), str) or not identity[key].strip():
            raise BackupManifestError(f"application_identity.{key} is required")
    _as_object(manifest.get("coverage"), description="coverage")
    return manifest


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackupManifestError(f"cannot read backup metadata: {path.name}") from exc
    return _as_object(value, description=path.name)


def read_manifest(path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    return validate_manifest(read_json(path), now=now)


def index_entry(manifest: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    checked = validate_manifest(manifest, now=now)
    return {
        key: checked[key]
        for key in (
            "manifest_name",
            "archive_name",
            "archive_size_bytes",
            "archive_sha256",
            "created_at_utc",
            "published_at_utc",
            "verification_status",
        )
    }


def _validate_index_entry(
    value: Mapping[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    entry = dict(value)
    _require_filename(entry.get("manifest_name"), field="manifest_name")
    archive_name = _require_filename(entry.get("archive_name"), field="archive_name")
    if entry.get("manifest_name") != manifest_name_for(archive_name):
        raise BackupManifestError("index manifest_name does not match archive_name")
    size = entry.get("archive_size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise BackupManifestError("index archive_size_bytes must be a positive integer")
    _require_hash(entry.get("archive_sha256"), field="archive_sha256")
    reference = now or utc_now()
    parse_utc(entry.get("created_at_utc"), field="created_at_utc", now=reference)
    parse_utc(entry.get("published_at_utc"), field="published_at_utc", now=reference)
    if entry.get("verification_status") != FORMAT_VERIFIED_STATUS:
        raise BackupManifestError("index contains an unverified backup")
    return entry


def build_index(
    entries: list[Mapping[str, Any]],
    *,
    generated_at: datetime | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    reference = now or utc_now()
    normalized = [
        index_entry(entry, now=reference)
        if entry.get("kind") == MANIFEST_KIND
        else _validate_index_entry(entry, now=reference)
        for entry in entries
    ]
    normalized.sort(
        key=lambda item: parse_utc(item["created_at_utc"], field="created_at_utc"), reverse=True
    )
    names = [item["archive_name"] for item in normalized]
    if len(names) != len(set(names)):
        raise BackupManifestError("backup index contains duplicate archive names")
    generated_text = format_utc(generated_at or reference)
    parse_utc(generated_text, field="generated_at_utc", now=reference)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": INDEX_KIND,
        "generated_at_utc": generated_text,
        "backups": normalized,
    }


def validate_index(value: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    index = dict(value)
    reference = now or utc_now()
    if index.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise BackupManifestError("unsupported backup index schema")
    if index.get("kind") != INDEX_KIND:
        raise BackupManifestError("unexpected backup index kind")
    parse_utc(index.get("generated_at_utc"), field="generated_at_utc", now=reference)
    backups = index.get("backups")
    if not isinstance(backups, list) or len(backups) > 10_000:
        raise BackupManifestError("backups must be a bounded list")
    names: list[str] = []
    for entry in backups:
        checked = _validate_index_entry(entry, now=reference)
        names.append(str(checked["archive_name"]))
    if len(names) != len(set(names)):
        raise BackupManifestError("backup index contains duplicate archive names")
    return index


def read_index(path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    return validate_index(read_json(path), now=now)


def write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".partial",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
