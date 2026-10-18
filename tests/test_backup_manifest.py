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
        "published_at_utc": "2026-10-18T12:00:00Z",
        "verification_status": "format_verified_pg_restore_list",
    }

    with pytest.raises(backup_manifest.BackupManifestError, match="duplicate"):
        backup_manifest.build_index([entry, entry])


def test_manifest_and_index_reject_timestamps_beyond_fixed_clock_skew() -> None:
    now = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 support.
    archive = Path("synthetic.dump")
    manifest = {
        "schema_version": 1,
        "kind": "yfc-backup-manifest",
        "source": "vps",
        "archive_name": archive.name,
        "manifest_name": backup_manifest.manifest_name_for(archive.name),
        "archive_size_bytes": 1,
        "archive_sha256": "0" * 64,
        "created_at_utc": "2026-10-19T12:06:00Z",
        "published_at_utc": "2026-10-19T12:00:00Z",
        "database_major": "16",
        "schema_revision": "20261018_01",
        "verification_status": "format_verified_pg_restore_list",
        "restore_status": "not_run",
        "application_identity": {
            "status": "not_provided",
            "git_sha": "unknown",
            "backend_image_digest": "unknown",
            "bot_image_digest": "unknown",
        },
        "coverage": {"postgresql": "included"},
    }

    with pytest.raises(backup_manifest.BackupManifestError, match="too far in the future"):
        backup_manifest.validate_manifest(manifest, now=now)

    future_published = dict(
        manifest,
        created_at_utc="2026-10-19T12:00:00Z",
        published_at_utc="2026-10-19T12:06:00Z",
    )
    with pytest.raises(backup_manifest.BackupManifestError, match="too far in the future"):
        backup_manifest.validate_manifest(future_published, now=now)

    within_tolerance = dict(
        manifest,
        created_at_utc="2026-10-19T12:05:00Z",
        published_at_utc="2026-10-19T12:05:00Z",
    )
    assert backup_manifest.validate_manifest(within_tolerance, now=now) == within_tolerance

    entry = backup_manifest.index_entry(within_tolerance, now=now)
    future_entry = dict(entry, published_at_utc="2026-10-19T12:06:00Z")
    future_index = {
        "schema_version": 1,
        "kind": "yfc-backup-index",
        "generated_at_utc": "2026-10-19T12:00:00Z",
        "backups": [future_entry],
    }
    with pytest.raises(backup_manifest.BackupManifestError, match="too far in the future"):
        backup_manifest.validate_index(future_index, now=now)


def test_index_validation_rejects_duplicate_or_unsafe_entries() -> None:
    entry = {
        "manifest_name": "one.dump.manifest.json",
        "archive_name": "one.dump",
        "archive_size_bytes": 1,
        "archive_sha256": "0" * 64,
        "created_at_utc": "2026-10-18T12:00:00Z",
        "published_at_utc": "2026-10-18T12:00:00Z",
        "verification_status": "format_verified_pg_restore_list",
    }
    index = {
        "schema_version": 1,
        "kind": "yfc-backup-index",
        "generated_at_utc": "2026-10-18T12:00:00Z",
        "backups": [entry, entry],
    }

    with pytest.raises(backup_manifest.BackupManifestError, match="duplicate"):
        backup_manifest.validate_index(index)

    with pytest.raises(backup_manifest.BackupManifestError, match="safe file name"):
        backup_manifest.validate_index(
            {**index, "backups": [{**entry, "archive_name": "../outside.dump"}]}
        )


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
    published_entry = backup_manifest.read_index(index_path)["backups"][0]
    assert published_entry["archive_name"] == archive.name
    assert published_entry["published_at_utc"]


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


def test_publish_keeps_retained_copies_when_rotation_is_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / ".artifacts"
    root = artifacts / "operations" / "backups" / "offhost"
    root.mkdir(parents=True)

    def write_existing(name: str, content: bytes, created_at: datetime) -> dict[str, object]:
        archive = root / name
        archive.write_bytes(content)
        manifest = backup_manifest.build_manifest(
            archive,
            database_major="16",
            schema_revision="20261018_01",
            created_at=created_at,
            published_at=created_at,
        )
        backup_manifest.write_json_atomic(root / manifest["manifest_name"], manifest)
        return manifest

    oldest = write_existing(
        "fitminiapp-20261016T120000Z.dump",
        b"oldest",
        datetime(2026, 10, 16, 12, tzinfo=timezone.utc),  # noqa: UP017 - Python 3.10 support.
    )
    retained = write_existing(
        "fitminiapp-20261017T120000Z.dump",
        b"retained",
        datetime(2026, 10, 17, 12, tzinfo=timezone.utc),  # noqa: UP017 - Python 3.10 support.
    )
    backup_manifest.write_json_atomic(
        root / "index.json", backup_manifest.build_index([oldest, retained])
    )
    new_archive = root / "fitminiapp-20261018T120000Z.dump"
    new_archive.write_bytes(b"new")

    monkeypatch.setattr(db_maintenance, "ROOT", tmp_path)
    monkeypatch.setattr(db_maintenance, "ARTIFACTS", artifacts)
    monkeypatch.setattr(db_maintenance, "BACKUP_DIR", artifacts / "operations" / "backups")
    monkeypatch.setattr(db_maintenance, "_verify_archive", lambda path: None)
    original_unlink = Path.unlink

    def fail_oldest_archive(self: Path, *args: object, **kwargs: object) -> None:
        if self == root / oldest["archive_name"]:
            raise OSError("synthetic rotation failure")
        original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_oldest_archive)

    _, index_path, warnings = db_maintenance.publish_backup(
        new_archive,
        publish_dir=root,
        database_major="16",
        schema_revision="20261018_01",
        created_at=datetime(2026, 10, 18, 12, tzinfo=timezone.utc),  # noqa: UP017 - Python 3.10 support.
        retain=2,
    )

    assert warnings == ("rotation could not remove fitminiapp-20261016T120000Z.dump",)
    assert {
        entry["archive_name"] for entry in backup_manifest.read_index(index_path)["backups"]
    } == {new_archive.name, retained["archive_name"]}
    assert new_archive.is_file()
    assert (root / retained["archive_name"]).is_file()
    assert (
        root / oldest["archive_name"]
    ).is_file()  # orphan is preserved, not mistaken for a verified entry.
    assert not (root / oldest["manifest_name"]).exists()
