"""Contract tests for non-root deployment identity and libpq credential DAC."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import sequential_deploy_safety as safety


@pytest.fixture
def observer_access(monkeypatch):
    deploy_uid, deploy_gid = 2001, 2002
    directory = safety.OBSERVER_DIRECTORY
    service, password = directory / "pg_service.conf", directory / "pgpass"

    def info(permissions: int, *, uid: int, gid: int, ino: int, file: bool):
        return SimpleNamespace(
            st_mode=(stat.S_IFREG if file else stat.S_IFDIR) | permissions,
            st_uid=uid,
            st_gid=gid,
            st_dev=18,
            st_ino=ino,
            st_nlink=1,
        )

    paths = {
        directory: info(0o750, uid=0, gid=deploy_gid, ino=30, file=False),
        service: info(0o640, uid=0, gid=deploy_gid, ino=31, file=True),
        password: info(0o600, uid=deploy_uid, gid=deploy_gid, ino=32, file=True),
    }
    for parent in directory.parents:
        paths[parent] = info(0o755, uid=0, gid=0, ino=20, file=False)

    monkeypatch.setattr(
        safety.pwd,
        "getpwnam",
        lambda name: (
            SimpleNamespace(pw_uid=deploy_uid, pw_gid=deploy_gid) if name == "yfc-deploy" else None
        ),
    )
    monkeypatch.setattr(safety.os, "geteuid", lambda: deploy_uid)
    monkeypatch.setattr(safety.os, "getegid", lambda: deploy_gid)
    monkeypatch.setattr(Path, "lstat", lambda path: paths[path])

    opens: list[tuple[Path, int]] = []

    def fake_open(path, flags):
        opens.append((path, flags))
        return paths[path].st_ino

    monkeypatch.setattr(safety.os, "open", fake_open)
    monkeypatch.setattr(
        safety.os, "fstat", lambda fd: next(m for m in paths.values() if m.st_ino == fd)
    )
    monkeypatch.setattr(safety.os, "close", lambda fd: None)
    return paths, directory, service, password, opens


def test_non_root_deploy_account_can_open_protected_files(observer_access):
    _, _, service, password, opens = observer_access
    safety._protected_observer_files()
    assert [path for path, _ in opens] == [service, password]
    assert all(flags & os.O_NOFOLLOW for _, flags in opens)
    assert all(flags & os.O_CLOEXEC for _, flags in opens)


@pytest.mark.parametrize(
    "name,attribute,value",
    [
        ("directory", "st_mode", stat.S_IFDIR | 0o700),
        ("directory", "st_gid", 0),
        ("directory", "st_uid", 2001),
        ("service", "st_mode", stat.S_IFREG | 0o644),
        ("service", "st_mode", stat.S_IFREG | 0o600),
        ("service", "st_uid", 2001),
        ("service", "st_nlink", 2),
        ("password", "st_uid", 0),
        ("password", "st_mode", stat.S_IFREG | 0o640),
        ("password", "st_mode", stat.S_IFLNK | 0o600),
        ("password", "st_nlink", 2),
    ],
)
def test_misowned_or_overpermissive_files_are_rejected(observer_access, name, attribute, value):
    paths, directory, service, password, _ = observer_access
    path = {"directory": directory, "service": service, "password": password}[name]
    setattr(paths[path], attribute, value)
    with pytest.raises(safety.SafetyError):
        safety._protected_observer_files()


def test_world_writable_parent_is_rejected(observer_access):
    paths, directory, _, _, _ = observer_access
    parent = directory.parent
    paths[parent].st_mode = stat.S_IFDIR | 0o777
    with pytest.raises(safety.SafetyError, match="parent_unprotected"):
        safety._protected_observer_files()


def test_wrong_effective_user_is_rejected(observer_access, monkeypatch):
    monkeypatch.setattr(safety.os, "geteuid", lambda: 0)
    with pytest.raises(safety.SafetyError, match="identity_invalid"):
        safety._protected_observer_files()


def test_missing_account_is_rejected(observer_access, monkeypatch):
    def missing(_):
        raise KeyError("not installed")

    monkeypatch.setattr(safety.pwd, "getpwnam", missing)
    with pytest.raises(safety.SafetyError, match="identity_missing"):
        safety._protected_observer_files()


def test_open_failure_is_fail_closed(observer_access, monkeypatch):
    def unavailable(*_):
        raise PermissionError("private credential")

    monkeypatch.setattr(safety.os, "open", unavailable)
    with pytest.raises(safety.SafetyError, match="unreadable"):
        safety._protected_observer_files()


def test_file_swap_between_metadata_and_open_is_rejected(observer_access, monkeypatch):
    paths, _, _, _, _ = observer_access

    def changed(fd):
        actual = next(m for m in paths.values() if m.st_ino == fd)
        return SimpleNamespace(**{**vars(actual), "st_ino": actual.st_ino + 100})

    monkeypatch.setattr(safety.os, "fstat", changed)
    with pytest.raises(safety.SafetyError, match="changed_during_access"):
        safety._protected_observer_files()
