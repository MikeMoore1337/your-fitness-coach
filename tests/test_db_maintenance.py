from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import db_maintenance


@pytest.fixture()
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    artifacts = tmp_path / ".artifacts"
    monkeypatch.setattr(db_maintenance, "ROOT", tmp_path)
    monkeypatch.setattr(db_maintenance, "ARTIFACTS", artifacts)
    monkeypatch.setattr(db_maintenance, "BACKUP_DIR", artifacts / "operations" / "backups")
    return artifacts


def test_artifact_path_accepts_only_paths_below_operational_backups(isolated_paths: Path) -> None:
    accepted = db_maintenance._artifact_path(Path(".artifacts/operations/backups/database.dump"))

    assert accepted == (isolated_paths / "operations" / "backups" / "database.dump").resolve()
    with pytest.raises(ValueError, match="backup paths must stay below"):
        db_maintenance._artifact_path(Path("database.dump"))
    with pytest.raises(ValueError, match="backup paths must stay below"):
        db_maintenance._artifact_path(isolated_paths.parent / "outside.dump")
    with pytest.raises(ValueError, match="backup paths must stay below"):
        db_maintenance._artifact_path(Path(".artifacts/runtime/cache/not-a-backup.dump"))


def test_restore_uses_single_transaction_and_streams_selected_dump(
    isolated_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = isolated_paths / "operations" / "backups" / "selected.dump"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"postgres-custom-dump")
    safety_backup = isolated_paths / "operations" / "backups" / "pre-restore.dump"
    captured: dict[str, object] = {}

    monkeypatch.setattr(db_maintenance, "_database_name", lambda: "fitminiapp_test")
    monkeypatch.setattr(db_maintenance, "create_backup", lambda output: safety_backup)

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured["command"] = command
        stream = kwargs["stdin"]
        assert hasattr(stream, "read")
        captured["dump"] = stream.read()
        captured["cwd"] = kwargs["cwd"]
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(db_maintenance.subprocess, "run", fake_run)

    result = db_maintenance.restore_backup(source, confirmed_database="fitminiapp_test")

    assert result == (safety_backup, "fitminiapp_test")
    assert captured["dump"] == b"postgres-custom-dump"
    assert captured["cwd"] == isolated_paths.parent
    assert captured["command"] == db_maintenance._compose_exec(db_maintenance.RESTORE_SCRIPT)
    assert "--single-transaction" in db_maintenance.RESTORE_SCRIPT


def test_restore_rejects_wrong_database_before_backup_or_pg_restore(
    isolated_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = isolated_paths / "operations" / "backups" / "selected.dump"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"postgres-custom-dump")
    monkeypatch.setattr(db_maintenance, "_database_name", lambda: "fitminiapp_test")

    def unexpected_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("backup/restore must not start after a confirmation mismatch")

    monkeypatch.setattr(db_maintenance, "create_backup", unexpected_call)
    monkeypatch.setattr(db_maintenance.subprocess, "run", unexpected_call)

    with pytest.raises(ValueError, match="confirmation does not match"):
        db_maintenance.restore_backup(source, confirmed_database="production")


def test_create_backup_refuses_to_overwrite_existing_dump(isolated_paths: Path) -> None:
    target = isolated_paths / "operations" / "backups" / "existing.dump"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"keep-me")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        db_maintenance.create_backup(target)

    assert target.read_bytes() == b"keep-me"


def test_create_backup_validates_dump_before_publishing(
    isolated_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = isolated_paths / "operations" / "backups" / "validated.dump"
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        if command == db_maintenance._compose_exec(db_maintenance.BACKUP_SCRIPT):
            stream = kwargs["stdout"]
            assert hasattr(stream, "write")
            stream.write(b"postgres-custom-dump")
            return SimpleNamespace(returncode=0, stderr=b"")

        assert command == db_maintenance._compose_exec(db_maintenance.VERIFY_DUMP_SCRIPT)
        stream = kwargs["stdin"]
        assert hasattr(stream, "read")
        assert stream.read() == b"postgres-custom-dump"
        assert kwargs["stdout"] is subprocess.DEVNULL
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(db_maintenance.subprocess, "run", fake_run)

    assert db_maintenance.create_backup(target) == target.resolve()
    assert target.read_bytes() == b"postgres-custom-dump"
    assert calls == [
        db_maintenance._compose_exec(db_maintenance.BACKUP_SCRIPT),
        db_maintenance._compose_exec(db_maintenance.VERIFY_DUMP_SCRIPT),
    ]


def test_create_backup_discards_dump_that_pg_restore_cannot_read(
    isolated_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = isolated_paths / "operations" / "backups" / "invalid.dump"

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command == db_maintenance._compose_exec(db_maintenance.BACKUP_SCRIPT):
            stream = kwargs["stdout"]
            assert hasattr(stream, "write")
            stream.write(b"invalid-dump")
            return SimpleNamespace(returncode=0, stderr=b"")
        return SimpleNamespace(returncode=1, stderr=b"invalid archive")

    monkeypatch.setattr(db_maintenance.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="could not read the new backup"):
        db_maintenance.create_backup(target)

    assert not target.exists()
    assert not target.with_suffix(".dump.partial").exists()


def test_cli_returns_error_for_output_outside_artifacts(
    isolated_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del isolated_paths
    monkeypatch.setattr(
        sys,
        "argv",
        ["db_maintenance.py", "backup", "--output", "database.dump"],
    )

    assert db_maintenance.main() == 1
    assert "backup paths must stay below" in capsys.readouterr().err


def test_database_name_uses_compose_without_exposing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="fitminiapp_test\n", stderr="")

    monkeypatch.setattr(db_maintenance.subprocess, "run", fake_run)

    assert db_maintenance._database_name() == "fitminiapp_test"
    assert captured["command"] == db_maintenance._compose_exec('printf "%s" "$POSTGRES_DB"')
    assert captured["kwargs"] == {
        "cwd": db_maintenance.ROOT,
        "check": True,
        "capture_output": True,
        "text": True,
    }


def test_encrypt_rejects_unpinned_binary_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "age.exe"
    executable.write_bytes(b"untrusted executable")

    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("untrusted binary executed")

    monkeypatch.setattr(db_maintenance.subprocess, "run", unexpected)
    with pytest.raises(ValueError, match="pinned official binary"):
        db_maintenance._encrypt_archive(
            tmp_path / "input.dump",
            tmp_path / "output.age",
            recipient="invalid",
            age_path=executable,
        )


def test_create_published_backup_removes_private_staging_on_age_failure(
    isolated_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = isolated_paths / "operations" / "backups"

    def fake_dump(path: Path) -> Path:
        path.write_bytes(b"PGDMP private")
        return path

    def failed_publish(path: Path, **kwargs: object) -> None:
        assert path.parent.parent == root
        assert path.parent != kwargs["publish_dir"]
        raise RuntimeError("synthetic encryption failure")

    monkeypatch.setattr(db_maintenance, "create_backup", fake_dump)
    monkeypatch.setattr(db_maintenance, "publish_backup", failed_publish)
    with pytest.raises(RuntimeError, match="encryption failure"):
        db_maintenance.create_published_backup(
            root / "offhost" / "new.dump.age",
            publish_dir=root / "offhost",
            database_major="16",
            schema_revision="test",
            recipient="invalid",
            age_path=Path("/age"),
        )
    assert list(root.iterdir()) == []
