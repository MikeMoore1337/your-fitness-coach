from __future__ import annotations

import gzip
import json
import os
import struct
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from scripts import backup_manifest as bm
from scripts import db_maintenance as db


def synthetic_dump() -> bytes:
    """Hand-built PG16 custom fixture: no database access and no pg_dump execution.

    Layout: PostgreSQL REL_16_STABLE pg_backup_archiver.c WriteHead/WriteToc.
    The one schema entry executes only this synthetic SQL during isolated restore.
    """

    def integer(value: int) -> bytes:
        return bytes([int(value < 0)]) + struct.pack("<I", abs(value))

    def text(value: str | None) -> bytes:
        if value is None:
            return integer(-1)
        data = value.encode("ascii")
        return integer(len(data)) + data

    sql = """CREATE TABLE public.parents(id serial PRIMARY KEY, payload bytea NOT NULL);
CREATE TABLE public.children(id serial PRIMARY KEY, parent_id integer REFERENCES public.parents);
INSERT INTO public.parents(payload) VALUES (decode('00ff10','hex'));
INSERT INTO public.children(parent_id) VALUES (1);
CREATE TABLE public.alembic_version(version_num text PRIMARY KEY);
INSERT INTO public.alembic_version VALUES ('synthetic_849');
"""
    header = b"PGDMP" + bytes([1, 15, 0, 4, 8, 1, 0])
    header += b"".join(integer(n) for n in [0, 0, 3, 22, 9, 126, 0])
    header += text("synthetic_only") + text("16.15") + text("16.15")
    toc = integer(1) + integer(1) + integer(0)
    toc += text("0") + text("0") + text("parents") + text("TABLE") + integer(1)
    toc += b"".join(text(v) for v in [sql, "", "", "public", "", "heap", "postgres", "false", None])
    return header + toc + bytes([3]) + bytes(8)


def make_archive(root: Path, created: datetime | None = None) -> Path:
    created = created or bm.utc_now()
    root.mkdir(parents=True, exist_ok=True)
    dump = root / "fixture.dump"
    dump.write_bytes(synthetic_dump())
    date = created.astimezone(timezone(timedelta(hours=3))).strftime("%Y-%m-%d")
    archive = root / f"backup-{date}.tar.gz"
    bm.create_tar_archive(
        dump,
        archive,
        {
            "schema_version": 1,
            "database_major": "16",
            "schema_revision": "synthetic_849",
            "created_at_utc": bm.format_utc(created),
        },
    )
    return archive


def manifest_for(path: Path) -> dict:
    return bm.build_manifest(path, database_major="16", schema_revision="synthetic_849")


def test_archive_manifest_index_roundtrip_and_safe_unpack(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    manifest = manifest_for(archive)
    if os.name != "nt":
        assert archive.stat().st_mode & 0o777 == 0o640
        previous_umask = os.umask(0o077)
        try:
            private_archive = make_archive(tmp_path / "private")
            assert private_archive.stat().st_mode & 0o777 == 0o600
        finally:
            os.umask(previous_umask)
    bm.write_json_atomic(tmp_path / manifest["manifest_name"], manifest)
    index = bm.build_index([manifest])
    assert bm.validate_index(index) == index
    assert manifest["archive_sha256"] == bm.sha256_file(archive)
    assert manifest["schema_version"] == 3 and manifest["restore_status"] == "not_run"
    assert "recipient" not in manifest and "age_version" not in manifest
    output = tmp_path / "unpacked"
    bm.unpack_archive(archive, output)
    assert (output / "database.dump").read_bytes() == synthetic_dump()
    assert {p.name for p in output.iterdir()} == {"database.dump", "recovery.json"}
    with pytest.raises(FileExistsError):
        bm.unpack_archive(archive, output)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("schema_version", "3"),
        ("schema_version", 3.0),
        ("schema_version", True),
        ("archive_format", "age-v1"),
        ("archive_name", "../outside.tar.gz"),
        ("archive_name", "backup-2026-99-99.tar.gz"),
        ("archive_name", "legacy.dump.age"),
        ("archive_size_bytes", "100"),
        ("archive_size_bytes", True),
        ("archive_size_bytes", 0),
        ("archive_sha256", "0"),
        ("created_at_utc", "2999-01-01T00:00:00Z"),
    ],
)
def test_manifest_and_index_reject_bad_metadata(tmp_path: Path, field: str, value: object) -> None:
    manifest = manifest_for(make_archive(tmp_path))
    with pytest.raises(bm.BackupManifestError):
        bm.validate_manifest({**manifest, field: value})
    entry = bm.index_entry(manifest)
    if field == "schema_version":
        with pytest.raises(bm.BackupManifestError):
            bm.validate_index({**bm.build_index([manifest]), field: value})
    else:
        with pytest.raises(bm.BackupManifestError):
            bm.build_index([{**entry, field: value}])


def test_duplicates_and_future_index_rejected(tmp_path: Path) -> None:
    manifest = manifest_for(make_archive(tmp_path))
    with pytest.raises(bm.BackupManifestError, match="duplicate"):
        bm.build_index([manifest, manifest])
    with pytest.raises(bm.BackupManifestError, match="future"):
        bm.validate_index(
            {**bm.build_index([manifest]), "generated_at_utc": "2999-01-01T00:00:00Z"}
        )


@pytest.mark.parametrize("damage", ["truncated", "crc", "raw-dump", "tar-checksum", "trailing"])
def test_corrupt_archive_rejected_before_output(tmp_path: Path, damage: str) -> None:
    archive = make_archive(tmp_path)
    data = archive.read_bytes()
    if damage == "truncated":
        data = data[:-8]
    elif damage == "crc":
        data = data[:-8] + bytes([data[-8] ^ 1]) + data[-7:]
    elif damage == "raw-dump":
        data = synthetic_dump()
    else:
        raw = bytearray(gzip.decompress(data))
        if damage == "tar-checksum":
            raw[0] ^= 1
        else:
            raw += b"unexpected"
        data = gzip.compress(raw)
    archive.write_bytes(data)
    with pytest.raises(bm.BackupManifestError):
        bm.unpack_archive(archive, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("../escape", tarfile.REGTYPE),
        ("/absolute", tarfile.REGTYPE),
        ("C:/escape", tarfile.REGTYPE),
        ("..\\escape", tarfile.REGTYPE),
        ("database.dump", tarfile.SYMTYPE),
        ("database.dump", tarfile.LNKTYPE),
        ("database.dump", tarfile.CHRTYPE),
        ("database.dump", tarfile.FIFOTYPE),
        ("database.dump", tarfile.DIRTYPE),
        ("extra.txt", tarfile.REGTYPE),
        ("database.dump", tarfile.REGTYPE),
        ("pax", tarfile.XHDTYPE),
    ],
)
def test_unsafe_tar_rejected_even_with_valid_outer_hash(
    tmp_path: Path, name: str, kind: bytes
) -> None:
    good = make_archive(tmp_path)
    raw = gzip.decompress(good.read_bytes())
    # Inject after the two legitimate files, before the end marker.
    with tarfile.open(good) as stream:
        last = stream.getmembers()[-1]
        end = last.offset_data + ((last.size + 511) // 512) * 512
    member = tarfile.TarInfo(name)
    member.type = kind
    if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
        member.linkname = "../escape"
    raw = raw[:end] + member.tobuf(format=tarfile.USTAR_FORMAT) + bytes(1024)
    good.write_bytes(gzip.compress(raw))
    assert len(bm.sha256_file(good)) == 64
    with pytest.raises(bm.BackupManifestError):
        bm.unpack_archive(good, tmp_path / "out")
    assert not (tmp_path / "out").exists() and not (tmp_path.parent / "escape").exists()


@pytest.fixture()
def publisher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "backups"
    root.mkdir()
    monkeypatch.setattr(db, "BACKUP_DIR", root)
    monkeypatch.setattr(db, "_verify_archive", lambda path: None)
    return root


def publish(root: Path, created: datetime | None = None, retain: int = 7) -> tuple:
    private = root / "private"
    private.mkdir(exist_ok=True)
    source = private / "synthetic.dump"
    source.write_bytes(synthetic_dump())
    return db.publish_backup(
        source,
        publish_dir=root / "export",
        database_major="16",
        schema_revision="synthetic_849",
        created_at=created,
        retain=retain,
    )


def test_publication_rechecks_dump_then_commits_index(
    publisher: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified = []
    monkeypatch.setattr(db, "_verify_archive", lambda path: verified.append(path))
    manifest, index, warnings = publish(publisher)
    assert verified == [publisher / "private" / "synthetic.dump"]
    assert warnings == ()
    entry = bm.read_index(index)["backups"][0]
    assert bm.index_entry(bm.read_manifest(manifest)) == entry
    db._validate_published_entry(index.parent, entry)
    before = {p.name: p.read_bytes() for p in index.parent.iterdir()}
    with pytest.raises(FileExistsError):
        publish(publisher)
    assert before == {p.name: p.read_bytes() for p in index.parent.iterdir()}



@pytest.mark.skipif(os.name != "posix", reason="POSIX SFTP permission contract")
def test_sftp_export_metadata_group_readable_after_index_replacement(publisher: Path) -> None:
    now = bm.utc_now()
    original_umask = os.umask(0o027)
    try:
        first_manifest, index, _ = publish(publisher, now - timedelta(days=1))
        second_manifest, index, _ = publish(publisher, now)
    finally:
        os.umask(original_umask)
    entries = bm.read_index(index)["backups"]
    assert len(entries) == 2
    for metadata in (first_manifest, second_manifest, index):
        assert metadata.stat().st_mode & 0o777 == 0o640
        assert metadata.stat().st_gid == os.getgid()
    for entry in entries:
        archive = index.parent / entry["archive_name"]
        assert archive.stat().st_mode & 0o777 == 0o640
        assert archive.stat().st_gid == os.getgid()
    private_metadata = publisher / "private" / "private.json"
    bm.write_json_atomic(private_metadata, {"private": True})
    assert private_metadata.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX SFTP permission contract")
def test_group_readable_json_failure_keeps_existing_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = tmp_path / "index.json"
    bm.write_json_atomic(index, {"version": 1}, group_readable=True)
    original = index.read_bytes()

    def reject_mode(*args: object) -> None:
        raise OSError("synthetic chmod failure")

    monkeypatch.setattr(bm.os, "fchmod", reject_mode)
    with pytest.raises(OSError, match="chmod failure"):
        bm.write_json_atomic(index, {"version": 2}, group_readable=True)
    assert index.read_bytes() == original
    assert not list(tmp_path.glob("*.partial"))

def test_retention_keeps_two_good_even_when_all_expired(publisher: Path) -> None:
    now = bm.utc_now()
    for days in (10, 9, 8):
        _, index, _ = publish(publisher, now - timedelta(days=days))
    entries = bm.read_index(index)["backups"]
    assert len(entries) == 2
    assert all((index.parent / entry["archive_name"]).is_file() for entry in entries)
    assert len(list(index.parent.glob("*.tar.gz"))) == 2
    publish(publisher, now - timedelta(days=6))
    assert len(bm.read_index(index)["backups"]) == 2


def test_corrupt_existing_copy_blocks_rotation_and_preserves_other_copy(publisher: Path) -> None:
    now = bm.utc_now()
    publish(publisher, now - timedelta(days=10))
    _, index, _ = publish(publisher, now - timedelta(days=9))
    old = index.parent / bm.read_index(index)["backups"][0]["archive_name"]
    old.write_bytes(b"corrupt")
    before = {p.name: p.read_bytes() for p in index.parent.iterdir()}
    with pytest.raises(bm.BackupManifestError):
        publish(publisher)
    assert before == {p.name: p.read_bytes() for p in index.parent.iterdir()}


@pytest.mark.parametrize("failure", ["pack", "space", "manifest", "index", "legacy", "rotation"])
def test_failed_publication_preserves_two_previous_copies(
    publisher: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    now = bm.utc_now()
    publish(publisher, now - timedelta(days=2))
    _, index, _ = publish(publisher, now - timedelta(days=1))
    before = {p.name: p.read_bytes() for p in index.parent.iterdir()}
    write = db.write_json_atomic

    def fail_write(path: Path, value: dict, *, group_readable: bool = False) -> None:
        if (failure == "manifest" and path.name.endswith(".manifest.json")) or (
            failure == "index" and path.name == "index.json"
        ):
            raise OSError("synthetic metadata failure")
        write(path, value, group_readable=group_readable)

    def fail_pack(*args: object) -> None:
        raise OSError("synthetic pack/space failure")

    monkeypatch.setattr(db, "write_json_atomic", fail_write)
    if failure in {"pack", "space"}:
        monkeypatch.setattr(db, "create_tar_archive", fail_pack)
    if failure == "legacy":
        (index.parent / "old.dump.age").write_bytes(b"legacy-preserved")
    if failure == "rotation":
        unlink = Path.unlink

        def fail_unlink(path: Path, *args: object, **kwargs: object) -> None:
            if path.name in before:
                raise OSError("synthetic rotation failure")
            unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_unlink)
        _, _, warnings = publish(publisher, retain=1)
        assert warnings
    else:
        with pytest.raises((OSError, ValueError)):
            publish(publisher)
    for name, content in before.items():
        if name != "index.json" or failure != "rotation":
            assert (index.parent / name).read_bytes() == content
    assert not list(publisher.glob(".tar-*"))
    if failure == "legacy":
        assert (index.parent / "old.dump.age").read_bytes() == b"legacy-preserved"


def test_windows_bom_sidecar_and_recovery_mismatch(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    manifest = manifest_for(archive)
    path = tmp_path / manifest["manifest_name"]
    path.write_text(json.dumps(manifest), encoding="utf-8-sig")
    assert bm.read_manifest(path) == manifest
    with pytest.raises(bm.BackupManifestError, match="does not match"):
        bm.build_manifest(archive, database_major="17", schema_revision="synthetic_849")


def test_disabled_schedule_and_storage_contract() -> None:
    import xml.etree.ElementTree as et

    directory = (
        Path(__file__).resolve().parents[1] / "docs/operations/v11-rec-01-off-host-backup-recovery"
    )
    config = json.loads((directory / "windows-pull.config.example.json").read_text())
    assert (
        config["retention_days"],
        config["minimum_valid_backups"],
        config["stale_after_hours"],
    ) == (7, 2, 26)
    assert "encryption_at_rest" not in config and config["python_path"]
    task = et.parse(directory / "windows-pull-task.example.xml")
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert [node.text for node in task.findall(".//t:Enabled", ns)] == ["false", "false"]
    assert task.find(".//t:Interval", ns).text == "PT1H"
    assert task.find(".//t:StartBoundary", ns).text.endswith("00:30:00+03:00")
