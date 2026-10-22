from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from scripts import backup_manifest, db_maintenance

RECIPIENT = "age1" + "q" * 58
HEADER = backup_manifest.AGE_HEADER
AGE_PATH = Path("/synthetic/age")


def test_manifest_is_format_verified_but_not_restore_verified(tmp_path: Path) -> None:
    archive = tmp_path / "fitminiapp-20261018T120000Z.dump.age"
    archive.write_bytes(HEADER + b"synthetic-ciphertext")

    manifest = backup_manifest.build_manifest(
        archive,
        database_major="16",
        schema_revision="20261018_01",
        recipient=RECIPIENT,
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
        "manifest_name": "one.dump.age.manifest.json",
        "archive_name": "one.dump.age",
        "archive_size_bytes": 1,
        "archive_sha256": "0" * 64,
        "created_at_utc": "2026-10-18T12:00:00Z",
        "published_at_utc": "2026-10-18T12:00:00Z",
        "verification_status": "format_verified_pg_restore_list",
        "archive_format": "age-v1",
        "age_version": "v1.3.2",
        "recipient": RECIPIENT,
    }

    with pytest.raises(backup_manifest.BackupManifestError, match="duplicate"):
        backup_manifest.build_index([entry, entry])


def test_manifest_and_index_reject_timestamps_beyond_fixed_clock_skew() -> None:
    now = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 support.
    archive = Path("synthetic.dump.age")
    manifest = {
        "schema_version": 2,
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
        "archive_format": "age-v1",
        "age_version": "v1.3.2",
        "recipient": RECIPIENT,
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
        "schema_version": 2,
        "kind": "yfc-backup-index",
        "generated_at_utc": "2026-10-19T12:00:00Z",
        "backups": [future_entry],
    }
    with pytest.raises(backup_manifest.BackupManifestError, match="too far in the future"):
        backup_manifest.validate_index(future_index, now=now)


def test_index_validation_rejects_duplicate_or_unsafe_entries() -> None:
    entry = {
        "manifest_name": "one.dump.age.manifest.json",
        "archive_name": "one.dump.age",
        "archive_size_bytes": 1,
        "archive_sha256": "0" * 64,
        "created_at_utc": "2026-10-18T12:00:00Z",
        "published_at_utc": "2026-10-18T12:00:00Z",
        "verification_status": "format_verified_pg_restore_list",
        "archive_format": "age-v1",
        "age_version": "v1.3.2",
        "recipient": RECIPIENT,
    }
    index = {
        "schema_version": 2,
        "kind": "yfc-backup-index",
        "generated_at_utc": "2026-10-18T12:00:00Z",
        "backups": [entry, entry],
    }

    with pytest.raises(backup_manifest.BackupManifestError, match="duplicate"):
        backup_manifest.validate_index(index)

    with pytest.raises(backup_manifest.BackupManifestError, match="safe file name"):
        backup_manifest.validate_index(
            {**index, "backups": [{**entry, "archive_name": "../outside.dump.age"}]}
        )


def test_publish_rechecks_archive_and_writes_index_commit_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / ".artifacts"
    root = artifacts / "operations" / "backups" / "offhost"
    archive = root.parent / "private" / "fitminiapp-20261018T120000Z.dump"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(HEADER + b"synthetic-ciphertext")
    monkeypatch.setattr(db_maintenance, "ROOT", tmp_path)
    monkeypatch.setattr(db_maintenance, "ARTIFACTS", artifacts)
    monkeypatch.setattr(db_maintenance, "BACKUP_DIR", artifacts / "operations" / "backups")
    verified: list[Path] = []
    monkeypatch.setattr(db_maintenance, "_verify_archive", lambda path: verified.append(path))

    root.mkdir(exist_ok=True)
    manifest_path, index_path, warnings = db_maintenance.publish_backup(
        archive,
        publish_dir=root,
        age_path=AGE_PATH,
        database_major="16",
        schema_revision="20261018_01",
        recipient=RECIPIENT,
    )

    assert manifest_path.is_file()
    assert index_path.is_file()
    assert warnings == ()
    assert verified == [archive]
    published_entry = backup_manifest.read_index(index_path)["backups"][0]
    assert published_entry["archive_name"] == archive.name + ".age"
    assert published_entry["published_at_utc"]


def test_publish_refuses_to_rotate_when_existing_index_target_is_corrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / ".artifacts"
    root = artifacts / "operations" / "backups" / "offhost"
    old_archive = root / "fitminiapp-20261017T120000Z.dump.age"
    new_archive = root.parent / "private" / "fitminiapp-20261018T120000Z.dump"
    root.mkdir(parents=True)
    old_archive.write_bytes(HEADER + b"old")
    old_manifest = backup_manifest.build_manifest(
        old_archive,
        database_major="16",
        schema_revision="20261017_01",
        recipient=RECIPIENT,
    )
    backup_manifest.write_json_atomic(root / old_manifest["manifest_name"], old_manifest)
    backup_manifest.write_json_atomic(
        root / "index.json", backup_manifest.build_index([old_manifest])
    )
    before = (root / "index.json").read_bytes()
    old_archive.write_bytes(HEADER + b"bad")
    new_archive.parent.mkdir(exist_ok=True)
    new_archive.write_bytes(b"new")

    monkeypatch.setattr(db_maintenance, "ROOT", tmp_path)
    monkeypatch.setattr(db_maintenance, "ARTIFACTS", artifacts)
    monkeypatch.setattr(db_maintenance, "BACKUP_DIR", artifacts / "operations" / "backups")
    monkeypatch.setattr(db_maintenance, "_verify_archive", lambda path: None)

    with pytest.raises(backup_manifest.BackupManifestError, match="digest"):
        db_maintenance.publish_backup(
            new_archive,
            publish_dir=root,
            age_path=AGE_PATH,
            database_major="16",
            schema_revision="20261018_01",
            recipient=RECIPIENT,
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
        archive.write_bytes(HEADER + content)
        manifest = backup_manifest.build_manifest(
            archive,
            database_major="16",
            schema_revision="20261018_01",
            recipient=RECIPIENT,
            created_at=created_at,
            published_at=created_at,
        )
        backup_manifest.write_json_atomic(root / manifest["manifest_name"], manifest)
        return manifest

    oldest = write_existing(
        "fitminiapp-20261016T120000Z.dump.age",
        b"oldest",
        datetime(2026, 10, 16, 12, tzinfo=timezone.utc),  # noqa: UP017 - Python 3.10 support.
    )
    retained = write_existing(
        "fitminiapp-20261017T120000Z.dump.age",
        b"retained",
        datetime(2026, 10, 17, 12, tzinfo=timezone.utc),  # noqa: UP017 - Python 3.10 support.
    )
    backup_manifest.write_json_atomic(
        root / "index.json", backup_manifest.build_index([oldest, retained])
    )
    new_archive = root.parent / "private" / "fitminiapp-20261018T120000Z.dump"
    new_archive.parent.mkdir(exist_ok=True)
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
        age_path=AGE_PATH,
        database_major="16",
        schema_revision="20261018_01",
        recipient=RECIPIENT,
        created_at=datetime(2026, 10, 18, 12, tzinfo=timezone.utc),  # noqa: UP017 - Python 3.10 support.
        retain=2,
    )

    assert warnings == ("rotation could not remove fitminiapp-20261016T120000Z.dump.age",)
    assert {
        entry["archive_name"] for entry in backup_manifest.read_index(index_path)["backups"]
    } == {new_archive.name + ".age", retained["archive_name"]}
    assert (root / (new_archive.name + ".age")).is_file()
    assert (root / retained["archive_name"]).is_file()
    assert (
        root / oldest["archive_name"]
    ).is_file()  # orphan is preserved, not mistaken for a verified entry.
    assert not (root / oldest["manifest_name"]).exists()


@pytest.fixture(autouse=True)
def synthetic_encrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    def encrypt(source: Path, output: Path, **kwargs: object) -> None:
        output.write_bytes(HEADER + source.read_bytes())

    monkeypatch.setattr(db_maintenance, "_encrypt_archive", encrypt)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 1),
        ("schema_version", "2"),
        ("schema_version", 2.0),
        ("schema_version", True),
        ("archive_format", "pg-custom"),
        ("age_version", "v1.2.1"),
        ("recipient", "AGE-SECRET-KEY-private"),
        ("archive_name", "plaintext.dump"),
        ("archive_size_bytes", "200"),
        ("archive_size_bytes", True),
        ("archive_size_bytes", 0),
    ],
)
def test_encrypted_manifest_rejects_downgrade_and_wrong_types(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    archive = tmp_path / "one.dump.age"
    archive.write_bytes(HEADER + b"synthetic")
    manifest = backup_manifest.build_manifest(
        archive,
        database_major="16",
        schema_revision="test",
        recipient=RECIPIENT,
    )
    with pytest.raises(backup_manifest.BackupManifestError):
        backup_manifest.validate_manifest({**manifest, field: value})
    if field != "schema_version":
        entry = backup_manifest.index_entry(manifest)
        with pytest.raises(backup_manifest.BackupManifestError):
            backup_manifest.build_index([{**entry, field: value}])


def test_plaintext_renamed_to_age_cannot_get_manifest(tmp_path: Path) -> None:
    archive = tmp_path / "renamed.dump.age"
    archive.write_bytes(b"PGDMP plaintext")
    with pytest.raises(backup_manifest.BackupManifestError, match="binary age"):
        backup_manifest.build_manifest(
            archive,
            database_major="16",
            schema_revision="test",
            recipient=RECIPIENT,
        )


@pytest.mark.parametrize(
    "failure", ["encrypt", "space", "manifest", "index", "legacy", "recipient"]
)
def test_failed_publication_keeps_previous_copy_and_commit_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    root = tmp_path / "backups"
    export = root / "offhost"
    private = root / "private"
    export.mkdir(parents=True)
    private.mkdir()
    monkeypatch.setattr(db_maintenance, "BACKUP_DIR", root)
    monkeypatch.setattr(db_maintenance, "_verify_archive", lambda path: None)
    old = export / "old.dump.age"
    old.write_bytes(HEADER + b"old")
    old_manifest = backup_manifest.build_manifest(
        old,
        database_major="16",
        schema_revision="test",
        recipient=RECIPIENT,
    )
    backup_manifest.write_json_atomic(export / old_manifest["manifest_name"], old_manifest)
    backup_manifest.write_json_atomic(
        export / "index.json", backup_manifest.build_index([old_manifest])
    )
    before = {p.name: p.read_bytes() for p in export.iterdir()}
    source = private / "new.dump"
    source.write_bytes(b"PGDMP synthetic")
    original_write = db_maintenance.write_json_atomic

    def fail_encrypt(*args: object, **kwargs: object) -> None:
        if failure == "space":
            raise OSError(28, "synthetic no space")
        raise RuntimeError("synthetic age failure")

    def fail_metadata(path: Path, value: object) -> None:
        if (failure == "manifest" and path.name.endswith("manifest.json")) or (
            failure == "index" and path.name == "index.json"
        ):
            raise OSError("synthetic publication failure")
        original_write(path, value)

    if failure in {"encrypt", "space"}:
        monkeypatch.setattr(db_maintenance, "_encrypt_archive", fail_encrypt)
    monkeypatch.setattr(db_maintenance, "write_json_atomic", fail_metadata)
    if failure == "legacy":
        (export / "legacy.dump").write_bytes(b"preserve legacy")
    with pytest.raises((RuntimeError, OSError, ValueError)):
        db_maintenance.publish_backup(
            source,
            publish_dir=export,
            database_major="16",
            schema_revision="test",
            recipient=("age1" + "p" * 58) if failure == "recipient" else RECIPIENT,
            age_path=AGE_PATH,
        )
    for name, content in before.items():
        assert (export / name).read_bytes() == content
    assert not list(export.glob("*.partial"))
    assert not list(root.glob(".age-*"))
    assert not (export / source.name).exists()
    if failure == "legacy":
        assert (export / "legacy.dump").read_bytes() == b"preserve legacy"
