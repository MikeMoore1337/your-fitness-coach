from __future__ import annotations

import os
from pathlib import Path

import pytest
from scripts import production_host_cleanup as cleanup


def _release(root: Path, revision: str, mtime: int) -> Path:
    release = root / "releases" / revision
    release.mkdir(parents=True)
    (release / ".deployment-sha").write_text(revision + "\n", encoding="utf-8")
    os.utime(release, (mtime, mtime))
    return release


def _setup(tmp_path: Path) -> tuple[Path, Path, str, str, str, str]:
    app = tmp_path / "app"
    tmp = tmp_path / "tmp"
    app.mkdir()
    tmp.mkdir()
    current_sha = "d" * 40
    old1 = "c" * 40
    old2 = "b" * 40
    old3 = "a" * 40
    current = _release(app, current_sha, 400)
    _release(app, old1, 300)
    _release(app, old2, 200)
    _release(app, old3, 100)
    (app / "current").symlink_to(current)

    backup = app / ".artifacts" / "operations" / "backups"
    backup.mkdir(parents=True)
    for index in range(8):
        path = backup / f"fitminiapp-20260919T0{index}0000Z.dump"
        path.write_bytes(str(index).encode())
        os.utime(path, (100 + index, 100 + index))
    (backup / "pre-restore-20260919T999999Z.dump").write_bytes(b"safe")
    (backup / "manual-note.txt").write_text("keep", encoding="utf-8")

    staging = app / "releases" / ".staging-failed-1"
    staging.mkdir()
    os.utime(staging, (100, 100))
    bundle = tmp / "yfc-deploy-old.tar.gz"
    bundle.write_bytes(b"bundle")
    os.utime(bundle, (100, 100))
    return app, tmp, current_sha, old1, old2, old3


def test_cleanup_keeps_five_backups_current_and_two_previous(tmp_path: Path, monkeypatch) -> None:
    app, tmp, current_sha, old1, old2, old3 = _setup(tmp_path)
    monkeypatch.setattr(cleanup, "_free_mb", lambda _path: 4096)

    report = cleanup.cleanup(
        app_root=app,
        target_revision=current_sha,
        backup_keep=5,
        previous_releases=2,
        tmp_root=tmp,
        warning_free_mb=3072,
        stale_ttl_hours=24,
        docker_prune=False,
    )

    backup = app / ".artifacts" / "operations" / "backups"
    assert len(list(backup.glob("fitminiapp-*.dump"))) == 5
    assert (backup / "pre-restore-20260919T999999Z.dump").exists()
    assert (backup / "manual-note.txt").exists()
    assert (app / "releases" / current_sha).exists()
    assert (app / "releases" / old1).exists()
    assert (app / "releases" / old2).exists()
    assert not (app / "releases" / old3).exists()
    assert not (app / "releases" / ".staging-failed-1").exists()
    assert not (tmp / "yfc-deploy-old.tar.gz").exists()
    assert len(report.removed_backups) == 3
    assert len(report.removed_releases) == 1


def test_cleanup_refuses_before_current_points_to_target(tmp_path: Path) -> None:
    app, tmp, _current_sha, *_ = _setup(tmp_path)

    with pytest.raises(cleanup.CleanupError, match="does not match target"):
        cleanup.cleanup(
            app_root=app,
            target_revision="e" * 40,
            backup_keep=5,
            previous_releases=2,
            tmp_root=tmp,
            warning_free_mb=3072,
            stale_ttl_hours=24,
            docker_prune=False,
        )


def test_release_with_bad_marker_is_preserved(tmp_path: Path, monkeypatch) -> None:
    app, tmp, current_sha, *_ = _setup(tmp_path)
    suspicious = app / "releases" / ("9" * 40)
    suspicious.mkdir()
    (suspicious / ".deployment-sha").write_text("8" * 40, encoding="utf-8")
    monkeypatch.setattr(cleanup, "_free_mb", lambda _path: 4096)

    report = cleanup.cleanup(
        app_root=app,
        target_revision=current_sha,
        backup_keep=5,
        previous_releases=2,
        tmp_root=tmp,
        warning_free_mb=3072,
        stale_ttl_hours=24,
        docker_prune=False,
    )

    assert suspicious.exists()
    assert any("mismatched marker" in warning for warning in report.warnings)


def test_docker_cleanup_never_prunes_volumes(monkeypatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        cleanup.subprocess,
        "run",
        lambda command, check=False: commands.append(command)
        or type("Result", (), {"returncode": 0})(),
    )
    report = cleanup.CleanupReport()

    cleanup._docker_prune(report)

    assert commands == [
        ["docker", "image", "prune", "--all", "--force"],
        ["docker", "builder", "prune", "--all", "--force"],
    ]
    assert all("volume" not in command for command in commands)
