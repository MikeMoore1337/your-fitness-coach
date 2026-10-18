from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from scripts import backup_manifest, db_maintenance


def test_manifest_is_format_verified_but_not_restore_verified(tmp_path: Path) -> None:
    archive = tmp_path / "fitminiapp-20261018T120000Z.dump"
    archive.write_bytes(b"synthetic-custom-format-dump")

    manifest = backup_manifest.build_manifest(
        archive,
        database_major="16",
        schema_revision="20261018_01",
        created_at=datetime(2026, 10, 18, 12, tzinfo=timezone.utc),  # noqa: UP017 - Python 3.10 support.
    )

    assert manifest["verification_status"] == "format_verified_pg_restore_list"
    assert manifest["restore_status"] == "not_run"
    assert backup_manifest.validate_manifest(manifest) == manifest

    restored = dict(manifest, restore_status="restore_verified")
    with pytest.raises(backup_manifest.BackupManifestError, match="restore_status"):
        backup_manifest.validate_manifest(restored)


def test_index_rejects_duplicate_archives() -> None:
    entry = {
        "manifest_name": "one.dump.manifest.json",
        "archive_name": "one.dump",
        "archive_size_bytes": 1,
        "archive_sha256": "0" * 64,
        "created_at_utc": "2026-10-18T12:00:00Z",
        "verification_status": "format_verified_pg_restore_list",
    }

    with pytest.raises(backup_manifest.BackupManifestError, match="duplicate"):
        backup_manifest.build_index([entry, entry])


def test_publish_rechecks_archive_and_writes_index_commit_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / ".artifacts"
    root = artifacts / "operations" / "backups" / "offhost"
    archive = root / "fitminiapp-20261018T120000Z.dump"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"synthetic-custom-format-dump")
    monkeypatch.setattr(db_maintenance, "ROOT", tmp_path)
    monkeypatch.setattr(db_maintenance, "ARTIFACTS", artifacts)
    monkeypatch.setattr(db_maintenance, "BACKUP_DIR", artifacts / "operations" / "backups")
    verified: list[Path] = []
    monkeypatch.setattr(db_maintenance, "_verify_archive", lambda path: verified.append(path))

    manifest_path, index_path, warnings = db_maintenance.publish_backup(
        archive,
        publish_dir=root,
        database_major="16",
        schema_revision="20261018_01",
    )

    assert manifest_path.is_file()
    assert index_path.is_file()
    assert warnings == ()
    assert verified == [archive]
    assert backup_manifest.read_index(index_path)["backups"][0]["archive_name"] == archive.name


def test_publish_refuses_to_rotate_when_existing_index_target_is_corrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / ".artifacts"
    root = artifacts / "operations" / "backups" / "offhost"
    old_archive = root / "fitminiapp-20261017T120000Z.dump"
    new_archive = root / "fitminiapp-20261018T120000Z.dump"
    root.mkdir(parents=True)
    old_archive.write_bytes(b"old")
    old_manifest = backup_manifest.build_manifest(
        old_archive,
        database_major="16",
        schema_revision="20261017_01",
    )
    backup_manifest.write_json_atomic(root / old_manifest["manifest_name"], old_manifest)
    backup_manifest.write_json_atomic(
        root / "index.json", backup_manifest.build_index([old_manifest])
    )
    before = (root / "index.json").read_bytes()
    old_archive.write_bytes(b"bad")
    new_archive.write_bytes(b"new")

    monkeypatch.setattr(db_maintenance, "ROOT", tmp_path)
    monkeypatch.setattr(db_maintenance, "ARTIFACTS", artifacts)
    monkeypatch.setattr(db_maintenance, "BACKUP_DIR", artifacts / "operations" / "backups")
    monkeypatch.setattr(db_maintenance, "_verify_archive", lambda path: None)

    with pytest.raises(backup_manifest.BackupManifestError, match="digest"):
        db_maintenance.publish_backup(
            new_archive,
            publish_dir=root,
            database_major="16",
            schema_revision="20261018_01",
        )

    assert (root / "index.json").read_bytes() == before
