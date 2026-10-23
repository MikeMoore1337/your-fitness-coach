"""Create and restore PostgreSQL dumps through the Compose db service.

All dump files are intentionally restricted to .artifacts/operations/backups so
operational data cannot accidentally become a tracked repository file or a
generic runtime-cleanup candidate.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows developer hosts do not publish VPS backups.
    fcntl = None

try:
    from scripts.backup_manifest import (
        BackupManifestError,
        build_index,
        build_manifest,
        create_tar_archive,
        format_utc,
        index_entry,
        manifest_name_for,
        parse_utc,
        read_index,
        read_manifest,
        sha256_file,
        validate_tar_archive,
        write_json_atomic,
    )
except ModuleNotFoundError:  # direct `python scripts/db_maintenance.py` invocation
    from backup_manifest import (
        BackupManifestError,
        build_index,
        build_manifest,
        create_tar_archive,
        format_utc,
        index_entry,
        manifest_name_for,
        parse_utc,
        read_index,
        read_manifest,
        sha256_file,
        validate_tar_archive,
        write_json_atomic,
    )

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = Path(os.environ.get("DEPLOY_ARTIFACT_ROOT", str(ROOT / ".artifacts"))).resolve()
BACKUP_DIR = ARTIFACTS / "operations" / "backups"
UTC = timezone.utc  # noqa: UP017 - deployment hosts can still run Python 3.10.
BACKUP_SCRIPT = (
    "exec pg_dump --format=custom --no-owner --no-privileges "
    '--dbname="$POSTGRES_DB" --username="$POSTGRES_USER"'
)
RESTORE_SCRIPT = (
    "exec pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error "
    "--single-transaction "
    '--dbname="$POSTGRES_DB" --username="$POSTGRES_USER"'
)
VERIFY_DUMP_SCRIPT = "exec pg_restore --list"
DATABASE_MAJOR_SCRIPT = (
    "exec psql --tuples-only --no-align "
    '--dbname="$POSTGRES_DB" --username="$POSTGRES_USER" '
    "--command 'SHOW server_version_num'"
)
SCHEMA_REVISION_SCRIPT = (
    "exec psql --tuples-only --no-align "
    '--dbname="$POSTGRES_DB" --username="$POSTGRES_USER" '
    "--command 'SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1'"
)


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _artifact_path(path: Path) -> Path:
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    backup_dir = BACKUP_DIR.resolve()
    if not resolved.is_relative_to(backup_dir):
        raise ValueError(f"backup paths must stay below {backup_dir}")
    return resolved


def _compose_exec(script: str) -> list[str]:
    return ["docker", "compose", "exec", "-T", "db", "sh", "-ec", script]


def _database_name() -> str:
    result = subprocess.run(
        _compose_exec('printf "%s" "$POSTGRES_DB"'),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    name = result.stdout.strip()
    if not name:
        raise RuntimeError("POSTGRES_DB is empty inside the db service")
    return name


def _compose_query(script: str) -> str:
    result = subprocess.run(
        _compose_exec(script),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")


def _database_major() -> str:
    raw = _compose_query(DATABASE_MAJOR_SCRIPT)
    try:
        return str(int(raw) // 10_000)
    except ValueError as exc:
        raise RuntimeError("could not determine PostgreSQL major version") from exc


def _schema_revision() -> str:
    revision = _compose_query(SCHEMA_REVISION_SCRIPT)
    if not revision:
        raise RuntimeError("could not determine Alembic schema revision")
    return revision


def create_backup(output: Path) -> Path:
    target = _artifact_path(output)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing backup: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")

    try:
        with partial.open("xb") as stream:
            process = subprocess.run(
                _compose_exec(BACKUP_SCRIPT),
                cwd=ROOT,
                check=False,
                stdout=stream,
                stderr=subprocess.PIPE,
            )
        if process.returncode != 0:
            sys.stderr.buffer.write(process.stderr)
            raise RuntimeError(f"pg_dump failed with exit code {process.returncode}")

        with partial.open("rb") as stream:
            verification = subprocess.run(
                _compose_exec(VERIFY_DUMP_SCRIPT),
                cwd=ROOT,
                check=False,
                stdin=stream,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        if verification.returncode != 0:
            sys.stderr.buffer.write(verification.stderr)
            raise RuntimeError("pg_restore could not read the new backup; refusing to accept it")
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return target


def _verify_archive(archive: Path) -> None:
    """Verify the archive format immediately before it becomes publishable."""

    with archive.open("rb") as stream:
        verification = subprocess.run(
            _compose_exec(VERIFY_DUMP_SCRIPT),
            cwd=ROOT,
            check=False,
            stdin=stream,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    if verification.returncode != 0:
        raise RuntimeError("pg_restore could not read the archive; refusing to publish it")


@contextmanager
def _publisher_lock(root: Path) -> Iterator[None]:
    """Serialize manifest/index publication on the Linux VPS."""

    lock_path = root / ".publish.lock"
    root.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        if fcntl is not None:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("backup publication is already running") from exc
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _validate_published_entry(root: Path, entry: dict[str, object]) -> None:
    """Recheck the actual archive and sidecar before using an index entry."""

    archive = root / str(entry["archive_name"])
    manifest_path = root / str(entry["manifest_name"])
    if not archive.is_file() or not manifest_path.is_file():
        raise BackupManifestError("published index points to a missing archive or manifest")
    manifest = read_manifest(manifest_path)
    if index_entry(manifest) != entry:
        raise BackupManifestError("published index does not match its manifest")
    if manifest["archive_size_bytes"] != archive.stat().st_size:
        raise BackupManifestError("published archive size does not match its manifest")
    if manifest["archive_sha256"] != sha256_file(archive):
        raise BackupManifestError("published archive digest does not match its manifest")
    validate_tar_archive(archive)


def publish_backup(
    archive: Path,
    *,
    publish_dir: Path,
    database_major: str,
    schema_revision: str,
    created_at: datetime | None = None,
    retain: int = 7,
) -> tuple[Path, Path, tuple[str, ...]]:
    """Publish one verified archive and its index, with rotation after commit."""

    if retain < 1:
        raise ValueError("retention days must be positive")
    root = _artifact_path(publish_dir)
    if root == BACKUP_DIR or not root.is_relative_to(BACKUP_DIR):
        raise ValueError("publish directory must be a child of the backup directory")
    source = _artifact_path(archive)
    if source.is_relative_to(root) or root.is_relative_to(source.parent):
        raise ValueError("plaintext staging must be separate from the SFTP publish directory")
    if source.suffix != ".dump" or not source.is_file():
        raise ValueError("publication requires an existing private .dump")
    created_at = created_at or datetime.now(UTC)
    date = created_at.astimezone(timezone(timedelta(hours=3))).strftime("%Y-%m-%d")
    target = root / f"backup-{date}.tar.gz"

    with _publisher_lock(root):
        # Legacy exports require an explicit migration, never an automatic downgrade or deletion.
        if any(
            path.name not in {"index.json", ".publish.lock"}
            and not path.name.endswith((".tar.gz", ".tar.gz.manifest.json"))
            for path in root.iterdir()
        ):
            raise ValueError(
                "publish directory contains legacy or unexpected files; migrate it first"
            )
        index_path = root / "index.json"
        current_entries: list[dict[str, object]] = []
        if index_path.exists():
            current_entries = list(read_index(index_path)["backups"])
            for entry in current_entries:
                _validate_published_entry(root, entry)
        if target.exists():
            raise FileExistsError("refusing to overwrite published archive")
        _verify_archive(source)
        with tempfile.TemporaryDirectory(prefix=".tar-", dir=BACKUP_DIR) as staging:
            packed = Path(staging) / target.name
            create_tar_archive(
                source,
                packed,
                {
                    "schema_version": 1,
                    "database_major": database_major,
                    "schema_revision": schema_revision,
                    "created_at_utc": format_utc(created_at),
                },
            )
            manifest = build_manifest(
                packed,
                database_major=database_major,
                schema_revision=schema_revision,
                created_at=created_at,
            )
            packed.replace(target)
        manifest_path = root / manifest_name_for(target.name)
        write_json_atomic(manifest_path, manifest, group_readable=True)
        current_entries = [
            entry for entry in current_entries if entry["archive_name"] != target.name
        ]
        current_entries.append(index_entry(manifest))
        ordered = build_index(current_entries)["backups"]
        cutoff = datetime.now(UTC) - timedelta(days=retain)
        retained_entries = [
            entry
            for position, entry in enumerate(ordered)
            if position < 2 or parse_utc(entry["created_at_utc"], field="created_at_utc") >= cutoff
        ]
        # index.json is the commit marker: it is replaced only after all metadata is complete.
        write_json_atomic(index_path, build_index(retained_entries), group_readable=True)

        warnings: list[str] = []
        retained_names = {str(entry["archive_name"]) for entry in retained_entries}
        for entry in current_entries:
            archive_name = str(entry["archive_name"])
            if archive_name in retained_names:
                continue
            old_archive = root / archive_name
            old_manifest = root / str(entry["manifest_name"])
            for candidate in (old_archive, old_manifest):
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    warnings.append(f"rotation could not remove {candidate.name}")
        return manifest_path, index_path, tuple(warnings)


def create_published_backup(
    output: Path,
    *,
    publish_dir: Path,
    database_major: str,
    schema_revision: str,
    retain: int = 7,
) -> tuple[Path, Path, Path, tuple[str, ...]]:
    root = _artifact_path(publish_dir)
    target = _artifact_path(output)
    created_at = datetime.now(UTC)
    date = created_at.astimezone(timezone(timedelta(hours=3))).strftime("%Y-%m-%d")
    if target.parent != root or target.name != f"backup-{date}.tar.gz":
        raise ValueError("published archive must be directly below the publish directory")
    if target.exists():
        raise FileExistsError("daily backup already exists; refusing to overwrite")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dump-", dir=BACKUP_DIR) as staging:
        archive = create_backup(Path(staging) / "database.dump")
        manifest, index, warnings = publish_backup(
            archive,
            publish_dir=root,
            database_major=database_major,
            schema_revision=schema_revision,
            created_at=created_at,
            retain=retain,
        )
    return target, manifest, index, warnings


def restore_backup(source: Path, *, confirmed_database: str) -> tuple[Path, str]:
    dump = _artifact_path(source)
    if not dump.is_file():
        raise FileNotFoundError(f"backup does not exist: {dump}")

    actual_database = _database_name()
    if confirmed_database != actual_database:
        raise ValueError(
            "restore confirmation does not match POSTGRES_DB: "
            f"expected --confirm-database {actual_database!r}"
        )

    safety_backup = create_backup(BACKUP_DIR / f"pre-restore-{_timestamp()}.dump")
    with dump.open("rb") as stream:
        process = subprocess.run(
            _compose_exec(RESTORE_SCRIPT),
            cwd=ROOT,
            check=False,
            stdin=stream,
            stderr=subprocess.PIPE,
        )
    if process.returncode != 0:
        sys.stderr.buffer.write(process.stderr)
        raise RuntimeError(
            "pg_restore failed; writers must remain stopped. "
            f"The automatic safety backup is {safety_backup}"
        )
    return safety_backup, actual_database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="create a custom-format pg_dump")
    backup_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="path below .artifacts/operations/backups (default: timestamped backup file)",
    )
    backup_parser.add_argument(
        "--publish-dir",
        type=Path,
        default=None,
        help="publish a verified archive, manifest and index below this backup child directory",
    )
    backup_parser.add_argument(
        "--database-major",
        default=None,
        help="PostgreSQL major version for published metadata (queried when omitted)",
    )
    backup_parser.add_argument(
        "--schema-revision",
        default=None,
        help="Alembic revision for published metadata (queried when omitted)",
    )
    backup_parser.add_argument(
        "--retain-published",
        type=int,
        default=7,
        help="retention in days; always preserve the newest two verified archives",
    )

    restore_parser = subparsers.add_parser(
        "restore",
        help="restore a custom-format dump after creating a safety backup",
    )
    restore_parser.add_argument(
        "input", type=Path, help="dump file below .artifacts/operations/backups/"
    )
    restore_parser.add_argument(
        "--confirm-database",
        required=True,
        help="must exactly match POSTGRES_DB inside the running db service",
    )

    args = parser.parse_args()
    try:
        if args.command == "backup":
            if args.publish_dir is None:
                output = args.output or BACKUP_DIR / f"fitminiapp-{_timestamp()}.dump"
                created = create_backup(output)
                print(f"Backup created: {created}")
                return 0
            publish_dir = _artifact_path(args.publish_dir)
            date = datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d")
            output = args.output or publish_dir / f"backup-{date}.tar.gz"
            database_major = args.database_major or _database_major()
            schema_revision = args.schema_revision or _schema_revision()
            created, manifest, index, warnings = create_published_backup(
                output,
                publish_dir=publish_dir,
                database_major=database_major,
                schema_revision=schema_revision,
                retain=args.retain_published,
            )
            print(f"Backup created: {created}")
            print(f"Backup manifest: {manifest}")
            print(f"Backup index: {index}")
            for warning in warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
            return 2 if warnings else 0

        safety_backup, database = restore_backup(
            args.input,
            confirmed_database=args.confirm_database,
        )
        print(f"Database restored: {database}")
        print(f"Pre-restore safety backup: {safety_backup}")
        return 0
    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        ValueError,
        BackupManifestError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
